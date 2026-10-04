# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference-review corrections: circulation, canopies, landscape and shaders.

All lengths are metres. This module is called by build_sdb after the site build.
The refinements are ordinary editable meshes, curves, materials and instances.
"""
import bpy, math, random
from mathutils import Vector
from sdb_utils import MeshBatch, ensure_collection, material, polygon_prism, mesh_instance
from sdb_architecture import north_spine_y, _tower_sections

def delete_named(name):
    ob=bpy.data.objects.get(name)
    if ob: bpy.data.objects.remove(ob,do_unlink=True)

def mesh_object(name,vs,fs,coll,mat):
    me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update()
    ob=bpy.data.objects.new(name,me);coll.objects.link(ob);me.materials.append(mat)
    return ob

def tube(name,a,b,r,coll,mat,r2=None,sides=8):
    a,b=Vector(a),Vector(b);vec=b-a
    v=vec.normalized().cross(Vector((0,0,1)))
    if v.length<.01: v=Vector((1,0,0))
    v.normalize();u=vec.normalized().cross(v)
    vs=[]
    for center,radius in [(a,r),(b,r if r2 is None else r2)]:
        vs += [tuple(center+radius*(u*math.cos(i*2*math.pi/sides)+v*math.sin(i*2*math.pi/sides))) for i in range(sides)]
    fs=[tuple(reversed(range(sides))),tuple(range(sides,sides*2))]
    fs += [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    return mesh_object(name,vs,fs,coll,mat)

def ellipsoid(name,center,scale,coll,mat,segments=12,rings=6):
    vs=[];fs=[]
    for j in range(rings+1):
        t=math.pi*j/rings
        for i in range(segments):
            a=2*math.pi*i/segments
            vs.append((center[0]+scale[0]*math.sin(t)*math.cos(a),center[1]+scale[1]*math.sin(t)*math.sin(a),center[2]+scale[2]*math.cos(t)))
    for j in range(rings):
        for i in range(segments):
            a=j*segments+i;b=j*segments+(i+1)%segments
            fs.append((a,b,b+segments,a+segments))
    ob=mesh_object(name,vs,fs,coll,mat)
    for p in ob.data.polygons:p.use_smooth=True
    return ob

def architecture(params,collections,mats):
    coll=collections['Podium'];cream=mats['SDB Sandstone Cream']
    delete_named('Central Spine | Atrium Floor Slabs')
    floors=MeshBatch('Spine | Continuous galleries and connecting bridges',coll,cream)
    for level in range(16):
        z=6.4+3.9*level
        # Uninterrupted galleries run beside both external walls; voids stay between them.
        floors.add_box((-174,-8.5,z-.18),(174,-4.5,z+.08))
        for x in range(-174,174,6):
            y=north_spine_y(x+3)
            floors.add_box((x,y-4.4,z-.18),(x+6,y-.45,z+.08))
        for x in (-143,-117,-83,-57,-23,3,42,68,120):
            floors.add_box((x-2,-4.5,z-.18),(x+2,north_spine_y(x)-.4,z+.08))
    floors.commit()['sdb_component']='continuous_spine_circulation'
    port=ensure_collection('Tower arrival canopies',collections['root'])
    for t in params['towers']:
        sec=_tower_sections(t,params)[-1];sign=sec['direction']
        edge=sec['y_max'] if sign>0 else sec['y_min'];x=sec['x'];cy=edge+sign*7
        # Rectangular canopy ring with a true circular oculus, without Boolean modifiers.
        n=48;vs=[];fs=[];half_x=7;half_y=4.5;r=1.4
        for z in (5.1,5.55):
            for ring in (0,1):
                for i in range(n):
                    a=2*math.pi*i/n;c,s=math.cos(a),math.sin(a)
                    q=min(half_x/max(abs(c),1e-8),half_y/max(abs(s),1e-8)) if ring==0 else r
                    vs.append((x+q*c,cy+q*s,z))
        for i in range(n):
            j=(i+1)%n
            fs.extend([(i,j,j+n,i+n),(i+2*n,i+3*n,j+3*n,j+2*n),(i,j,j+2*n,i+2*n),(i+n,i+3*n,j+3*n,j+n)])
        canopy=mesh_object(t['name']+' | Oculus entrance canopy',vs,fs,port,cream)
        canopy.parent=bpy.data.objects.get('Tower '+t['name']+' Root')
        cols=MeshBatch(t['name']+' | Canopy supports',port,cream)
        for dx in (-5.8,5.8):
            cols.add_box((x+dx-.3,cy+sign*2.8-.3,.3),(x+dx+.3,cy+sign*2.8+.3,5.1))
        cols.commit().parent=canopy.parent

def stone_shader(mat,base):
    nt=mat.node_tree;n=nt.nodes;nt.nodes.clear();link=nt.links.new
    out=n.new('ShaderNodeOutputMaterial');p=n.new('ShaderNodeBsdfPrincipled')
    p.inputs['Roughness'].default_value=.55;link(p.outputs['BSDF'],out.inputs['Surface'])
    geo=n.new('ShaderNodeNewGeometry');sep=n.new('ShaderNodeSeparateXYZ');link(geo.outputs['Position'],sep.inputs[0])
    norm=n.new('ShaderNodeSeparateXYZ');link(geo.outputs['Normal'],norm.inputs[0])
    def mathnode(op,a,b=None):
        m=n.new('ShaderNodeMath');m.operation=op
        for i,q in enumerate([a,b] if b is not None else [a]):
            if isinstance(q,(int,float)):m.inputs[i].default_value=q
            else:link(q,m.inputs[i])
        return m.outputs[0]
    mask=mathnode('GREATER_THAN',mathnode('ABSOLUTE',norm.outputs['X']),mathnode('ABSOLUTE',norm.outputs['Y']))
    horizontal=mathnode('ADD',mathnode('MULTIPLY',mask,sep.outputs['Y']),mathnode('MULTIPLY',mathnode('SUBTRACT',1,mask),sep.outputs['X']))
    u=mathnode('DIVIDE',horizontal,1.2);v=mathnode('DIVIDE',sep.outputs['Z'],.9)
    seam=mathnode('MAXIMUM',mathnode('LESS_THAN',mathnode('FRACT',u),.006),mathnode('LESS_THAN',mathnode('FRACT',v),.007))
    xyz=n.new('ShaderNodeCombineXYZ');link(mathnode('FLOOR',u),xyz.inputs['X']);link(mathnode('FLOOR',v),xyz.inputs['Y'])
    noise=n.new('ShaderNodeTexWhiteNoise');noise.noise_dimensions='2D';link(xyz.outputs[0],noise.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=tuple(c*.91 for c in base)+(1,)
    ramp.color_ramp.elements[1].color=tuple(c*1.06 for c in base)+(1,)
    link(noise.outputs['Value'],ramp.inputs[0])
    mix=n.new('ShaderNodeMixRGB');link(seam,mix.inputs[0]);link(ramp.outputs[0],mix.inputs[1]);mix.inputs[2].default_value=tuple(c*.63 for c in base)+(1,)
    link(mix.outputs[0],p.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.002
    link(seam,bump.inputs['Height']);link(bump.outputs['Normal'],p.inputs['Normal'])
    mat.diffuse_color=base+(1,)

def materials(mats):
    stone_shader(mats['SDB Sandstone Cream'],(.53,.49,.40))
    stone_shader(mats['SDB Red Granite'],(.30,.085,.052))
    glass=mats['SDB Dark Blue Glazing'];p=glass.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(.020,.031,.039,1)
    p.inputs['Roughness'].default_value=.125;p.inputs['Metallic'].default_value=.62
    p.inputs['Coat Weight'].default_value=.3
    glass.diffuse_color=(.020,.031,.039,1)
    world=bpy.context.scene.world;nt=world.node_tree;n=nt.nodes;ln=nt.links.new
    old=n.get('Background');out=n.get('World Output')
    # Keep analytic sky for illumination; a restrained gradient gives a clean camera horizon.
    tex=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');ln(tex.outputs['Normal'],sep.inputs[0])
    mapping=n.new('ShaderNodeMapRange');mapping.inputs['From Min'].default_value=-.06;mapping.inputs['From Max'].default_value=.65
    flip=n.new('ShaderNodeMath');flip.operation='MULTIPLY';flip.inputs[1].default_value=-1
    ln(sep.outputs['Z'],flip.inputs[0]);ln(flip.outputs[0],mapping.inputs['Value'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.57,.69,.78,1);ramp.color_ramp.elements[1].color=(.17,.35,.58,1)
    ln(mapping.outputs[0],ramp.inputs[0]);bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.8;ln(ramp.outputs[0],bg.inputs['Color'])
    ray=n.new('ShaderNodeLightPath');mix=n.new('ShaderNodeMixShader');ln(ray.outputs['Is Camera Ray'],mix.inputs[0]);ln(old.outputs[0],mix.inputs[1]);ln(bg.outputs[0],mix.inputs[2]);ln(mix.outputs[0],out.inputs['Surface'])

def landscape(collections,mats):
    coll=ensure_collection('Garden detail and human scale',collections['root'])
    grass=material('SDB Garden mound',base_color=(.08,.145,.037,1),roughness=.95)
    shrub=material('SDB Garden shrubs',base_color=(.048,.115,.021,1),roughness=.9)
    soil=material('SDB Garden mulch',base_color=(.075,.042,.023,1),roughness=1)
    cream=mats['SDB Sandstone Cream'];metal=mats['SDB Dark Metal']
    courts=[(-87,63),(-27,63),(35,63),(-113,-53),(-53,-53),(9,-53),(80,-53)]
    rng=random.Random(126)
    plant_source=ellipsoid('Shrub linked source',(0,0,0),(1,.85,.55),coll,shrub)
    plant_source.hide_render=True;plant_source.hide_viewport=True
    for i,(x,y) in enumerate(courts):
        ellipsoid('Court %02d | Planted grass mound'%i,(x+6,y+9,-.18),(6,7.5,.9),coll,grass,32,12)
        bed=MeshBatch('Court %02d | Planting beds'%i,coll,soil)
        for dx,dy in [(-12,15),(11,-15)]:
            bed.add_box((x+dx-3,y+dy-5,.15),(x+dx+3,y+dy+5,.22))
            for k in range(24):
                q=mesh_instance('Low flowering shrub',plant_source,(x+dx+rng.uniform(-2.8,2.8),y+dy+rng.uniform(-4.5,4.5),.48),scale=(.55,.55,.75),collection=coll)
        bed.commit()
    for x0,x1 in [(-200,-155),(104,186)]:
        MeshBatch('North peripheral lawn',coll,grass).add_box((x0,111,.02),(x1,124,.15)).commit()
    # Lamps follow the enclosed site, keeping circulation surfaces clear.
    lamps=MeshBatch('Roadside lamp arms',coll,metal)
    for x in range(-205,206,30):
        for y in (-123,125):
            tube('Site lamp pole',(x,y,.2),(x,y,7.3),.075,coll,metal)
            lamps.add_box((x-.05,y-.07,7.25),(x+1.7,y+.07,7.4))
    lamps.commit()
    # Discreet scale figures, modeled as clothed volumes at approximately 1.7m.
    skin=material('SDB Figure skin',base_color=(.22,.12,.065,1),roughness=.85)
    shirts=[material('SDB Shirt '+str(i),base_color=c+(1,),roughness=.85) for i,c in enumerate([(.48,.50,.48),(.07,.11,.14),(.23,.13,.08)])]
    pants=material('SDB Trousers',base_color=(.035,.044,.05,1),roughness=.9)
    for i,(x,y) in enumerate([(-83,75),(-82,78),(-95,50),(-26,57),(-21,57),(34,80),(40,47),(130,91),(133,90),(-112,-64),(8,-40),(80,-62)]):
        for dx in (-.13,.13):tube('Person legs',(x+dx,y,.2),(x+dx,y,1.03),.085,coll,pants)
        ellipsoid('Person torso',(x,y,1.18),(.24,.13,.32),coll,shirts[i%3])
        ellipsoid('Person head',(x,y,1.65),(.115,.11,.145),coll,skin)
        for sign in (-1,1):tube('Person arm',(x+sign*.24,y,1.40),(x+sign*.30,y+.04,.97),.06,coll,shirts[i%3])
    delete_named('Perimeter parked cars')
    rubber=material('SDB Tire rubber',base_color=(.012,.012,.012,1),roughness=.86)
    for i,x in enumerate(range(-176,181,44)):
        y=126;paint=material('SDB Vehicle paint '+str(i),base_color=([(.5,.52,.53,1),(.15,.17,.19,1),(.05,.09,.12,1)][i%3]),roughness=.27,metallic=.35)
        body=MeshBatch('Parked car body',coll,paint).add_box((x,y-.9,.55),(x+4.5,y+.9,1.22)).commit()
        bevel=body.modifiers.new('Soft body edges','BEVEL');bevel.width=.23;bevel.segments=3
        cabin=MeshBatch('Car glazing',coll,mats['SDB Dark Blue Glazing']).add_box((x+1,y-.76,1.2),(x+3.6,y+.76,1.84)).commit()
        bevel=cabin.modifiers.new('Sloped glazing corners','BEVEL');bevel.width=.22;bevel.segments=2
        for xx in (x+.85,x+3.6):
            for sign in (-1,1):tube('Car wheel',(xx,y+sign*.8,.55),(xx,y+sign*1.0,.55),.34,coll,rubber,sides=16)

def apply(params,collections,mats):
    architecture(params,collections,mats)
    landscape(collections,mats)
    materials(mats)
