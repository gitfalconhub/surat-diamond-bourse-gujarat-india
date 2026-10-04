# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable procedural PBR materials and still-lighting recipes, metres / Z up.

Call apply(scene) once after geometry modules, then configure_daylight(scene) or
configure_dusk(scene). No render, file save, animation or geometry creation occurs.
"""
from __future__ import annotations
import math
from pathlib import Path
import bpy
from mathutils import Vector

VERSION = '2026-09-30.3'


def _node(nt, kind, name=None, xy=None):
    n = nt.nodes.new(kind)
    if name:
        n.name = name
        n.label = name
    if xy:
        n.location = xy
    return n


def _input(nt, socket, value):
    if hasattr(value, 'is_output'):
        nt.links.new(value, socket)
    else:
        socket.default_value = value


def _math(nt, op, a, b=None):
    n = _node(nt, 'ShaderNodeMath', op)
    n.operation = op
    _input(nt, n.inputs[0], a)
    if b is not None:
        _input(nt, n.inputs[1], b)
    return n.outputs[0]


def _mix(nt, fac, a, b, mode='MIX', name=None):
    n = _node(nt, 'ShaderNodeMixRGB', name)
    n.blend_type = mode
    _input(nt, n.inputs[0], fac)
    _input(nt, n.inputs[1], a)
    _input(nt, n.inputs[2], b)
    return n.outputs[0]


def _ramp(nt, fac, lo, hi, name, positions=(0.0, 1.0)):
    n = _node(nt, 'ShaderNodeValToRGB', name)
    n.color_ramp.elements[0].position = positions[0]
    n.color_ramp.elements[0].color = (*lo[:3], 1)
    n.color_ramp.elements[1].position = positions[1]
    n.color_ramp.elements[1].color = (*hi[:3], 1)
    _input(nt, n.inputs['Fac'], fac)
    return n.outputs['Color']


def _scalar_range(nt, fac, low, high, name):
    n = _node(nt, 'ShaderNodeMapRange', name)
    n.clamp = True
    _input(nt, n.inputs['Value'], fac)
    n.inputs['From Min'].default_value = 0
    n.inputs['From Max'].default_value = 1
    n.inputs['To Min'].default_value = low
    n.inputs['To Max'].default_value = high
    return n.outputs[0]


def _new_material(name, color, roughness=.5, metallic=0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    nt = m.node_tree
    out = _node(nt, 'ShaderNodeOutputMaterial', 'Material Output', (840, 100))
    p = _node(nt, 'ShaderNodeBsdfPrincipled', 'Principled BSDF', (560, 100))
    p.inputs['Base Color'].default_value = (*color[:3], 1)
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Metallic'].default_value = metallic
    p.inputs['IOR'].default_value = 1.5
    nt.links.new(p.outputs['BSDF'], out.inputs['Surface'])
    m.diffuse_color = (*color[:3], 1)
    m['sdb_polish_version'] = VERSION
    return m, nt, p


def _position(nt):
    geo = _node(nt, 'ShaderNodeNewGeometry', 'World metres / geometric normal', (-1400, 60))
    return geo.outputs['Position'], geo.outputs.get('True Normal', geo.outputs['Normal'])


def _noise(nt, position, scale, detail=2, roughness=.55, name='Mineral noise'):
    n = _node(nt, 'ShaderNodeTexNoise', name)
    n.noise_dimensions = '3D'
    _input(nt, n.inputs['Vector'], position)
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = roughness
    return n.outputs['Fac']


def _bump(nt, p, fac, strength=.12, distance=.0006, normal=None):
    n = _node(nt, 'ShaderNodeBump', 'Submillimetre surface grain')
    n.inputs['Strength'].default_value = strength
    n.inputs['Distance'].default_value = distance
    _input(nt, n.inputs['Height'], fac)
    if normal:
        _input(nt, n.inputs['Normal'], normal)
    nt.links.new(n.outputs['Normal'], p.inputs['Normal'])
    return n.outputs['Normal']


def _layout(nt):
    """Keep node editing usable without relying on a UI layout operator."""
    reserved = {'Material Output', 'Principled BSDF', 'World metres / geometric normal'}
    i = 0
    for n in nt.nodes:
        if n.name in reserved:
            continue
        n.location = (-1100 + (i % 6) * 265, -220 - (i // 6) * 205)
        i += 1


def _panel_projection(nt, a, b, size, joint):
    """Continuous world projection, symmetric seams and stable per-panel colour."""
    u = _math(nt, 'DIVIDE', a, size[0])
    v = _math(nt, 'DIVIDE', b, size[1])
    seams = []
    for q, dimension in ((u, size[0]), (v, size[1])):
        fract = _math(nt, 'FRACT', q)
        distance = _math(nt, 'MINIMUM', fract, _math(nt, 'SUBTRACT', 1, fract))
        seams.append(_scalar_range(nt, _math(nt, 'DIVIDE', distance, joint / dimension), 1, 0, 'Soft recessed joint edge'))
    seam = _math(nt, 'MAXIMUM', *seams)
    cell = _node(nt, 'ShaderNodeCombineXYZ', 'Panel cell in metres')
    _input(nt, cell.inputs['X'], _math(nt, 'FLOOR', u))
    _input(nt, cell.inputs['Y'], _math(nt, 'FLOOR', v))
    white = _node(nt, 'ShaderNodeTexWhiteNoise', 'Stable panel tone')
    white.noise_dimensions = '2D'
    _input(nt, white.inputs['Vector'], cell.outputs[0])
    return seam, white.outputs['Value']


def _triplanar_panels(nt, position, normal, size=(1.2, .9), joint=.003):
    pos = _node(nt, 'ShaderNodeSeparateXYZ', 'World XYZ')
    nor = _node(nt, 'ShaderNodeSeparateXYZ', 'Unperturbed surface XYZ')
    _input(nt, pos.inputs[0], position)
    _input(nt, nor.inputs[0], normal)
    weights = [_math(nt, 'POWER', _math(nt, 'ABSOLUTE', nor.outputs[axis]), 12.0) for axis in ('X', 'Y', 'Z')]
    total = _math(nt, 'MAXIMUM', _math(nt, 'ADD', _math(nt, 'ADD', weights[0], weights[1]), weights[2]), .00001)
    weights = [_math(nt, 'DIVIDE', weight, total) for weight in weights]
    # X-facing wall: YZ; Y-facing wall: XZ; horizontal roof/floor: XY.
    projections = [
        _panel_projection(nt, pos.outputs['Y'], pos.outputs['Z'], size, joint),
        _panel_projection(nt, pos.outputs['X'], pos.outputs['Z'], size, joint),
        _panel_projection(nt, pos.outputs['X'], pos.outputs['Y'], size, joint),
    ]
    values = []
    for index in (0, 1):
        values.append(_math(nt, 'ADD', _math(nt, 'ADD', _math(nt, 'MULTIPLY', projections[0][index], weights[0]), _math(nt, 'MULTIPLY', projections[1][index], weights[1])), _math(nt, 'MULTIPLY', projections[2][index], weights[2])))
    return values


def _stone(name, base, roughness, size=(1.2, .9), joint=.003, polished=False, panels=True):
    m, nt, p = _new_material(name, base, roughness)
    position, normal = _position(nt)
    mineral = _noise(nt, position, 3.7, 3, name='Stone mineral clouds / 27 cm')
    grain = _noise(nt, position, 175, 2, name='Stone grain / 6 mm')
    color = _ramp(nt, mineral, tuple(c * .96 for c in base), tuple(min(1, c * 1.04) for c in base), 'Restrained stone variation')
    if panels:
        seam, paneltone = _triplanar_panels(nt, position, normal, size, joint)
        panelmult = _ramp(nt, paneltone, (.90, .90, .90) if polished else (.94, .94, .94), (1.08, 1.08, 1.08) if polished else (1.045, 1.045, 1.045), 'Stone-specific panel tone range')
        color = _mix(nt, 1, color, panelmult, 'MULTIPLY', 'Mineral and panel colour')
        color = _mix(nt, seam, color, tuple(c * .66 for c in base) + (1,), name='Stone toned joints')
        jointnormal = _node(nt, 'ShaderNodeBump', 'Recessed panel joints / 1.2 mm')
        jointnormal.invert = True
        jointnormal.inputs['Strength'].default_value = .22
        jointnormal.inputs['Distance'].default_value = .0012
        _input(nt, jointnormal.inputs['Height'], seam)
        _bump(nt, p, grain, .11, .00024 if polished else .0006, jointnormal.outputs['Normal'])
    else:
        _bump(nt, p, grain, .10, .0003 if polished else .0006)
    _input(nt, p.inputs['Base Color'], color)
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, grain, max(.06, roughness - .045), min(1, roughness + .045), 'Variable microsurface roughness'))
    if polished:
        p.inputs['Coat Weight'].default_value = .12
        p.inputs['Coat Roughness'].default_value = .18
    m['sdb_mapping'] = 'world-space metric, True Normal weighted YZ/XZ/XY; UV independent'
    m['sdb_panel_dimensions_m'] = list(size)
    _layout(nt)
    return m


def _granular(name, base, roughness, scale=75, distance=.0006, variation=.13):
    m, nt, p = _new_material(name, base, roughness)
    position, _ = _position(nt)
    broad = _noise(nt, position, .8, 3, name='Large surface variation / 1.25 m')
    micro = _noise(nt, position, scale, 2, name='Aggregate / actual metre scale')
    color = _ramp(nt, broad, tuple(c * (1 - variation) for c in base), tuple(c * (1 + variation) for c in base), 'Muted surface colour range')
    _input(nt, p.inputs['Base Color'], color)
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, micro, max(.08, roughness - .05), min(1, roughness + .05), 'Aggregate roughness'))
    _bump(nt, p, micro, .17, distance)
    _layout(nt)
    return m


def _wood(name):
    m, nt, p = _new_material(name, (.23, .105, .045), .43)
    tex = _node(nt, 'ShaderNodeTexCoord', 'Object grain coordinates')
    mapping = _node(nt, 'ShaderNodeVectorMath', 'Longitudinal timber grain')
    mapping.operation = 'MULTIPLY'
    _input(nt, mapping.inputs[0], tex.outputs['Object'])
    mapping.inputs[1].default_value = (1.8, 36, 36)
    grain = _noise(nt, mapping.outputs[0], 1, 3, name='Timber annual fibre')
    _input(nt, p.inputs['Base Color'], _ramp(nt, grain, (.13, .057, .023), (.31, .16, .075), 'Warm natural timber grain'))
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, grain, .35, .50, 'Timber finish variation'))
    _bump(nt, p, grain, .12, .00015)
    p.inputs['Coat Weight'].default_value = .17
    p.inputs['Coat Roughness'].default_value = .32
    _layout(nt)
    return m


def glass_material(name='SDB Clear Architectural Glass', *, transmission=1.0, tint=(.93, .97, .98), roughness=.035):
    """True dielectric for thin glass geometry with a modelled occupied space."""
    m, nt, p = _new_material(name, tint, roughness, 0)
    p.inputs['IOR'].default_value = 1.52
    if 'Transmission Weight' in p.inputs:
        p.inputs['Transmission Weight'].default_value = transmission
    else:
        p.inputs['Transmission'].default_value = transmission
    m['sdb_glass_geometry'] = 'Use thin 12-18 mm panes / hollow shell, never a tower volume'
    _layout(nt)
    return m


def _backed_glass():
    """An opaque interior-backed optical proxy for the inherited solid boxes."""
    m, nt, p = _new_material('SDB Dark Blue Glazing', (.029, .043, .047), .065, 0)
    p.inputs['IOR'].default_value = 1.52
    # The Principled dielectric Fresnel gives a neutral glass reflection; the
    # dark diffuse substrate is an aggregate of the unseen interior beyond it.
    # No metallic tint and no transmission through 60 m of solid glass.
    p.inputs['Coat Weight'].default_value = .18
    p.inputs['Coat Roughness'].default_value = .045
    pos, _ = _position(nt)
    variation = _noise(nt, pos, .29, 1, name='Restrained occupied-space backing variation')
    _input(nt, p.inputs['Base Color'], _ramp(nt, variation, (.023, .034, .036), (.042, .057, .060), 'Interior backing, not metallic glass tint'))
    m['sdb_glass_geometry'] = 'Nontransmitting dielectric plus dark interior proxy for closed boxes; replace on hollow bays with SDB Clear Architectural Glass'
    _layout(nt)
    return m


def _metal(name, base, roughness, metallic=1):
    m, nt, p = _new_material(name, base, roughness, metallic)
    position, _ = _position(nt)
    grain = _noise(nt, position, 240, 1, name='Very fine metal finish')
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, grain, max(.04, roughness - .025), roughness + .025, 'Metal microsurface'))
    _bump(nt, p, grain, .05, .00004)
    _layout(nt)
    return m


def _leaf(name, base):
    """Thin botanical surface: restrained specular and diffuse transmission."""
    m, nt, p = _new_material(name, base, .75)
    position, _ = _position(nt)
    fleck = _noise(nt, position, 28, 2, name='Leaf pigmentation / actual scale')
    color = _ramp(nt, fleck, tuple(c * .85 for c in base), tuple(c * 1.09 for c in base), 'Subtle botanical colour')
    _input(nt, p.inputs['Base Color'], color)
    _bump(nt, p, fleck, .07, .00008)
    if 'Specular IOR Level' in p.inputs:
        p.inputs['Specular IOR Level'].default_value = .30
    translucent = _node(nt, 'ShaderNodeBsdfTranslucent', 'Thin leaf diffuse light transmission')
    _input(nt, translucent.inputs['Color'], color)
    mix = _node(nt, 'ShaderNodeMixShader', 'Leaf body and transmission')
    mix.inputs[0].default_value = .13
    nt.links.new(p.outputs['BSDF'], mix.inputs[1])
    nt.links.new(translucent.outputs['BSDF'], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
    _layout(nt)
    return m


def _turf(name):
    """Dense fine ground response beneath geometry, with restrained patchiness."""
    m,nt,p=_new_material(name,(.071,.132,.027),.86)
    position,_=_position(nt)
    patches=_noise(nt,position,1.1,3,name='Small changes in lawn growth')
    color=_ramp(nt,patches,(.047,.094,.016),(.087,.15,.033),'Natural lawn colour variation')
    _input(nt,p.inputs['Base Color'],color)
    detail=_noise(nt,position,340,2,name='Dense fine blades under geometry')
    _bump(nt,p,detail,.30,.0015)
    root=Path(__file__).resolve().parents[1];folder=root/'textures'/'Grass004'
    files={key:folder/('Grass004_2K-JPG_'+part+'.jpg') for key,part in [('color','Color'),('normal','NormalGL'),('rough','Roughness')]}
    if all(path.is_file() for path in files.values()):
        scale=_node(nt,'ShaderNodeVectorMath','1.4 metre lawn material repeat');scale.operation='SCALE'
        nt.links.new(position,scale.inputs[0]);scale.inputs['Scale'].default_value=1/1.4
        maps={}
        for key,path in files.items():
            im=bpy.data.images.get(path.name) or bpy.data.images.load(str(path),check_existing=True);im.colorspace_settings.name='sRGB' if key=='color' else 'Non-Color'
            if not im.packed_file:im.pack()
            im.filepath='//textures/Grass004/'+path.name
            node=_node(nt,'ShaderNodeTexImage','ambientCG lawn '+key);node.image=im;node.extension='REPEAT'
            nt.links.new(scale.outputs[0],node.inputs['Vector']);maps[key]=node
        tint=_mix(nt,.18,maps['color'].outputs['Color'],color,mode='MULTIPLY',name='Subtle variation over dense lawn texture')
        nt.links.new(tint,p.inputs['Base Color']);nt.links.new(maps['rough'].outputs['Color'],p.inputs['Roughness'])
        normal=_node(nt,'ShaderNodeNormalMap','Lawn surface normal');normal.space='OBJECT';normal.inputs['Strength'].default_value=.55
        nt.links.new(maps['normal'].outputs['Color'],normal.inputs['Color']);nt.links.new(normal.outputs['Normal'],p.inputs['Normal'])
        m['asset_source']='https://ambientcg.com/view?id=Grass004';m['asset_license']='CC0';m['texture_width_metres']=1.4
    _layout(nt)
    return m


def _photographic_ground(name):
    """Packed CC0 Poly Haven leaf litter used only beneath ornamental planting."""
    root=Path(__file__).resolve().parents[1]
    folder=root/'textures'/'leafy_grass'
    paths={k:folder/('leafy_grass_'+k+'_2k.jpg') for k in ('diff','rough','nor_gl')}
    if not all(p.is_file() for p in paths.values()):
        return _granular(name,(.07,.039,.018),1,28,.002,.3)
    m,nt,p=_new_material(name,(.065,.07,.027),.9)
    position,_=_position(nt)
    mapping=_node(nt,'ShaderNodeVectorMath','Two metre photographic ground repeat');mapping.operation='SCALE'
    nt.links.new(position,mapping.inputs[0]);mapping.inputs['Scale'].default_value=.5
    images={}
    for key,path in paths.items():
        im=bpy.data.images.get(path.name) or bpy.data.images.load(str(path),check_existing=True)
        im.colorspace_settings.name='sRGB' if key=='diff' else 'Non-Color'
        if not im.packed_file:im.pack()
        im.filepath='//textures/leafy_grass/'+path.name
        n=_node(nt,'ShaderNodeTexImage','Poly Haven '+key);n.image=im;n.extension='REPEAT'
        nt.links.new(mapping.outputs[0],n.inputs['Vector']);images[key]=n
    # A dark leaf-litter mix suits the maintained planter beds; raw meadow
    # colours would misrepresent the closely trimmed lawn in the references.
    color=_mix(nt,.42,images['diff'].outputs['Color'],(.045,.027,.012,1),mode='MULTIPLY',name='Shaded planting bed litter')
    nt.links.new(color,p.inputs['Base Color']);nt.links.new(images['rough'].outputs['Color'],p.inputs['Roughness'])
    normal=_node(nt,'ShaderNodeNormalMap','Photographic OpenGL normal');normal.space='OBJECT';normal.inputs['Strength'].default_value=.65
    nt.links.new(images['nor_gl'].outputs['Color'],normal.inputs['Color']);nt.links.new(normal.outputs['Normal'],p.inputs['Normal'])
    m['asset_source']='https://polyhaven.com/a/leafy_grass';m['asset_license']='CC0';m['texture_width_metres']=2.0
    _layout(nt)
    return m


def _marble():
    m, nt, p = _new_material('SDB Interior Polished Marble', (.70, .69, .63), .18)
    position, _ = _position(nt)
    vein = _noise(nt, position, .8, 4, name='Soft natural limestone-marble veining')
    color = _ramp(nt, vein, (.52, .52, .48), (.77, .76, .69), 'Ivory marble vein range', (.25, .7))
    _input(nt, p.inputs['Base Color'], color)
    micro = _noise(nt, position, 110, 1, name='Polished stone microsurface')
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, micro, .13, .22, 'Marble polish variation'))
    _bump(nt, p, micro, .05, .00008)
    p.inputs['Coat Weight'].default_value = .15
    p.inputs['Coat Roughness'].default_value = .13
    _layout(nt)
    return m


def _decorative_marble(name, base, vein, roughness=.18):
    """Public-photo finish: continuous polished stone with irregular fine veins."""
    m, nt, p = _new_material(name, base, roughness)
    position, _ = _position(nt)
    cloud = _noise(nt, position, .72, 3, name='Large continuous stone colour')
    color = _ramp(nt, cloud, tuple(c * .965 for c in base), tuple(c * 1.035 for c in base), 'Stone field tone')
    pattern = _noise(nt, position, 1.65, 4, name='Irregular continuous marble veins')
    distance = _math(nt, 'ABSOLUTE', _math(nt, 'SUBTRACT', pattern, .50))
    mask = _scalar_range(nt, _math(nt, 'DIVIDE', distance, .008), .22, 0, 'Thin marble vein mask')
    _input(nt, p.inputs['Base Color'], _mix(nt, mask, color, (*vein, 1), name='Fine mineral vein tint'))
    grain = _noise(nt, position, 140, 1, name='Polished stone microsurface')
    _input(nt, p.inputs['Roughness'], _scalar_range(nt, grain, roughness - .035, roughness + .035, 'Natural polish roughness'))
    _bump(nt, p, grain, .045, .000055)
    p.inputs['Coat Weight'].default_value = .20
    p.inputs['Coat Roughness'].default_value = .12
    m['sdb_reference_finish'] = 'Owner public-interior photograph: polished golden or charcoal marble; vein placement inferred'
    _layout(nt)
    return m


def _water():
    m = glass_material('SDB Water', transmission=.96, tint=(.97, .99, .985), roughness=.06)
    nt = m.node_tree
    p = nt.nodes.get('Principled BSDF')
    p.inputs['IOR'].default_value = 1.333
    pos, _ = _position(nt)
    ripple = _noise(nt, pos, 4.2, 2, name='Small water ripples / 24 cm')
    _bump(nt, p, ripple, .14, .009)
    # Shallow bowl needs a pale physical basin below this water, not a blue solid.
    m['sdb_glass_geometry'] = 'Clear shallow water surface over a basin floor; 0.05-0.15 m actual depth'
    _layout(nt)
    return m


def build_material_library():
    """Refresh owned materials in place; stable pointers make repeat calls safe."""
    mats = {}
    def add(m):
        mats[m.name] = m
        return m
    add(_stone('SDB Sandstone Cream', (.73, .69, .59), .56))
    add(_stone('SDB Red Granite', (.365, .112, .058), .30, polished=True))
    add(_backed_glass())
    add(glass_material())
    add(_granular('SDB Concrete', (.51, .50, .46), .78, 90, .00075, .075))
    add(_granular('SDB Asphalt', (.044, .047, .046), .88, 130, .0013, .16))
    add(_granular('SDB Road Paint', (.77, .76, .65), .70, 140, .0002, .035))
    add(_stone('SDB Pale Curb', (.61, .60, .54), .71, panels=False))
    for name, base, size in (
        ('SDB Courtyard Paving', (.64, .62, .54), (.9, .6)),
        ('SDB Entry Apron Paving', (.48, .47, .42), (.6, .3)),
        ('SDB Exterior Pale Stone', (.67, .65, .56), (1.2, .8)),
        ('SDB Interior Honed Limestone', (.69, .68, .61), (1.2, 1.2)),
    ):
        add(_stone(name, base, .53, size, .0025))
    add(_stone('SDB Pavement Charcoal Inlay', (.07, .072, .066), .50, (.9, .3), .002))
    add(_stone('SDB Interior Dark Floor Border', (.055, .058, .056), .24, panels=False, polished=True))
    add(_marble())
    add(_decorative_marble('SDB Interior Golden Marble', (.62, .445, .215), (.73, .62, .43), .17))
    add(_decorative_marble('SDB Interior Charcoal Marble', (.042, .047, .047), (.29, .295, .27), .22))
    m, nt, p = _new_material('SDB Interior Ivory Polish', (.77, .755, .695), .25)
    p.inputs['Coat Weight'].default_value = .16
    p.inputs['Coat Roughness'].default_value = .20
    add(m)
    add(_granular('SDB Interior White Plaster', (.77, .77, .74), .76, 175, .00015, .025))
    add(_granular('SDB Interior Fabric', (.21, .23, .22), .90, 440, .00025, .08))
    add(_metal('SDB Dark Metal', (.045, .049, .049), .31, .72))
    add(_metal('SDB Brushed Chrome', (.61, .64, .64), .25))
    add(_metal('SDB Solar Cell', (.012, .022, .037), .22, .30))
    for name in ('SDB Interior Warm Wood', 'SDB Bench Wood', 'SDB Timber Slats'):
        add(_wood(name))
    for name, base in (
        ('SDB Landscape', (.083, .145, .041)), ('SDB Courtyard Grass', (.09, .165, .043)),
        ('SDB Garden mound', (.10, .16, .044)), ('SDB Hedge', (.043, .13, .023)),
        ('SDB Garden shrubs', (.051, .14, .025)), ('SDB Garden mulch', (.080, .047, .024)),
        ('SDB Context Terrain', (.20, .21, .11)), ('SDB Distant Context', (.40, .39, .34)),
        ('SDB Tree Bark', (.115, .062, .030)),
    ):
        add(_granular(name, base, .89, 45 if 'Bark' not in name else 24, .0013, .18))
    for name, base in (
        ('SDB Tree Leaves Deep', (.024, .096, .021)),
        ('SDB Tree Leaves Mid', (.045, .16, .035)),
        ('SDB Tree Leaves Sun', (.11, .24, .055)),
        ('SDB Palm Leaves Deep', (.027, .11, .031)),
        ('SDB Palm Leaves Mid', (.045, .18, .051)),
        ('SDB Palm Leaves Sun', (.095, .25, .072)),
        ('SDB Interior Plant Leaves', (.045, .13, .035)),
    ):
        add(_leaf(name, base))
    add(_granular('SDB Interior Planting Soil', (.055, .032, .017), .95, 36, .002, .18))
    add(_granular('SDB Interior Equipment Black', (.018, .022, .022), .46, 220, .00005, .04))
    add(_water())
    m, nt, p = _new_material('SDB Fixture Warm Emission', (.78, .70, .53), .34)
    p.inputs['Emission Color'].default_value = (1, .74, .44, 1)
    p.inputs['Emission Strength'].default_value = 2.0
    m['sdb_day_emission'] = 2.0
    m['sdb_dusk_emission'] = 8.0
    add(m)
    return mats


def get_material(name):
    """Get an owned material; builds only if library not created yet."""
    m = bpy.data.materials.get(name)
    if m and m.get('sdb_polish_version') == VERSION:
        return m
    mats = build_material_library()
    if name not in mats:
        raise KeyError('Unknown polish material: ' + name)
    return mats[name]


def _set_safe(obj, name, value):
    if hasattr(obj, name):
        try:
            setattr(obj, name, value)
            return True
        except (TypeError, ValueError):
            pass
    return False


def configure_cycles(scene):
    """Metal when actually reported by Cycles; CPU is a valid fallback."""
    scene.render.engine = 'CYCLES'
    c = scene.cycles
    c.max_bounces = 8
    c.diffuse_bounces = 4
    c.glossy_bounces = 4
    c.transmission_bounces = 6
    c.transparent_max_bounces = 8
    c.use_denoising = True
    c.samples = max(c.samples, 96)
    _set_safe(c, 'use_adaptive_sampling', True)
    _set_safe(c, 'adaptive_threshold', .025)
    _set_safe(c, 'sample_clamp_indirect', 6.0)
    # Refractive caustics are unnecessary in this architectural still.
    _set_safe(c, 'caustics_reflective', False)
    _set_safe(c, 'caustics_refractive', False)
    device = 'CPU'
    try:
        pref = bpy.context.preferences.addons['cycles'].preferences
        types = {v.identifier for v in pref.bl_rna.properties['compute_device_type'].enum_items}
        if hasattr(pref, 'get_device_types'):
            types.update(item[0] for item in pref.get_device_types(bpy.context))
        if 'METAL' in types or getattr(pref, 'compute_device_type', '') == 'METAL':
            pref.compute_device_type = 'METAL'
            pref.get_devices()
            metal = [d for d in pref.devices if d.type == 'METAL']
            if metal:
                for d in pref.devices:
                    d.use = d.type == 'METAL'
                device = 'GPU'
    except (KeyError, AttributeError, TypeError, ValueError, RuntimeError):
        pass
    c.device = device
    scene.view_settings.view_transform = 'AgX'
    try:
        looks = {v.identifier for v in scene.view_settings.bl_rna.properties['look'].enum_items}
        for name in ('AgX - Medium High Contrast', 'Medium High Contrast', 'None'):
            if name in looks:
                scene.view_settings.look = name
                break
    except (KeyError, AttributeError, TypeError, ValueError):
        pass
    scene.view_settings.gamma = 1
    scene.render.film_transparent = False
    return device


def _world(scene):
    world = bpy.data.worlds.get('SDB Unified Architectural Sky') or bpy.data.worlds.new('SDB Unified Architectural Sky')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.clear()
    world['sdb_polish_version'] = VERSION
    return world, world.node_tree


def _sun(scene, elevation=38.0, azimuth=125.0, energy=2.6):
    # Disable inherited suns so there is precisely one direct solar emitter.
    for obj in scene.objects:
        if obj.type == 'LIGHT' and obj.data.type == 'SUN':
            obj.hide_render = True
    name = 'SDB Polish | sole sun'
    obj = bpy.data.objects.get(name)
    if obj is None:
        data = bpy.data.lights.new(name, 'SUN')
        obj = bpy.data.objects.new(name, data)
        coll = bpy.data.collections.get('Lighting') or scene.collection
        coll.objects.link(obj)
    obj.hide_render = energy <= 0
    obj.data.energy = energy
    obj.data.color = (1.0, .94, .84)
    obj.data.angle = math.radians(.8)
    direction = Vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)), math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)), math.sin(math.radians(elevation))))
    obj.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
    obj['sdb_sun_elevation_deg'] = elevation
    obj['sdb_sun_azimuth_deg'] = azimuth
    return obj


def _fixtures(scene, dusk=False):
    for obj in scene.objects:
        if obj.type != 'LIGHT' or not obj.get('sdb_fixture'):
            continue
        if 'sdb_day_energy' not in obj:
            obj['sdb_day_energy'] = obj.data.energy
        if 'sdb_dusk_energy' not in obj:
            obj['sdb_dusk_energy'] = obj['sdb_day_energy'] * 1.7
        obj.data.energy = obj['sdb_dusk_energy' if dusk else 'sdb_day_energy']
    for mat in bpy.data.materials:
        if not mat.use_nodes or 'sdb_day_emission' not in mat:
            continue
        p = mat.node_tree.nodes.get('Principled BSDF')
        if p and 'Emission Strength' in p.inputs:
            p.inputs['Emission Strength'].default_value = mat['sdb_dusk_emission' if dusk else 'sdb_day_emission']


def configure_daylight(scene, *, sky_strength=.27, sun_energy=3.0, aerosol=.22, exposure=-.35):
    """Clear warm 38 degree sun; one sky for camera, glass and illumination."""
    configure_cycles(scene)
    world, nt = _world(scene)
    sky = _node(nt, 'ShaderNodeTexSky', 'Physical atmosphere: unified for every ray', (-360, 80))
    types = {v.identifier for v in sky.bl_rna.properties['sky_type'].enum_items}
    for kind in ('NISHITA', 'MULTIPLE_SCATTERING', 'SINGLE_SCATTERING'):
        if kind in types:
            sky.sky_type = kind
            break
    _set_safe(sky, 'sun_elevation', math.radians(38))
    _set_safe(sky, 'sun_rotation', math.radians(125))
    _set_safe(sky, 'sun_direction', Vector((math.cos(math.radians(125)) * math.cos(math.radians(38)), math.sin(math.radians(125)) * math.cos(math.radians(38)), math.sin(math.radians(38)))))
    # Analytic sky emits the atmosphere; the one Sun supplies the solar disk.
    # This avoids duplicated sun energy and keeps environment reflections exact.
    _set_safe(sky, 'sun_disc', False)
    _set_safe(sky, 'sun_intensity', 1.0)
    _set_safe(sky, 'air_density', 1.0)
    _set_safe(sky, 'dust_density', aerosol)
    _set_safe(sky, 'aerosol_density', aerosol)
    _set_safe(sky, 'ozone_density', 1.0)
    bg = _node(nt, 'ShaderNodeBackground', 'Daylight sky strength', (-80, 80))
    bg.inputs['Strength'].default_value = sky_strength
    out = _node(nt, 'ShaderNodeOutputWorld', 'World Output', (200, 80))
    nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    _sun(scene, 38, 125, sun_energy)
    _fixtures(scene, False)
    scene.view_settings.exposure = exposure
    scene['sdb_lighting_recipe'] = 'Daylight: unified atmosphere + single soft .8 degree sun; no camera-ray background replacement'
    return {'sky': sky.sky_type, 'sky_strength': sky_strength, 'aerosol': aerosol, 'sun_energy': sun_energy, 'exposure': exposure}


def configure_dusk(scene):
    """Blue-hour still: dim unified sky and warm architectural practicals."""
    configure_cycles(scene)
    world, nt = _world(scene)
    tex = _node(nt, 'ShaderNodeTexCoord', 'Environment direction', (-680, 80))
    sep = _node(nt, 'ShaderNodeSeparateXYZ', 'Sky elevation', (-480, 80))
    nt.links.new(tex.outputs['Normal'], sep.inputs[0])
    # World texture normals point inward: negative Z is the upper hemisphere.
    height = _math(nt, 'MULTIPLY', sep.outputs['Z'], -1)
    fac = _scalar_range(nt, height, 0, 1, 'Horizon to zenith')
    color = _ramp(nt, fac, (.095, .111, .150), (.012, .025, .064), 'Blue-hour all-ray environment')
    bg = _node(nt, 'ShaderNodeBackground', 'Twilight strength', (-80, 80))
    bg.inputs['Strength'].default_value = .42
    nt.links.new(color, bg.inputs['Color'])
    out = _node(nt, 'ShaderNodeOutputWorld', 'World Output', (200, 80))
    nt.links.new(bg.outputs[0], out.inputs['Surface'])
    _sun(scene, -4, 125, 0)
    _fixtures(scene, True)
    scene.view_settings.exposure = 2.7
    scene['sdb_lighting_recipe'] = 'Blue-hour artist still: uniform all-ray twilight gradient, warm actual fixture lights; no bloom'
    return {'sun_energy': 0, 'exposure': 2.7}


def refine_site_materials():
    """Polish the site agent's palette while preserving its paving/water graphs."""
    prefix = 'Polish Site | '
    leaf_names = {'Leaf shadow', 'Leaf olive', 'Leaf green', 'Leaf new growth', 'Palm blue green', 'Mown grass blade'}
    count = 0
    for mat in list(bpy.data.materials):
        if not mat.name.startswith(prefix) or not mat.use_nodes:
            continue
        key = mat.name[len(prefix):]
        base = tuple(mat.diffuse_color[:3])
        nt = mat.node_tree
        p = nt.nodes.get('Principled BSDF')
        if not p:
            continue
        if key in leaf_names:
            _leaf(mat.name, base)
        elif key in {'Paving pale stone', 'Paving basalt'}:
            # Preserve real-scale staggered site paving; joints must recess.
            for node in nt.nodes:
                if node.bl_idname == 'ShaderNodeBump':
                    node.invert = True
                    node.inputs['Distance'].default_value = .0015
        elif key=='Turf':
            _turf(mat.name)
        elif key=='Mulch':
            _photographic_ground(mat.name)
        elif key in {'Water', 'Bark', 'Palm bark'}:
            # Existing texture detail is retained but uses metres rather than
            # automatically normalised Generated coordinates on linked sources.
            geo = nt.nodes.get('SDB Polish metric coord') or _node(nt, 'ShaderNodeNewGeometry', 'SDB Polish metric coord')
            for node in nt.nodes:
                if node.bl_idname == 'ShaderNodeTexNoise':
                    nt.links.new(geo.outputs['Position'], node.inputs['Vector'])
            if key == 'Turf':
                for node in nt.nodes:
                    if node.bl_idname == 'ShaderNodeBump':
                        node.inputs['Distance'].default_value = .0025
            if key == 'Water':
                p.inputs['IOR'].default_value = 1.333
                p.inputs['Metallic'].default_value = 0
                p.inputs['Roughness'].default_value = .045
                # Basin geometry already supplies water colour and depth.
                p.inputs['Base Color'].default_value = (.93, .98, .965, 1)
        elif key == 'Bench teak':
            _wood(mat.name)
        elif key in {'Shirt cream', 'Shirt grey', 'Trousers', 'Shoe', 'Tyre', 'Dry grass', 'Edging stone', 'Basin interior', 'Marker white'}:
            roughness = float(p.inputs['Roughness'].default_value)
            _granular(mat.name, base, roughness, 280 if key.startswith('Shirt') or key == 'Trousers' else 130, .00015, .05)
        elif key == 'Vehicle glass':
            p.inputs['Metallic'].default_value = 0
            p.inputs['IOR'].default_value = 1.52
            p.inputs['Roughness'].default_value = .065
            p.inputs['Coat Weight'].default_value = .18
            p.inputs['Coat Roughness'].default_value = .035
            mat['sdb_glass_geometry'] = 'Opaque interior-backed car-window proxy, neutral dielectric reflection'
        elif key.startswith('Vehicle '):
            p.inputs['Coat Weight'].default_value = .65
            p.inputs['Coat Roughness'].default_value = .09
        elif key == 'Skin':
            if 'Subsurface Weight' in p.inputs:
                p.inputs['Subsurface Weight'].default_value = .06
            if 'Subsurface Scale' in p.inputs:
                p.inputs['Subsurface Scale'].default_value = .015
        elif key in {'Headlight', 'Tail light'}:
            p.inputs['Metallic'].default_value = 0
            p.inputs['Coat Weight'].default_value = .35
            p.inputs['Coat Roughness'].default_value = .08
        count += 1
    return count


def exposure_for_camera(camera, *, dusk=False):
    """Starting photographic exposures for different still framings."""
    name = camera.name if hasattr(camera, 'name') else str(camera)
    if dusk:
        return 2.7
    if 'Courtyard' in name:
        return .20
    if 'Parking Ramp' in name:
        return .20
    if 'Parking' in name or 'Basement' in name:
        return 3.5
    if 'Office' in name or 'Atrium' in name:
        return .05
    return -.35


def _reference_finish_assignments(scene, mats):
    count = 0
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        material = None
        if 'Lobby | 1.2m honed stone tile field' in obj.name:
            material = mats['SDB Interior Polished Marble']
        elif 'Lobby | smooth white flared column' in obj.name or 'Lobby | linked flared column' in obj.name:
            material = mats['SDB Interior Ivory Polish']
        if material:
            for slot in obj.material_slots:
                slot.link = 'OBJECT'
                slot.material = material
            count += 1
    return count


def apply(scene):
    """Idempotently update material nodes, obvious solar assignments and daylight."""
    mats = build_material_library()
    site_materials = refine_site_materials()
    reference_finishes = _reference_finish_assignments(scene, mats)
    solar_count = 0
    for obj in scene.objects:
        if obj.type == 'MESH' and 'Solar Panel' in obj.name:
            # Shared meshes may share their glass slot with other objects.
            # Object-linked override avoids corrupting a whole linked library.
            for slot in obj.material_slots:
                slot.link = 'OBJECT'
                slot.material = mats['SDB Solar Cell']
            solar_count += 1
    light = configure_daylight(scene)
    scene['sdb_material_polish_version'] = VERSION
    return {'materials': len(mats), 'site_materials': site_materials, 'reference_finishes': reference_finishes, 'solar_objects': solar_count, 'lighting': light}
