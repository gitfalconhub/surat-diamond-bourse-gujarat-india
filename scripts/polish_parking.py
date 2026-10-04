# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable, connected two-basement visualization; layout is inferred, not surveyed.

The owner documents basement parking. Detailed footprints, levels, structure,
ramps and fit-out here are reconstruction assumptions with a traversable route.
"""
import math, random, json
import bpy
from mathutils import Vector
from sdb_utils import MeshBatch, ensure_collection, material, polyline_curve, camera, point_at
from polish_architecture import _clear, _difference, _patch, _tube

ROOT='Polish | Basement parking'
PREFIX='PK | '
LEVELS=(-4.2,-8.3)
BOUNDS=(-208,208,-112,112)

def _mat(name, color, rough=.6, metal=0):
    m=material('SDB Parking '+name,base_color=(*color,1),roughness=rough,metallic=metal)
    p=m.node_tree.nodes.get('Principled BSDF')
    if name in ('Concrete','Floor','Retaining wall'):
        nodes=m.node_tree.nodes; links=m.node_tree.links
        noise=nodes.get('Parking micrograin') or nodes.new('ShaderNodeTexNoise'); noise.name='Parking micrograin'
        noise.inputs['Scale'].default_value=18;noise.inputs['Detail'].default_value=3
        tex=nodes.get('Parking metre coordinates') or nodes.new('ShaderNodeTexCoord');tex.name='Parking metre coordinates'
        links.new(tex.outputs['Position'] if 'Position' in tex.outputs else tex.outputs['Object'],noise.inputs['Vector'])
        bump=nodes.get('Parking subtle bump') or nodes.new('ShaderNodeBump');bump.name='Parking subtle bump'
        bump.inputs['Strength'].default_value=.2;bump.inputs['Distance'].default_value=.004
        links.new(noise.outputs['Fac'],bump.inputs['Height']); links.new(bump.outputs['Normal'],p.inputs['Normal'])
    return m

def _box(name,lo,hi,coll,mat,bevel=0):
    o=MeshBatch(PREFIX+name,coll,mat).add_box(lo,hi).commit();o['reconstruction_scope']='inferred basement visualization'
    if bevel:
        b=o.modifiers.new('Rounded construction edges','BEVEL');b.width=bevel;b.segments=2
    return o

def _text(body, loc, size, coll, mat, rotation=(math.pi/2,0,0), name=None):
    d=bpy.data.curves.new(PREFIX+(name or body),'FONT');d.body=body;d.size=size;d.align_x='CENTER';d.extrude=.001
    o=bpy.data.objects.new(PREFIX+(name or body),d);coll.objects.link(o);o.location=loc;o.rotation_euler=rotation;d.materials.append(mat)
    return o

def _subtract_boxes(o,cuts):
    def transform(boxes):
        for cut in cuts: boxes=[part for b in boxes for part in _difference(b,cut)]
        return boxes
    _patch(o,transform)

def _ramp(name,x0,x1,y0,y1,z0,z1,coll,mat,thick=.28):
    vs=[(x,y,z) for zoff in (-thick,0) for x,y,z in
        [(x0,y0,z0+zoff),(x1,y0,z0+zoff),(x1,y1,z1+zoff),(x0,y1,z1+zoff)]]
    faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    m=bpy.data.meshes.new(PREFIX+name+' Mesh');m.from_pydata(vs,[],faces);m.update()
    o=bpy.data.objects.new(PREFIX+name,m);coll.objects.link(o);m.materials.append(mat)
    return o

def _arrow(x,y,z,direction,coll,mat):
    # Floor arrow local axis+Y; paint lies just above the concrete surface.
    poly=[(-.10,-1),(.10,-1),(.10,.25),(.45,.25),(0,.85),(-.45,.25),(-.10,.25)]
    co=[(x+px*math.cos(direction)-py*math.sin(direction),y+px*math.sin(direction)+py*math.cos(direction),z+.0003) for px,py in poly]
    m=bpy.data.meshes.new('Parking direction arrow');m.from_pydata(co,[],[tuple(range(len(co)))]);m.update()
    o=bpy.data.objects.new(PREFIX+'Aisle direction arrow',m);coll.objects.link(o);m.materials.append(mat)

def apply(scene=None):
    scene=scene or bpy.context.scene
    root=ensure_collection(ROOT);_clear(root)
    structure=ensure_collection('Parking | Slabs columns and ramps',root)
    detail=ensure_collection('Parking | Markings services and vehicles',root)
    cores=ensure_collection('Parking | Vertical connections',root)
    lights=ensure_collection('Parking | Lighting and cameras',root)
    mats={k:_mat(k,*v) for k,v in {
        'Concrete':((.42,.40,.35),.85,0), 'Floor':((.28,.29,.28),.65,0),
        'Retaining wall':((.38,.36,.31),.82,0), 'White paint':((.75,.75,.69),.5,0),
        'Yellow paint':((.70,.43,.025),.5,0), 'Red pipe':((.32,.025,.016),.35,.25),
        'Black rubber':((.025,.027,.028),.7,0), 'Galvanized metal':((.36,.39,.40),.34,.85),
        'Column band':((.40,.13,.045),.55,0), 'Wayfinding blue':((.025,.075,.085),.6,0),
    }.items()}
    emission=_mat('LED diffuser',(.85,.9,1),.3)
    p=emission.node_tree.nodes.get('Principled BSDF');p.inputs['Emission Color'].default_value=(.83,.9,1,1);p.inputs['Emission Strength'].default_value=20
    green=_mat('Exit light',(.006,.09,.02),.4)
    p=green.node_tree.nodes.get('Principled BSDF');p.inputs['Emission Color'].default_value=(.03,.5,.08,1);p.inputs['Emission Strength'].default_value=.025
    # Cut foundation/ramp/core paths in existing generic site solids. These
    # source boxes stay preserved by _patch, so repeated application is stable.
    terrain=bpy.data.objects.get('Presentation terrain plane')
    _subtract_boxes(terrain,[((-208,-112,-10),(208,112,-.65))])
    # A welded planar ring avoids secondary-ray seams where long, coincident
    # box side faces met across the 20km context terrain. The basement stays open.
    if terrain:
        old=terrain.data;mesh=bpy.data.meshes.new('Context terrain with welded basement opening')
        inv=terrain.matrix_world.inverted()
        points=[(-10000,-10000,-.9),(10000,-10000,-.9),(10000,10000,-.9),(-10000,10000,-.9),
                (-208,-112,-.9),(208,-112,-.9),(208,112,-.9),(-208,112,-.9)]
        mesh.from_pydata([tuple(inv@Vector(p)) for p in points],[],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
        for mat in old.materials:mesh.materials.append(mat)
        mesh.update();terrain.data=mesh
        if old.users==0 and not old.use_fake_user:bpy.data.meshes.remove(old)
    ground_cuts=[((-194.3,-113,-10),(-185.7,-65,.25)),
                 ((21.8,-8.2,-10),(29,-4.5,.4)),
                 ((34.5,-3.2,-10),(42.8,3.2,.4))]
    for n in ('Site datum','Site ground pavement','Inner arrival and pedestrian aprons'):
        if bpy.data.objects.get(n): _subtract_boxes(bpy.data.objects[n],ground_cuts)
    for n in ('PI | Lobby | 1.2m honed stone tile field','PI | Lobby | continuous floor substrate','PI | Lobby | dark stone border and transverse bands'):
        if bpy.data.objects.get(n): _subtract_boxes(bpy.data.objects[n],[((34.5,-3.2,.05),(42.8,3.2,.4))])
    # Broad slabs segmented around through-cores and the second ramp void.
    for li,z in enumerate(LEVELS):
        slab=_box(f'B{li+1} floor slab',(-208,-112,z-.27),(208,112,z),structure,mats['Floor'])
        cuts=[((21.8,-8.2,z-.3),(29,-4.5,z+.1)),((34.5,-3.2,z-.3),(42.8,3.2,z+.1))]
        if li==0:cuts.append(((-204.3,-103,z-.3),(-195.7,-59,z+.1)))
        _subtract_boxes(slab,cuts)
    # Continuous retaining walls (ground ramp terminates before north edge).
    wall=MeshBatch(PREFIX+'Retaining perimeter',structure,mats['Retaining wall'])
    for lo,hi in [((-208,-112,-8.6),(-207.6,112,-.65)),((207.6,-112,-8.6),(208,112,-.65)),
                  ((-207.6,-112,-8.6),(207.6,-111.6,-.65)),((-207.6,111.6,-8.6),(207.6,112,-.65))]:wall.add_box(lo,hi)
    wall.commit()
    # Actual continuous descending surfaces and two 12 m clear turn areas.
    _ramp('Ground to B1 driveable ramp',-194,-186,-111,-67,.12,-4.2,structure,mats['Floor'])
    _ramp('B1 to B2 driveable ramp',-204,-196,-60,-103,-4.2,-8.3,structure,mats['Floor'])
    for x in (-194.22,-185.96):
        _ramp('Ground ramp side retaining wall',x,x+.18,-111,-67,1.22,-3.1,structure,mats['Concrete'],1.38)
    for x in (-204.22,-195.96):
        _ramp('B2 ramp kerb',x,x+.18,-60,-103,-4.0,-8.1,structure,mats['Concrete'],.32)
    # Entry connects to existing peripheral approach, no fabricated offsite gate.
    _box('Ramp approach lane',(-194,-124,.09),(-186,-111,.12),structure,mats['Floor'])
    for x in (-194,-186):
        _tube('Ramp safety rail',(x,-112,1.15),(x,-67,-3.17),.045,detail,mats['Galvanized metal'])
    for k in range(0,44,2):
        t=k/44; y=-111+k; z=.12+(-4.32)*t
        _ramp('Ramp ribbed grip strip',-193.85,-186.15,y,y+.045,z+.006,z-.004,detail,mats['White paint'],.004)
    _text('BASEMENT PARKING  |  B1 / B2',(-190,-115,2.2),.26,detail,mats['White paint'])
    _box('Ramp height sign',(-194.2,-115.2,1.95),(-185.8,-115.05,2.55),detail,mats['Wayfinding blue'])
    # Structural grid and parking slots. Keep a connected cross-aisle y[-4,4]
    # and clear ramp/turn rectangle x[-208,-180],y[-112,-48].
    columns=MeshBatch(PREFIX+'Concrete column grid',structure,mats['Concrete'])
    bands=MeshBatch(PREFIX+'Column finish bands',detail,mats['Column band'])
    paint=MeshBatch(PREFIX+'Parking bay paint',detail,mats['White paint'])
    stops=MeshBatch(PREFIX+'Wheel stops',detail,mats['Concrete'])
    beams=MeshBatch(PREFIX+'Concrete transfer beams',structure,mats['Concrete'])
    leds=MeshBatch(PREFIX+'Linear LED fixtures',detail,emission)
    pipes=MeshBatch(PREFIX+'Fire sprinkler mains',detail,mats['Red pipe'])
    trays=MeshBatch(PREFIX+'Cable trays',detail,mats['Galvanized metal'])
    marked=0;car_positions=[]
    for li,z in enumerate(LEVELS):
        ceiling= -.65 if li==0 else LEVELS[0]-.27
        for y in range(-100,100,16):
            if abs(y)<6:continue
            beams.add_box((-180,y-.22,ceiling-.42),(204,y+.22,ceiling))
            for ix in range(49):
                x=-177+ix*7.8
                if 20<x<45 and -12<y<12:continue
                columns.add_box((x-.34,y-.34,z),(x+.34,y+.34,ceiling))
                bands.add_box((x-.345,y-.345,z+1.0),(x+.345,y+.345,z+1.7))
                leds.add_box((x-.60,y+7.7,ceiling-.11),(x+.60,y+7.95,ceiling-.07))
            # Bays are 2.6 x 5 m; pedestrian/vehicle cross-aisle exempted.
            for ix in range(146):
                x=-177+ix*2.6
                for side in (-1,1):
                    y0=y+.4 if side==1 else y-5.4; y1=y+5.4 if side==1 else y-.4
                    if y0<4 and y1>-4:continue
                    if 19<x<45 and -13<y<13:continue
                    paint.add_box((x,y0,z+.003),(x+.055,y1,z+.006))
                    paint.add_box((x,y0 if side==1 else y1-.05,z+.003),(x+2.6,(y0+.05) if side==1 else y1,z+.006))
                    sy=y+4.65*side
                    stops.add_box((x+.5,sy-.075,z),(x+2.1,sy+.075,z+.10))
                    marked+=1
                    if ix%13==0 and (ix+li+y)%3==0:
                        car_positions.append((x+1.3,y+2.7*side,z,side,li))
        for y in range(-92,105,16):
            pipes.add_box((-183,y,ceiling-.6),(203,y+.085,ceiling-.515))
            trays.add_box((-183,y+2.0,ceiling-.38),(203,y+2.3,ceiling-.32))
            for x in range(-166,201,26):
                _arrow(x,y,z,(-math.pi/2 if y%32 else math.pi/2),detail,mats['White paint'])
        # Cross-route from ramp turning apron to shared lift/stair lobby.
        for x in range(-171,45,24):_arrow(x,0,z,-math.pi/2,detail,mats['Yellow paint'])
        # Concentrated physical lights in filmable parking/core area; all other
        # visible fixtures are emitting geometry, not thousands of point lights.
        for x in range(-166,45,26):
            for y in (-84,-68,-52,-36,-20,-4,12):
                data=bpy.data.lights.new(PREFIX+'B'+str(li+1)+' LED','AREA');data.energy=350;data.color=(.83,.9,1);data.shape='RECTANGLE';data.size=2.0;data.size_y=.4
                ob=bpy.data.objects.new(data.name,data);lights.objects.link(ob);ob.location=(x,y,ceiling-.13)
                ob['sdb_light_role']='parking'
        for x in (-150,-98,-46,6):
            _box('Suspended wayfinding', (x-2,-3,z+2.65),(x+2,-2.86,z+3.1),detail,mats['Wayfinding blue'])
            _text(f'B{li+1}  PARKING   /   LIFTS  >',(x,-2.83,z+2.78),.22,detail,mats['White paint'],(math.pi/2,0,math.pi))
        for x in (-145.8,-138,-130.2,-122.4,-114.6,-106.8,-99):
            _text(f'B{li+1}',(x,-67.64,z+1.2),.28,detail,mats['White paint'],(math.pi/2,0,math.pi))
        for x in (-158,-132,-106,-80,-54,-28,-2,24):
            for y in (-68,-36,-4):
                _tube('Sprinkler drop',(x,y+.04,ceiling-.55),(x,y+.04,ceiling-.8),.015,detail,mats['Red pipe'],8)
                _tube('Sprinkler head',(x,y+.04,ceiling-.78),(x,y+.04,ceiling-.82),.036,detail,mats['Galvanized metal'],8)
        _box('Core exit sign',(35.5,-3.3,z+2.0),(36.9,-3.2,z+2.35),detail,green)
        _text('EXIT',(36.2,-3.34,z+2.08),.22,detail,mats['White paint'])
    for batch in (columns,bands,paint,stops,beams,leds,pipes,trays):batch.commit()
    # Shared detailed vehicle source from site pass, rotated to park nose north.
    sources=[o for o in bpy.data.objects if 'Shaped vehicle ' in o.name and o.name.endswith(' source') and o.type=='MESH']
    for i,(x,y,z,side,li) in enumerate(car_positions):
        for src in sources[i%len(sources):i%len(sources)+1] if sources else []:
            ob=bpy.data.objects.new(PREFIX+f'B{li+1} parked vehicle {i} '+src.name,src.data);detail.objects.link(ob)
            ob.location=(x,y,z);ob.rotation_euler.z=(math.pi/2 if side==1 else -math.pi/2)
            ob.scale=src.scale
    # Continue exactly the selected lift bank, with enclosed static shaft walls
    # and closed B1/B2 landing doors. A real cab is already modeled at ground.
    for x0,x1 in ((22,25.1),(25.6,28.7)):
        for lo,hi in [((x0,-8.2,-8.6),(x0+.22,-4.5,.3)),((x1-.22,-8.2,-8.6),(x1,-4.5,.3)),
                      ((x0,-8.2,-8.6),(x1,-7.98,.3))]:_box('Lift shaft continuation',lo,hi,cores,mats['Concrete'])
        for li,z in enumerate(LEVELS):
            _box('Lift landing threshold',(x0+.3,-4.75,z-.12),(x1-.3,-4.45,z),cores,mats['Galvanized metal'])
            _box('Landing door left',(x0+.46,-4.73,z),(x0+1.54,-4.66,z+2.3),cores,mats['Galvanized metal'])
            _box('Landing door right',(x0+1.56,-4.73,z),(x1-.46,-4.66,z+2.3),cores,mats['Galvanized metal'])
            _text(f'B{li+1}',((x0+x1)/2,-4.64,z+2.52),.28,cores,mats['White paint'],(math.pi/2,0,math.pi))
            _box('Lift call control',(x1-.34,-4.65,z+1.0),(x1-.2,-4.60,z+1.22),cores,mats['Black rubber'])
    # U-stairs connect B2 -> B1 -> ground: 24/26 risers, 300 mm treads.
    for li,(bottom,top,risers) in enumerate([(-8.3,-4.2,24),(-4.2,.30,26)]):
        steps=risers//2;rise=(top-bottom)/risers;end=36.3+steps*.3
        _box('Stair intermediate landing',(end-.1,-2.8,bottom+steps*rise-.2),(end+2.2,2.8,bottom+steps*rise),cores,mats['Concrete'])
        _box('Stair level landing',(34.4,-2.8,top-.22),(36.3,2.8,top),cores,mats['Concrete'])
        for y0,y1,z0,z1 in ((-2.8,-.6,bottom+.02,bottom+steps*rise-.08),(.6,2.8,top-.08,bottom+steps*rise+.02)):
            corners=[(36.3,y0,z0),(end,y0,z1),(end,y1,z1),(36.3,y1,z0)]
            vs=[(x,y,z-.23) for x,y,z in corners]+corners
            me=bpy.data.meshes.new('Basement stair structural waist Mesh');me.from_pydata(vs,[],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);me.update()
            ob=bpy.data.objects.new(PREFIX+'Stair structural waist',me);cores.objects.link(ob);me.materials.append(mats['Concrete'])
        for k in range(steps):
            x=36.3+k*.3;h=bottom+(k+1)*rise
            _box('Basement lower tread',(x,-2.8,h-.19),(x+.3,-.6,h),cores,mats['Concrete'])
            x=end-(k+1)*.3;h=bottom+(steps+k+1)*rise
            _box('Basement upper tread',(x,.6,h-.19),(x+.3,2.8,h),cores,mats['Concrete'])
        _tube('Stair handrail',(36.3,-.62,bottom+.95),(40.2,-.62,bottom+steps*rise+.95),.04,cores,mats['Galvanized metal'])
        _tube('Stair handrail',(40.2,.62,bottom+steps*rise+.95),(36.3,.62,top+.95),.04,cores,mats['Galvanized metal'])
        for side in (-2.75,2.75):
            for x in (36.3,37.5,38.7,39.9):
                zz=bottom+(x-36.3)/3.9*(steps*rise) if side<0 else top-(x-36.3)/3.9*(steps*rise)
                _tube('Stair baluster',(x,side,zz),(x,side,zz+1.0),.023,cores,mats['Galvanized metal'])
            _tube('Outer stair handrail',(36.3,side,(bottom if side<0 else top)+1),(40.2,side,bottom+steps*rise+1),.04,cores,mats['Galvanized metal'])
    # Ground edge guards keep the hole legible and protect the centre landing;
    # leave the two stair approaches open. Outer ground passage passes north.
    for a,b in [(a,b) for z in (.3,-4.2) for a,b in [((34.5,-3.2,z),(42.8,-3.2,z)),((42.8,-3.2,z),(42.8,3.2,z)),
                ((42.8,3.2,z),(34.5,3.2,z)),((34.5,-.55,z),(34.5,.55,z))]]:
        av,bv=Vector(a),Vector(b)
        _tube('Ground stair void guard',av+Vector((0,0,1.1)),bv+Vector((0,0,1.1)),.04,cores,mats['Galvanized metal'])
        count=max(1,math.ceil((bv-av).length/1.3))
        for k in range(count+1):
            p=av+(bv-av)*(k/count);_tube('Ground stair guard post',p,p+Vector((0,0,1.1)),.022,cores,mats['Galvanized metal'])
    cams={}
    for name,loc,target,lens in [
        ('CAM Parking',(-155,-66,-2.60),(-109,-77,-2.4),28),
        ('CAM Parking Core',(16,2,-2.60),(25,-5,-2.7),25),
        ('CAM Parking Ramp',(-190,-116,1.8),(-190,-68,-3.6),28),
        ('CAM Basement Stair',(34,-8,-2.6),(39,0,-1.6),22)]:
        cams[name]=camera(name,location=loc,target=target,focal_length=lens,collection=lights)
        cams[name].data.clip_start=.05;cams[name].data.clip_end=300
    stats={'levels':list(LEVELS),'bounds':BOUNDS,'marked_bays':marked,'vehicle_placements':len(car_positions),
           'parking_reference':'owner facilities; exact layout inferred','ramps':'ground/B1/B2 continuous slabs; approx9.5-9.8 percent grade',
           'cameras':list(cams)}
    scene['sdb_parking_metadata']=json.dumps(stats)
    return stats
