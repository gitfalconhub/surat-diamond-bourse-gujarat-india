# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference-led architectural polish, applied to an already opened SDB scene.

No loading, saving, rendering or operators. Geometry is in metres / world Z-up.
The public photos determine the visual language; detailed dimensions and office
fit-out are reconstruction assumptions, not an as-built BIM or code assessment.
"""
from __future__ import annotations

import json
import math
import random
import bpy
from mathutils import Matrix, Vector
from sdb_utils import MeshBatch, ensure_collection, material, polygon_prism, polyline_curve, camera
from sdb_architecture import north_spine_y, PARAMS

ROOT = 'Polish | Public interiors'
GROUND = .30
GALLERY = 6.48  # original 6.4 datum + original .08 floor finish
PREFIX = 'PI | '


def _clear(coll):
    for sub in list(coll.children):
        _clear(sub)
        bpy.data.collections.remove(sub)
    for ob in list(coll.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data and data.users == 0:
            if isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve): bpy.data.curves.remove(data)
            elif isinstance(data, bpy.types.Camera): bpy.data.cameras.remove(data)
            elif isinstance(data, bpy.types.Light): bpy.data.lights.remove(data)


def _mats():
    try:
        from polish_materials import build_material_library
        build_material_library()
    except ImportError:
        pass
    specs = {
        'stone': ('SDB Interior Honed Limestone', (.67,.63,.55,1), .42, 0),
        'white': ('SDB Interior White Plaster', (.82,.81,.76,1), .62, 0),
        'marble': ('SDB Interior Polished Marble', (.48,.46,.42,1), .22, 0),
        'border': ('SDB Interior Dark Floor Border', (.12,.13,.13,1), .28, 0),
        'wood': ('SDB Interior Warm Wood', (.24,.12,.06,1), .42, 0),
        'metal': ('SDB Brushed Chrome', (.36,.38,.38,1), .29, .9),
        'fabric': ('SDB Interior Fabric', (.34,.30,.24,1), .88, 0),
        'glass': ('SDB Clear Architectural Glass', (.82,.9,.94,1), .06, 0),
        'emission': ('SDB Fixture Warm Emission', (.94,.80,.59,1), .28, 0),
        'soil': ('SDB Interior Planting Soil', (.055,.032,.017,1), 1, 0),
        'leaf': ('SDB Interior Plant Leaves', (.045,.13,.035,1), .8, 0),
        'red': ('SDB Red Granite', (.3,.085,.052,1), .45, 0),
        'black': ('SDB Interior Equipment Black', (.018,.022,.022,1), .45, 0),
        'golden': ('SDB Interior Golden Marble', (.48,.33,.14,1), .18, 0),
        'charcoal': ('SDB Interior Charcoal Marble', (.055,.06,.063,1), .24, 0),
        'ivory': ('SDB Interior Ivory Polish', (.75,.69,.55,1), .20, 0),
    }
    out = {}
    for key, (name, col, rough, metal) in specs.items():
        m = bpy.data.materials.get(name)
        if m is None: m = material(name, base_color=col, roughness=rough, metallic=metal)
        out[key] = m
    p = out['glass'].node_tree.nodes.get('Principled BSDF')
    if p:
        if 'Transmission Weight' in p.inputs: p.inputs['Transmission Weight'].default_value = 1
        p.inputs['IOR'].default_value = 1.46
    p = out['emission'].node_tree.nodes.get('Principled BSDF')
    if p:
        if 'Emission Color' in p.inputs:
            p.inputs['Emission Color'].default_value = (1,.82,.58,1)
            p.inputs['Emission Strength'].default_value = 3
    return out


def _tag(ob, scope='reference-based public interior'):
    ob['sdb_component'] = 'public_interior_polish'
    ob['reconstruction_scope'] = scope
    return ob


def _bevel(ob, width=.015, segments=3):
    if width > 0:
        mod = ob.modifiers.new('Small construction edge radius', 'BEVEL')
        mod.width = width; mod.segments = segments
    return ob


def _box(name, lo, hi, coll, mat, bevel=0):
    ob = MeshBatch(PREFIX+name, coll, mat).add_box(lo,hi).commit()
    return _tag(_bevel(ob, bevel))


def _mesh(name, verts, faces, coll, mat, smooth=False):
    me = bpy.data.meshes.new(PREFIX+name+' Mesh'); me.from_pydata(verts, [], faces); me.update()
    ob = bpy.data.objects.new(PREFIX+name, me); coll.objects.link(ob); me.materials.append(mat)
    for p in me.polygons: p.use_smooth = smooth
    return _tag(ob)


def _tube(name, a, b, radius, coll, mat, sides=12):
    a,b = Vector(a),Vector(b); direction = (b-a).normalized()
    tangent = direction.cross(Vector((0,0,1)))
    if tangent.length < .01: tangent = Vector((1,0,0))
    tangent.normalize(); normal = direction.cross(tangent)
    vs = [tuple(c+radius*(tangent*math.cos(i*2*math.pi/sides)+normal*math.sin(i*2*math.pi/sides))) for c in (a,b) for i in range(sides)]
    fs = [tuple(reversed(range(sides))),tuple(range(sides,2*sides))]
    fs += [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    return _mesh(name,vs,fs,coll,mat,True)


def _lathe(name, x,y, profile, coll,mat,segments=48, faceted=False):
    vs = [(x+r*math.cos(i*2*math.pi/segments),y+r*math.sin(i*2*math.pi/segments),z) for r,z in profile for i in range(segments)]
    fs = [tuple(reversed(range(segments))),tuple(range((len(profile)-1)*segments,len(profile)*segments))]
    fs += [(j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i) for j in range(len(profile)-1) for i in range(segments)]
    return _mesh(name,vs,fs,coll,mat,not faceted)


def _ring(name, cx,cy, rx,ry, width, z,thick,coll,mat,segments=64):
    vs=[]
    for zz in (z,z+thick):
        for a,b in ((rx,ry),(rx-width,ry-width)):
            vs += [(cx+a*math.cos(i*2*math.pi/segments),cy+b*math.sin(i*2*math.pi/segments),zz) for i in range(segments)]
    fs=[];n=segments
    for i in range(n):
        j=(i+1)%n;fs += [(i,j,j+n,i+n),(i+2*n,i+3*n,j+3*n,j+2*n),(i,j,j+2*n,i+2*n),(i+n,i+3*n,j+3*n,j+n)]
    return _mesh(name,vs,fs,coll,mat)


def _source_boxes(ob):
    """Read the original disjoint eight-vertex MeshBatch boxes in world space.

    Original mesh is retained for repeatability, and to permit artist reversal.
    Root parenting/matrix_world are untouched; output vertices return to local.
    """
    key = ob.get('polish_source_mesh')
    source = bpy.data.meshes.get(key) if key else None
    if source is None:
        source = ob.data
        source.use_fake_user = True
        ob['polish_source_mesh'] = source.name
    if len(source.vertices)%8:
        raise ValueError('Expected MeshBatch box geometry: '+ob.name)
    matrix = ob.matrix_world
    boxes=[]
    for n in range(0,len(source.vertices),8):
        points=[matrix@source.vertices[i].co for i in range(n,n+8)]
        boxes.append((tuple(min(p[a] for p in points) for a in range(3)),tuple(max(p[a] for p in points) for a in range(3))))
    return boxes


def _difference(box, cut):
    lo,hi = box;cl,ch = cut
    il = [max(lo[i],cl[i]) for i in range(3)]; ih = [min(hi[i],ch[i]) for i in range(3)]
    if any(ih[i]<=il[i]+1e-6 for i in range(3)): return [box]
    parts=[]
    # Disjoint six-box partition: X flanks, Y flanks within X, Z within XY.
    if lo[0]<il[0]: parts.append((lo,(il[0],hi[1],hi[2])))
    if ih[0]<hi[0]: parts.append(((ih[0],lo[1],lo[2]),hi))
    if lo[1]<il[1]: parts.append(((il[0],lo[1],lo[2]),(ih[0],il[1],hi[2])))
    if ih[1]<hi[1]: parts.append(((il[0],ih[1],lo[2]),(ih[0],hi[1],hi[2])))
    if lo[2]<il[2]: parts.append(((il[0],il[1],lo[2]),(ih[0],ih[1],il[2])))
    if ih[2]<hi[2]: parts.append(((il[0],il[1],ih[2]),(ih[0],ih[1],hi[2])))
    return parts


def _patch(ob, transform):
    if ob is None: return
    boxes = transform(_source_boxes(ob))
    inv = ob.matrix_world.inverted()
    vs=[];fs=[]
    for lo,hi in boxes:
        x0,y0,z0=lo;x1,y1,z1=hi;n=len(vs)
        corners=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
        vs += [tuple(inv@Vector(v)) for v in corners]
        fs += [tuple(n+i for i in f) for f in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))]
    old=ob.data; name=PREFIX+'Corrected '+ob.name
    me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update()
    for mat in old.materials: me.materials.append(mat)
    ob.data=me
    if old.users == 0 and old.name != ob.get('polish_source_mesh'): bpy.data.meshes.remove(old)
    ob['polish_correction']='reversible; original mesh in polish_source_mesh'


def correct_junctions(scene):
    """Keep outward terminal screens; remove screens invading the spine route.

    Bridge tops align with corresponding gallery surfaces, not 0.6 m above.
    Near-end cream caps open a 4.8 m central connection without moving roots.
    """
    for spec in PARAMS['towers']:
        x=spec['x']; north=spec['side']=='north'
        near = north_spine_y(x)-1.5 if north else -6.5
        face = north_spine_y(x)+1.5 if north else -9.5
        name=spec['name']
        def screens(boxes):
            return [b for b in boxes if abs((b[0][1]+b[1][1])/2-near)>.45]
        _patch(bpy.data.objects.get(name+' | Perforated Red Screens'), screens)
        def caps(boxes):
            out=[]
            for lo,hi in boxes:
                if abs((lo[1]+hi[1])/2-face)<1.7:
                    out += _difference((lo,hi),((x-2.4,face-2,6.39),(x+2.4,face+2,71)))
                else:out.append((lo,hi))
            return out
        _patch(bpy.data.objects.get(name+' | Cream End Caps'),caps)
        def bridges(boxes):
            out=[]
            for lo,hi in boxes:
                if min(lo[1],hi[1])-1e-4<=near<=max(lo[1],hi[1])+1e-4:continue
                out.append(((lo[0],lo[1],lo[2]-.52),(hi[0],hi[1],hi[2]-.52)))
            return out
        _patch(bpy.data.objects.get(name+' | Screen Bridges'),bridges)
    # Local lift shaft openings: keep all gallery routes except shaft footprints.
    def lift_holes(boxes):
        out=[]
        cuts=[((21.8,-8.2,6.15),(29,-4.5,10.6))]
        for b in boxes:
            pieces=[b]
            for cut in cuts:pieces=[p for q in pieces for p in _difference(q,cut)]
            out+=pieces
        return out
    _patch(bpy.data.objects.get('Spine | Continuous galleries and connecting bridges'),lift_holes)
    scene['Spine junction repair']='Inward tower screens removed; near cream caps have 4.8m openings; outer screen bridge tops align gallery datums.'


def _floor_tiles(coll,m):
    # 1.2 m honed tiles in a 96 m connected hall. Open voids above remain open.
    tiles=MeshBatch(PREFIX+'Lobby | 1.2m honed stone tile field',coll,m['stone'])
    for i in range(80):
        x=-48+i*1.2
        for j in range(14):
            y=-8.4+j*1.2
            if y+1.2 <= north_spine_y(x+.6)-.52:
                for lo,hi in _difference(((x+.006,y+.006,.20),(x+1.194,y+1.194,GROUND)),((21.8,-8.2,.05),(29,-4.5,.35))):
                    tiles.add_box(lo,hi)
    _tag(tiles.commit())
    stripes=MeshBatch(PREFIX+'Lobby | dark stone border and transverse bands',coll,m['border'])
    for y in (-7.75,7.05):
        for lo,hi in _difference(((-48,y,.30),(48,y+.23,.314)),((21.8,-8.2,.05),(29,-4.5,.35))):stripes.add_box(lo,hi)
    for x in range(-48,49,12):
        for lo,hi in _difference(((x,-7.52,.30),(x+.35,7.05,.314)),((21.8,-8.2,.05),(29,-4.5,.35))):stripes.add_box(lo,hi)
    _tag(stripes.commit())
    # Fixed route underneath the whole floor so tile seams never become holes.
    substrate=MeshBatch(PREFIX+'Lobby | continuous floor substrate',coll,m['stone'])
    for lo,hi in _difference(((-48,-8.4,.10),(48,7.5,.2)),((21.8,-8.2,.05),(29,-4.5,.35))):substrate.add_box(lo,hi)
    _tag(substrate.commit())


def _column_seating(coll,m):
    source=None; benchsource=None
    profile=[(.98,.31),(.86,.48),(.68,.7),(.50,1.0),(.43,1.55),(.43,3.98),(.49,4.37),(.70,4.74),(1.0,5.08),(1.46,5.37),(1.92,5.59),(2.13,5.67)]
    for x in (-44,-32,-20,-8,4,16,28,40):
        for y in (-5.65,5.5):
            # Stair and lift shafts remain outside column/seating envelopes.
            if x==28 and y<0:continue
            if x==40:continue
            if x in (-20,-8,4,16) and y>0:
                _lathe('Planted corridor | polished cream column',x,y,[(.51,.3),(.51,5.7)],coll,m['ivory'],48)
                continue
            if source is None:
                source=_lathe('Lobby | smooth white flared column',0,0,profile,coll,m['white'],64)
                source.location=(x,y,0)
            else:
                ob=bpy.data.objects.new(PREFIX+'Lobby | linked flared column',source.data);coll.objects.link(ob);ob.location=(x,y,0);_tag(ob)
            # Broad elliptical seating basin follows the photographed integral benches.
            if benchsource is None:
                benchsource=_ring('Lobby | integral white elliptical seat',0,0,2.60,1.34,.63,.34,.40,coll,m['white'])
                _bevel(benchsource,.045,4);benchsource.location=(x,y,0)
            else:
                ob=bpy.data.objects.new(PREFIX+'Lobby | linked elliptical seat',benchsource.data);coll.objects.link(ob);ob.location=(x,y,0);_bevel(ob,.045,4);_tag(ob)
            _ring('Lobby | column indirect cove',x,y,2.20,2.20,.065,5.67,.025,coll,m['emission'],48)['sdb_fixture']=True


def _ceiling_lights(coll,m):
    # Separate panels permit real voids over stairs and atrium; no ceiling through them.
    panels=MeshBatch(PREFIX+'Lobby | suspended ceiling panels',coll,m['white'])
    for x in range(-48,48,3):
        for y in (-8.3,-5.3,-2.3,.7,3.7):
            if 32<x<46 and -4<y<4: continue
            panels.add_box((x+.012,y+.012,5.72),(x+2.988,min(y+2.99,7.35),5.84))
    _tag(panels.commit())
    vents=MeshBatch(PREFIX+'Lobby | recessed linear AC slots',coll,m['black'])
    fixtures=MeshBatch(PREFIX+'Lobby | recessed downlight trim rings',coll,m['metal'])
    emit=MeshBatch(PREFIX+'Lobby | downlight luminous apertures',coll,m['emission'])
    for x in range(-45,46,6):
        for y in (-3,0,3):
            if 32<x<46:continue
            fixtures.add_box((x-.11,y-.11,5.67),(x+.11,y+.11,5.72))
            emit.add_box((x-.085,y-.085,5.66),(x+.085,y+.085,5.673))
        for y in (-3.8,3.8):vents.add_box((x-1.45,y-.035,5.695),(x+1.45,y+.035,5.72))
    _tag(vents.commit());_tag(fixtures.commit());_tag(emit.commit())['sdb_fixture']=True
    # A modest number of physical light sources, separate from fixture geometry.
    for x in (-40,-20,0,20,40):
        data=bpy.data.lights.new(PREFIX+'Lobby indirect area','AREA');data.energy=900;data.shape='RECTANGLE';data.size=8;data.size_y=5
        ob=bpy.data.objects.new(PREFIX+'Lobby indirect area',data);coll.objects.link(ob);ob.location=(x,0,5.61);ob['sdb_fixture']=True


def _rail(name,points,coll,m):
    _tag(polyline_curve(PREFIX+name+' | round top rail',points,collection=coll,mat=m['metal'],bevel_depth=.025))
    for a,b in zip(points[:-1],points[1:]):
        va,vb=Vector(a),Vector(b);length=(vb-va).length
        for k in range(max(1,int(length/1.4))+1):
            t=k/max(1,int(length/1.4));p=va.lerp(vb,t)
            _tube(name+' | baluster',(p.x,p.y,p.z-1.08),p,.018,coll,m['metal'])
        _tag(polyline_curve(PREFIX+name+' | intermediate rail',[(a[0],a[1],a[2]-.5),(b[0],b[1],b[2]-.5)],collection=coll,mat=m['metal'],bevel_depth=.012))


def _stairs(coll,m):
    riser=(GALLERY-GROUND)/36; tread=.30;run=18*tread
    steps=MeshBatch(PREFIX+'Stair | 36 stone risers 171.7mm and 300mm treads',coll,m['stone'])
    nosings=MeshBatch(PREFIX+'Stair | anti slip inset strips',coll,m['border'])
    # Each riser/tread is a thin finish, with a continuous sloping structural waist.
    for i in range(18):
        x=35+i*tread;z=GROUND+(i+1)*riser
        steps.add_box((x,-2.8,z-.055),(x+tread,-.8,z))
        steps.add_box((x,-2.8,z-riser),(x+.045,-.8,z))
        nosings.add_box((x+.035,-2.72,z),(x+.075,-.88,z+.003))
        xx=40.4-(i+1)*tread;zz=GROUND+18*riser+(i+1)*riser
        steps.add_box((xx,.8,zz-.055),(xx+tread,2.8,zz))
        steps.add_box((xx+tread-.045,.8,zz-riser),(xx+tread,2.8,zz))
        nosings.add_box((xx+tread-.075,.88,zz),(xx+tread-.035,2.72,zz+.003))
    _tag(_bevel(steps.commit(),.008,2));_tag(nosings.commit())
    mid=GROUND+18*riser
    _box('Stair | 2m deep intermediate turning landing',(40.4,-2.8,mid-.20),(42.4,2.8,mid),coll,m['stone'],.015)
    _box('Stair | upper arrival landing',(33,.8,GALLERY-.22),(35.3,6.1,GALLERY),coll,m['stone'],.012)
    _box('Stair | lower approach',(32,-3.1,.2),(35,-.5,GROUND),coll,m['stone'],.012)
    for name,a,b,y0,y1 in [('lower',(35,.30),(40.4,mid),-2.8,-.8),('upper',(35,GALLERY),(40.4,mid),.8,2.8)]:
        x0,z0=a;x1,z1=b
        vs=[(x0,y0,z0-.24),(x1,y0,z1-.24),(x1,y1,z1-.24),(x0,y1,z0-.24),(x0,y0,z0-.08),(x1,y0,z1-.08),(x1,y1,z1-.08),(x0,y1,z0-.08)]
        _mesh('Stair | '+name+' structural waist',vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],coll,m['white'])
    for y in (-2.8,-.8):_rail('Stair lower',[(35,y,GROUND+1.1),(40.4,y,mid+1.1)],coll,m)
    for y in (.8,2.8):_rail('Stair upper',[(40.4,y,mid+1.1),(35,y,GALLERY+1.1)],coll,m)
    _rail('Stair turning landing',[(40.4,-2.8,mid+1.1),(42.4,-2.8,mid+1.1),(42.4,2.8,mid+1.1),(40.4,2.8,mid+1.1)],coll,m)
    _rail('Stair upper landing',[(33,.8,GALLERY+1.1),(33,4.2,GALLERY+1.1)],coll,m)
    coll['route_ground_to_gallery']='36 risers, 18+18, 0.1716667m rise, 0.30m tread, 2m clear flight, 2m intermediate landing; public recon assumption'
    coll['minimum_modelled_headroom_m']=2.48


def _lift(coll,m):
    # Two shafts outside the hall centreline. Front faces north into the public hall.
    wall=MeshBatch(PREFIX+'Lift lobby | shaft enclosure with actual door openings',coll,m['white'])
    for x in (22,25.6):
        wall.add_box((x,-8.05,.30),(x+.15,-4.5,10.42))
        wall.add_box((x+2.95,-8.05,.30),(x+3.1,-4.5,10.42))
        wall.add_box((x,-8.2,.30),(x+3.1,-8.05,10.42))
        wall.add_box((x,-4.66,.3),(x+.65,-4.5,10.42));wall.add_box((x+2.45,-4.66,.3),(x+3.1,-4.5,10.42))
        wall.add_box((x+.65,-4.66,2.7),(x+2.45,-4.5,6.48));wall.add_box((x+.65,-4.66,8.88),(x+2.45,-4.5,10.42))
    _tag(wall.commit())
    for x in (22,25.6):
        for z in (.30,6.48):
            _box('Lift | stone threshold',(x+.55,-4.8,z-.025),(x+2.55,-4.38,z+.015),coll,m['stone'],.01)
            for xx in (x+.56,x+2.46):_box('Lift | stainless door jamb',(xx,-4.48,z),(xx+.08,-4.37,z+2.45),coll,m['metal'],.012)
            _box('Lift | stainless head',(x+.56,-4.48,z+2.4),(x+2.54,-4.37,z+2.48),coll,m['metal'],.01)
            if x>25 or z>1:
                for off in (.68,1.56):_box('Lift | two leaf closed landing doors',(x+off,-4.54,z+.035),(x+off+.865,-4.48,z+2.38),coll,m['metal'],.008)
            # Actual push button and slim hall position screen; no invented wayfinding text.
            _box('Lift | call station',(x+2.63,-4.45,z+1.0),(x+2.73,-4.40,z+1.26),coll,m['metal'],.01)
            _tube('Lift | call button',(x+2.68,-4.395,z+1.13),(x+2.68,-4.375,z+1.13),.022,coll,m['emission'])
            _box('Lift | indicator glass',(x+1.25,-4.43,z+2.53),(x+1.85,-4.40,z+2.68),coll,m['black'],.012)
    # Ground cab of west shaft open, doors visibly pocketed aside: usable visual entry.
    x=22
    _box('Lift cab | floor',(x+.22,-7.90,.22),(x+2.88,-4.75,.30),coll,m['border'])
    _box('Lift cab | rear brushed wall',(x+.22,-7.94,.30),(x+2.88,-7.90,2.72),coll,m['metal'])
    for xx in (x+.22,x+2.84):_box('Lift cab | side brushed wall',(xx,-7.9,.3),(xx+.04,-4.76,2.72),coll,m['metal'])
    _box('Lift cab | rear mirror',(x+.42,-7.891,.92),(x+2.68,-7.875,2.4),coll,m['glass'])
    _box('Lift cab | ceiling',(x+.22,-7.9,2.72),(x+2.88,-4.76,2.80),coll,m['white'])
    _box('Lift cab | ceiling diffuser',(x+.62,-7.5,2.705),(x+2.48,-5.2,2.72),coll,m['emission'])['sdb_fixture']=True
    _tube('Lift cab | rear handrail',(x+.45,-7.80,1.22),(x+2.64,-7.80,1.22),.025,coll,m['metal'])
    for xx in (x+.17,x+2.48):_box('Lift cab | pocketed door leaves',(xx,-4.84,.34),(xx+.4,-4.78,2.68),coll,m['metal'])
    _box('Lift cab | button panel',(x+2.80,-5.1,.95),(x+2.84,-4.9,1.65),coll,m['metal'])
    for z in (1.08,1.2,1.32,1.44):_tube('Lift cab | floor selection',(x+2.795,-5.0,z),(x+2.78,-5.0,z),.022,coll,m['black'])
    _box('Lift lobby | gallery approach landing',(20.5,-4.50,GALLERY-.18),(30,-2.4,GALLERY),coll,m['stone'],.008)
    _rail('Lift lobby gallery edge',[(20.5,-2.4,GALLERY+1.1),(30,-2.4,GALLERY+1.1)],coll,m)
    coll['route']='Ground hall -> west open cab at (23.55,-4.5,.3); corresponding landing at6.48. Cab static at ground.'



def _owner_lift_finishes(coll,m):
    """Owner photo language on the existing two-door bank; cores never move."""
    # Separate cladding elements preserve the actual entrance voids.
    for z in (GROUND,GALLERY):
        for x in (22,25.6):
            for a,b in ((x,x+.55),(x+2.55,x+3.1)):
                _box('Lift lobby | gold stone pier',(a,-4.495,z),(b,-4.43,z+3.22),coll,m['golden'],.008)
            _box('Lift lobby | charcoal marble door crown',(x+.55,-4.497,z+2.48),(x+2.55,-4.425,z+3.22),coll,m['charcoal'],.008)
        for a,b in ((21.98,22.015),(28.685,28.72)):
            _box('Lift lobby | gold stone bank side',(a,-8.05,z),(b,-4.43,z+3.22),coll,m['golden'],.006)
        # Warm polished floor inset, with clear paths in front of each door.
        _box('Lift lobby | gold stone floor',(20.5,-4.38,z-.01),(30,-1.65,z+.016),coll,m['golden'],.008)
        _box('Lift lobby | charcoal floor margin',(20.5,-1.72,z+.017),(30,-1.65,z+.026),coll,m['charcoal'])
        # Owner lobby has a lower plain ceiling, slim black tracks and warm slots.
        _box('Lift lobby | lower cream ceiling',(20.5,-4.42,z+3.23),(30,-1.65,z+3.37),coll,m['white'])
        for y in (-3.75,-2.25):
            _box('Lift lobby | black ceiling light track',(20.6,y-.04,z+3.205),(29.9,y+.04,z+3.23),coll,m['black'])
            for x in (21.3,23.8,26.3,28.8):
                _box('Lift lobby | recessed track aperture',(x-.12,y-.025,z+3.20),(x+.12,y+.025,z+3.207),coll,m['emission'])['sdb_fixture']=True
        # A representative two-sided destination-control pedestal, rather than signs.
        # Its location is inferred; it leaves over1.6m approach depth before the bank.
        _box('Lift lobby | destination kiosk stone body',(26.2,-2.60,z),(27.65,-2.25,z+1.32),coll,m['golden'],.015)
        _box('Lift lobby | kiosk dark plinth',(26.18,-2.62,z),(27.67,-2.23,z+.065),coll,m['charcoal'],.006)
        for x in (26.45,26.925,27.40):
            ob=_box('Lift lobby | destination display',(x-.085,-2.232,z+.98),(x+.085,-2.18,z+1.30),coll,m['black'],.012)
            ob['reference_detail']='owner_lift_lobby.jpg: inclined black destination-control terminals; no invented floor text'
            _box('Lift lobby | display touch inset',(x-.059,-2.174,z+1.12),(x+.059,-2.17,z+1.265),coll,m['glass'],.004)
        data=bpy.data.lights.new(PREFIX+'Lift lobby warm area','AREA');data.energy=220;data.shape='RECTANGLE';data.size=7;data.size_y=1.8
        ob=bpy.data.objects.new(PREFIX+'Lift lobby warm area',data);coll.objects.link(ob);ob.location=(25,-3,z+3.15);ob['sdb_fixture']=True
    coll['owner_photo_reference']='owner_lift_lobby.jpg: honey polished stone, charcoal marble door crowns, low white ceiling/black track lights and destination-control pedestal. Bank count, dimensions and pedestal position adapted to model.'


def _garden_corridor(coll,m):
    """Long indoor planting edge and timber ceiling from the owner garden photo."""
    rng=random.Random(912)
    # Lower, restrained granite trough establishes a planted corridor edge.
    trough=MeshBatch(PREFIX+'Planted corridor | dark granite trough walls',coll,m['charcoal'])
    for a,b in ((-24,-12.2),(-11.8,-.2),(.2,11.8),(12.2,20)):
        trough.add_box((a,3.75,.30),(b,3.88,.93))
        trough.add_box((a,4.55,.30),(b,4.68,.93))
        trough.add_box((a,3.75,.30),(a+.13,4.68,.93))
        trough.add_box((b-.13,3.75,.30),(b,4.68,.93))
        _box('Planted corridor | real soil bed',(a+.13,3.88,.70),(b-.13,4.55,.83),coll,m['soil'])
        for k in range(int((b-a)/.85)):
            xx=a+.45+k*.85
            _plant('Planted corridor | low planting',xx,4.15+rng.uniform(-.15,.15),.83,coll,m,rng,.30)
        for xx in (a+2.2,b-2.2):
            _plant('Planted corridor | tall foliage',xx,4.2,.83,coll,m,rng,1.05)
    _tag(_bevel(trough.commit(),.012,3))
    # The slats span the narrow planter-side corridor, leaving the main hall ceiling.
    ceiling=MeshBatch(PREFIX+'Planted corridor | oak ceiling slats',coll,m['wood'])
    for k in range(158):
        x=-24+k*.28
        ceiling.add_box((x,2.75,5.51),(x+.075,7.1,5.68))
    _tag(ceiling.commit())
    for y in (3.03,6.80):
        _box('Planted corridor | continuous linear light',(-24,y-.028,5.493),(20,y+.028,5.509),coll,m['emission'])['sdb_fixture']=True
    # Upper visible gallery fronts reproduce the layered corridor aspect.
    fronts=MeshBatch(PREFIX+'Planted corridor | layered cream gallery parapets',coll,m['ivory'])
    for level in range(3):
        z=GALLERY+3.9*level
        for x in range(-24,20,2):
            edge=north_spine_y(x+1)-4.4
            fronts.add_box((x,edge-.03,z),(min(x+2,20),edge+.13,z+1.05))
    _tag(fronts.commit())
    coll['owner_photo_reference']='owner_indoor_garden.jpg: dark granite troughs, low/tall indoor planting, polished cylindrical cream columns, timber slats, linear lights and layered gallery fronts. Extent and precise planting are inferred.'


def _plant(name,cx,cy,z,coll,m,rng,size=1):
    # Fine branching ornamental foliage; curved leaves attach to real branchlets.
    # Batched geometry keeps the richer plants practical to edit and regenerate.
    from polish_site import Geometry
    g=Geometry()
    for k in range(7):
        angle=k*2.39996+rng.uniform(-.3,.3);height=size*rng.uniform(1.05,1.95)
        base=Vector((cx+rng.uniform(-.09,.09)*size,cy+rng.uniform(-.09,.09)*size,z))
        end=base+Vector((math.cos(angle)*.18*size,math.sin(angle)*.18*size,height))
        g.tube(base,end,.011*size,.004*size,0,8)
        for j in range(10):
            a=angle+j*2.39996+rng.uniform(-.3,.3)
            origin=base.lerp(end,.28+.68*j/9)
            reach=size*rng.uniform(.17,.38)*(1-.3*j/9)
            tip=origin+Vector((reach*math.cos(a),reach*math.sin(a),size*rng.uniform(.015,.11)))
            g.tube(origin,tip,.004*size,.001*size,0,5)
            for leaf in range(5):
                pos=origin.lerp(tip,.20+.18*leaf)
                direction=a+(-1 if leaf%2 else 1)*rng.uniform(.55,1.20)
                length=size*rng.uniform(.11,.23)
                g.leaf(pos,(math.cos(direction),math.sin(direction),rng.uniform(-.45,.35)),length,length*.13,1,rng.uniform(-.7,.7))
    _tag(g.object(name+' botanical foliage',coll,[m['wood'],m['leaf']],smooth=True))


def _atrium(coll,m):
    rng=random.Random(348)
    # Recesses alternate along the spine without introducing floors through voids.
    for level in range(5):
        z=GALLERY+3.9*level
        north=level%2==0
        if north:
            pts=[(-43,3.8),(-27,3.8),(-27,.8),(-29,-.4),(-34,-.8),(-40,.0),(-43,1.2)]
            edge=[(-43,1.2,z+1.1),(-40,0,z+1.1),(-34,-.8,z+1.1),(-29,-.4,z+1.1),(-27,.8,z+1.1)]
            planter=(-35,1.4); bench=(-39,2.9)
        else:
            pts=[(-43,-4.6),(-27,-4.6),(-27,-2.1),(-30,-1),(-36,-.6),(-41,-1.5),(-43,-2.7)]
            edge=[(-43,-2.7,z+1.1),(-41,-1.5,z+1.1),(-36,-.6,z+1.1),(-30,-1,z+1.1),(-27,-2.1,z+1.1)]
            planter=(-35,-3);bench=(-39,-4.1)
        _tag(_bevel(polygon_prism(PREFIX+'Atrium | staggered planted balcony %02d'%level,pts,z-.20,z,coll,m['stone']),.015,2))
        _rail('Atrium balcony %02d'%level,edge,coll,m)
        # Real mounted apertures under the balcony edge light the tall public void.
        soffit=[(a,b,z-.205) for a,b,_ in edge]
        _tag(polyline_curve(PREFIX+'Atrium | balcony soffit linear aperture',soffit,collection=coll,mat=m['emission'],bevel_depth=.027))['sdb_fixture']=True
        data=bpy.data.lights.new(PREFIX+'Atrium balcony indirect area','AREA');data.energy=550;data.shape='RECTANGLE';data.size=8;data.size_y=1.8
        ob=bpy.data.objects.new(PREFIX+'Atrium balcony indirect area',data);coll.objects.link(ob);ob.location=(-35,1.45 if north else -3,z-.24);ob['sdb_fixture']=True
        px,py=planter
        _ring('Atrium | curved planter rim',px,py,2.6,.75,.13,z,.47,coll,m['white'],48)
        soil_points=[(px+2.43*math.cos(i*2*math.pi/48),py+.58*math.sin(i*2*math.pi/48)) for i in range(48)]
        _tag(polygon_prism(PREFIX+'Atrium | elliptical soil bed',soil_points,z+.30,z+.43,coll,m['soil']))
        for k in range(6):_plant('Atrium balcony planting',px-1.9+k*.75,py+rng.uniform(-.2,.2),z+.43,coll,m,rng,.85)
        bx,by=bench
        _box('Atrium | wood bench seat',(bx,by,z+.44),(bx+3.8,by+.6,z+.51),coll,m['wood'],.04)
        for xx in (bx+.3,bx+3.4):_box('Atrium | bench support',(xx,by+.1,z),(xx+.14,by+.5,z+.44),coll,m['metal'],.015)
    # Transparent internal screen at the gallery limit, kept narrow and panelised.
    glazing=MeshBatch(PREFIX+'Atrium | clear glazed north gallery balustrades',coll,m['glass'])
    for level in range(5):
        z=GALLERY+level*3.9
        for x in range(-42,-27,3):glazing.add_box((x,3.9,z+.1),(x+2.94,3.916,z+1.07))
    _tag(glazing.commit())
    # Ground planted relief pocket, preserving the centre circulation strip y=-1.5..1.5.
    _ring('Atrium | ground planted seating island',-38,5.3,3.3,1.45,.55,.3,.48,coll,m['white'])
    for k in range(9):_plant('Atrium ground planting',-40.6+k*.62,5.3+rng.uniform(-.45,.45),.6,coll,m,rng,1.3)
    coll['reference']='Sectional-Perspective...jpeg: alternating planted break-out edges and visual connections, adapted to existing spine.'


def _office(coll,m):
    # North03 front: hollow just the first 18.5m of the first office floor.
    y0=north_spine_y(3)+1.5
    cut=((-5.06,y0-.01,6.39),(11.06,28.0,10.29))
    _patch(bpy.data.objects.get('North 03 Front Glazed Slab'),lambda boxes:[p for b in boxes for p in _difference(b,cut)])
    # Replace opaque face liners in this selected band with truly thin window panes.
    _patch(bpy.data.objects.get('North 03 | Glazing Face Liners'),lambda boxes:[p for b in boxes for p in _difference(b,cut)])
    _box('Office | selected bay finish floor',(-4.95,y0,6.40),(10.95,28,GALLERY),coll,m['stone'])
    _box('Office | selected bay ceiling',(-4.95,y0,10.10),(10.95,28,10.25),coll,m['white'])
    _box('Office | opaque depth backdrop',(-4.95,27.84,GALLERY),(10.95,28.0,10.10),coll,m['white'])
    # Interior walls lead to spine through a 4.8m double door on axis x3.
    for a,b in ((-4.95,.65),(5.35,10.95)):
        _box('Office | arrival wall',(a,y0+.17,GALLERY),(b,y0+.32,10.10),coll,m['white'])
    for x in (.65,3.0):
        _box('Office | entry glass door leaf',(x,y0+.23,GALLERY+.05),(x+2.32,y0+.247,9.72),coll,m['glass'])
        for xx in (x,x+2.27):_box('Office | entry door stile',(xx,y0+.19,GALLERY),(xx+.05,y0+.27,9.78),coll,m['metal'],.005)
        _tube('Office | door pull',(x+1.95,y0+.15,7.65),(x+1.95,y0+.15,8.3),.018,coll,m['metal'])
    _box('Office | spine to tower access bridge',(.55,5.75,GALLERY-.20),(5.45,y0+.3,GALLERY),coll,m['stone'])
    for side in (-4.99,10.975):
        _box('Office | limestone sill wall',(side,12.50,GALLERY),(side+.016,26.10,GALLERY+1.0),coll,m['stone'])
        for y in (12.55,14.05,15.55,17.05,18.55,20.05,21.55,23.05,24.55):
            _box('Office | true clear window pane',(side,y,GALLERY+1),(side+.016,y+1.47,10.06),coll,m['glass'])
        # Furniture route is a clear3m central corridor x1.5..4.5.
    for y in (15,21):
        for x in (-4.3,4.9):
            _box('Office | glazed partition',(x+4.15,y-1.3,GALLERY),(x+4.17,y+4.2,9.55),coll,m['glass'])
            _box('Office | oak desk',(x,y,GALLERY+.71),(x+1.8,y+.82,GALLERY+.78),coll,m['wood'],.035)
            for dx in (.12,1.58):_box('Office | desk legs',(x+dx,y+.12,GALLERY),(x+dx+.08,y+.7,GALLERY+.71),coll,m['metal'],.015)
            _box('Office | desk screen',(x+.65,y+.6,GALLERY+.82),(x+1.25,y+.67,GALLERY+1.23),coll,m['black'],.018)
            _box('Office | screen base',(x+.87,y+.47,GALLERY+.78),(x+1.03,y+.69,GALLERY+.82),coll,m['metal'])
            _chair(x+.9,y-.6,GALLERY,coll,m)
            _box('Office | side cabinet',(x+2.5,y+.1,GALLERY),(x+3.5,y+.55,GALLERY+.74),coll,m['wood'],.035)
    # Compact meeting bay in foreground along west side; access corridor remains clear.
    _box('Office | meeting table',(-4.0,11.3,GALLERY+.73),(-1.0,12.5,GALLERY+.8),coll,m['wood'],.06)
    for x in (-3.4,-1.6):
        for y in (10.75,13.05):_chair(x,y,GALLERY,coll,m)
    for x in (-2.5,7.5):
        _box('Office | ceiling diffuser',(x-1,17,10.075),(x+1,20,10.10),coll,m['emission'])['sdb_fixture']=True
        data=bpy.data.lights.new(PREFIX+'Office soft area','AREA');data.energy=300;data.size=4
        ob=bpy.data.objects.new(PREFIX+'Office soft area',data);coll.objects.link(ob);ob.location=(x,19,9.99);ob['sdb_fixture']=True
    coll['fitout_scope']='Private office furniture, partition divisions and equipment inferred; public typical floor plan establishes corridor/office arrangement only.'


def _chair(x,y,z,coll,m):
    _box('Office | upholstered seat',(x-.27,y-.25,z+.43),(x+.27,y+.25,z+.5),coll,m['fabric'],.055)
    _box('Office | upholstered back',(x-.27,y+.20,z+.48),(x+.27,y+.28,z+.99),coll,m['fabric'],.05)
    _tube('Office | chair pedestal',(x,y,z+.1),(x,y,z+.43),.03,coll,m['metal'])
    for angle in range(5):
        a=angle*2*math.pi/5;_tube('Office | chair five star base',(x,y,z+.11),(x+.29*math.cos(a),y+.29*math.sin(a),z+.08),.018,coll,m['metal'])


def _sculpture(coll,m):
    # Smaller study of photo14's suspended droplet, in double-height east stair void.
    # It is a reference motif here, not a claim of surveyed position or full scale.
    _ring('Entrance | droplet basin rim',46,1.0,1.8,1.8,.14,.30,.30,coll,m['metal'])
    _lathe('Entrance | faceted droplet reference study',46,1.0,[(.12,.54),(.85,.65),(1.32,1.1),(1.5,1.7),(1.36,2.3),(1.05,3.0),(.72,3.8),(.36,4.65),(.12,5.4),(.07,6.0)],coll,m['red'],16,True)
    _ring('Entrance | basin cove',46,1,1.86,1.86,.045,.305,.03,coll,m['emission'])['sdb_fixture']=True


def _inspection_cameras(coll):
    specs={
        'CAM Lobby':((-46,0,1.90),(8,0,2.45),25),
        'CAM Atrium':((-45,-3.2,8.05),(-32,.8,9.8),24),
        'CAM Office':((3,10.5,8.15),(2.5,23,8.1),24),
        'CAM Lift Lobby':((20.6,-.7,1.8),(25,-4.45,1.8),25),
        'CAM Stair':((30,-1.5,2.0),(39,1.0,4.3),23),
        'CAM Planted Corridor':((-22,1.75,1.9),(16,4.1,2.2),24),
    }
    out={}
    for name,(loc,target,lens) in specs.items():
        ob=camera(name,location=loc,target=target,collection=coll,focal_length=lens)
        ob.data.clip_start=.05;ob.data.clip_end=800
        ob['sdb_static_inspection_view']=True
        out[name]=ob
    return out


def apply(scene):
    """Idempotently correct junctions and add editable public/selected interiors.

    Return cameras and route dictionary for the runner; never change active camera.
    """
    root=ensure_collection(ROOT,scene.collection)
    _clear(root)
    m=_mats()
    groups={n:ensure_collection(PREFIX+n,root) for n in ('Lobby','Stair','Lift lobby','Planted atrium','North03 office fitout','Entrance motif','Inspection cameras')}
    correct_junctions(scene)
    _floor_tiles(groups['Lobby'],m);_column_seating(groups['Lobby'],m);_ceiling_lights(groups['Lobby'],m)
    _stairs(groups['Stair'],m);_lift(groups['Lift lobby'],m);_owner_lift_finishes(groups['Lift lobby'],m);_atrium(groups['Planted atrium'],m);_garden_corridor(groups['Planted atrium'],m);_office(groups['North03 office fitout'],m);_sculpture(groups['Entrance motif'],m)
    cams=_inspection_cameras(groups['Inspection cameras'])
    route={
        'units':'metres; reconstruction dimensions estimated',
        'ground_lobby':{'x_range':[-48,48],'floor_surface_z':GROUND,'centre_clear_strip_y':[-1.5,1.5]},
        'stair':{'lower_approach':[33.5,-1.8,.3],'half_landing':[41.4,0,3.39],'upper_landing':[34,1.8,GALLERY],'north_gallery_connection':[34,5.5,GALLERY],'risers':36,'riser_m':(GALLERY-GROUND)/36,'tread_m':.3,'flight_width_m':2},
        'lift':{'open_ground_entry':[23.55,-4.5,.3],'gallery_entry':[23.55,-4.5,GALLERY],'cab_model':'static at ground; landing doors upper closed'},
        'office':{'entry':[3,north_spine_y(3)+1.73,GALLERY],'corridor_x':[1.5,4.5],'depth_y':[north_spine_y(3)+1.5,28],'floor_surface_z':GALLERY},
        'atrium':{'x_range':[-43,-27],'floor_surface_z':[GALLERY+3.9*i for i in range(5)]},
    }
    scene['Public route metadata']=json.dumps(route,sort_keys=True)
    scene['Interior scope']='Photographic public interior language; selected reconstructed segment and inferred private office fitout. No as-built claim.'
    root['public_route_metadata']=json.dumps(route,sort_keys=True)
    scene.view_layers[0].update()
    return {'cameras':cams,'public_route':route,'collection':root}
