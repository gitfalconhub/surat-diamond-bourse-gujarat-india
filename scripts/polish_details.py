# SPDX-License-Identifier: GPL-3.0-or-later
"""Final-scale detailing and reference-led Club exterior correction."""
import math, random, bpy
from mathutils import Vector, Matrix
from sdb_utils import MeshBatch, ensure_collection, material, camera, point_at
from polish_architecture import _clear, _box, _ring, _tube, _mesh
from sdb_architecture import PARAMS,_tower_sections

ROOT='Polish | Finishing details'

def apply(scene=None):
    scene=scene or bpy.context.scene
    root=ensure_collection(ROOT);_clear(root)
    metal=bpy.data.materials['SDB Brushed Chrome'];black=bpy.data.materials['SDB Interior Equipment Black']
    white=bpy.data.materials['SDB Interior White Plaster'];cream=bpy.data.materials['SDB Sandstone Cream']
    glass=bpy.data.materials['SDB Clear Architectural Glass'];wood=bpy.data.materials['SDB Interior Warm Wood']
    floor=bpy.data.materials['SDB Interior Polished Marble']
    # Real photographs reveal the Club's white curved inner face through the
    # north-facing opening. Original wrap faced south, hiding that front face.
    wrap=bpy.data.objects.get('Diamond Club Red Outer Wrap')
    if wrap:
        key=wrap.get('polish_detail_source_mesh')
        src=bpy.data.meshes.get(key) if key else None
        if src is None:src=wrap.data;src.use_fake_user=True;wrap['polish_detail_source_mesh']=src.name
        mesh=src.copy();mesh.name='Club north-facing corrected wrap Mesh'
        for v in mesh.vertices:v.co.x=300-v.co.x;v.co.y=110-v.co.y
        old=wrap.data;wrap.data=mesh
        if old!=src and old.users==0:bpy.data.meshes.remove(old)
        wrap['reference_correction']='Opening faces north approach to reveal white inner Club face, as Edmund Sumner photo16'
    old=bpy.data.objects.get('Diamond Club Cream Inner Cylinder')
    if old:old.hide_render=True;old.hide_set(True)
    # Hollow white elliptical shell, with a real-scale glazed entry near55deg.
    cx,cy=150,55;n=128;vs=[];fs=[]
    for i in range(n):
        a=i*2*math.pi/n;b=(i+1)*2*math.pi/n
        opening=47<math.degrees((a+b)/2)<63
        z0=3.5 if opening else .3
        base=len(vs)
        vs.extend([(cx+rx*math.cos(t),cy+ry*math.sin(t),z) for z in (z0,15) for rx,ry in ((18,24),(17.5,23.5)) for t in (a,b)])
        fs.extend(tuple(base+k for k in f) for f in [(0,1,5,4),(3,2,6,7),(4,5,7,6),(0,2,3,1),(0,4,6,2),(1,3,7,5)])
    ob=_mesh('Club | hollow white inner shell',vs,fs,root,cream)
    ob['reconstruction_scope']='photographic exterior shape; entrance and internal layout inferred'
    lettering=bpy.data.objects.get('DIAMOND CLUB lettering')
    if lettering:
        angle=math.radians(12);lettering.location=(174.65,61.50,5.8);lettering.rotation_euler=(math.pi/2,0,angle+math.pi/2);lettering.data.size=.65;lettering.data.align_x='CENTER'
    _ring('Club | roof coping',cx,cy,18.12,24.12,.8,15,.16,root,cream,128)
    # A recessed roof provides visually plausible inner-space depth.
    points=[(cx+17.5*math.cos(k*2*math.pi/n),cy+23.5*math.sin(k*2*math.pi/n)) for k in range(n)]
    batch=MeshBatch('FD | Club internal roof and floor',root,white)
    batch.add_polygon_extrusion(points,12.45,12.70);batch.add_polygon_extrusion(points,.15,.3);batch.commit()
    a=math.radians(55);c=Vector((cx+17.7*math.cos(a),cy+23.7*math.sin(a),0));t=Vector((-18*math.sin(a),24*math.cos(a),0)).normalized()
    normal=Vector((t.y,-t.x,0))
    verts=[tuple(c+t*off+Vector((0,0,z))) for off,z in [(-3.1,.3),(3.1,.3),(3.1,3.5),(-3.1,3.5)]]
    pane=_mesh('Club | entry glazing',verts,[(0,1,2,3)],root,glass)
    sol=pane.modifiers.new('16 mm entry glass','SOLIDIFY');sol.thickness=.016
    for off in (-3.1,-1,0,1,3.1):_tube('Club | entry mullion',c+t*off+Vector((0,0,.3)),c+t*off+Vector((0,0,3.5)),.035,root,metal)
    # Denser terminal granite screen fields, with actual square openings and
    # continuous border, preserve the photo's broad clustered perforations.
    for ti,spec in enumerate(PARAMS['towers']):
        old=bpy.data.objects.get(spec['name']+' | Perforated Red Screens')
        if old is None:continue
        sec=_tower_sections(spec,PARAMS)[-1];north=spec['side']=='north'
        yy=(sec['y_max']+3) if north else (sec['y_min']-3);left=sec['x']-3
        batch=MeshBatch('FD | Terminal granite screen',root,bpy.data.materials['SDB Red Granite'])
        for row in range(280):
            cells=[]
            for col in range(24):
                noise=(row*173+col*67+row*col*19+ti*47+31)%101
                cluster=math.sin(row*.105+ti*.6)+math.sin(col*.43+row*.018)
                cells.append(not (1<col<22 and noise<(55 if cluster>.4 else 20)))
            col=0
            while col<24:
                if not cells[col]:col+=1;continue
                start=col
                while col<24 and cells[col]:col+=1
                batch.add_box((left+start*.25,yy-.15,.3+row*.25),(left+col*.25,yy+.15,.3+(row+1)*.25))
        inv=old.matrix_world.inverted();batch.vertices=[tuple(inv@Vector(v)) for v in batch.vertices]
        temp=batch.commit();mesh=temp.data;bpy.data.objects.remove(temp,do_unlink=True)
        previous=old.data;old.data=mesh
        if previous.users==0 and not previous.use_fake_user:bpy.data.meshes.remove(previous)
        old['reconstruction_scope']='photo-informed terminal screen density; precise aperture pattern inferred'
    # Furniture microdetails in selected inferred office bay only.
    for desk in [o for o in scene.objects if o.type=='MESH' and 'Office | oak desk' in o.name]:
        co=[desk.matrix_world@Vector(v) for v in desk.bound_box]
        lo=[min(v[i] for v in co) for i in range(3)];hi=[max(v[i] for v in co) for i in range(3)]
        x=(lo[0]+hi[0])/2;y=(lo[1]+hi[1])/2;z=hi[2]
        _box('Office | keyboard',(x-.22,y-.14,z+.002),(x+.22,y-.03,z+.019),root,black,.008)
        keys=MeshBatch('FD | Office keyboard keys',root,white)
        for j in range(4):
            for i in range(12):keys.add_box((x-.206+i*.034,y-.13+j*.022,z+.020),(x-.184+i*.034,y-.113+j*.022,z+.023))
        keys.commit()
        _box('Office | mouse',(x+.29,y-.12,z+.005),(x+.35,y-.01,z+.035),root,black,.025)
        _box('Office | desk document',(x-.57,y-.15,z+.004),(x-.36,y+.145,z+.006),root,white)
        _box('Office | monitor stand foot',(x-.18,y+.22,z),(x+.18,y+.38,z+.025),root,black,.008)
        _box('Office | monitor stand stem',(x-.025,y+.25,z+.02),(x+.025,y+.32,z+.22),root,black,.008)
    # A practical light inside the open lift cab.
    d=bpy.data.lights.new('FD | Lift cab soft ceiling','AREA');d.energy=65;d.color=(1,.90,.75);d.shape='RECTANGLE';d.size=1.4;d.size_y=1.8
    o=bpy.data.objects.new(d.name,d);root.objects.link(o);o.location=(23.55,-6.3,2.68);o['sdb_fixture']=True
    # Keep new office components attached to the original movable tower parent.
    tower=bpy.data.objects.get('Tower North 03 Root')
    if tower:
        coll=bpy.data.collections.get('PI | North03 office fitout')
        items=list(coll.all_objects) if coll else []
        items += [o for o in root.objects if 'Office |' in o.name]
        if bpy.data.objects.get('CAM Office'):items.append(bpy.data.objects['CAM Office'])
        for ob in items:
            world=ob.matrix_world.copy();ob.parent=tower;ob.matrix_parent_inverse=tower.matrix_world.inverted();ob.matrix_world=world
    # Near courtyard turf benefits from actual small grass blades. Draw only
    # above exposed turf; BVH rejects covered stone paths and planting beds.
    from mathutils.bvhtree import BVHTree
    turf=bpy.data.objects.get('Polish Site | Court 01 turf plane')
    if turf:
        refs=[o for o in bpy.data.objects if 'Court 01' in o.name and o.type=='MESH' and any(k in o.name for k in ('walk','band','mulch','pocket','basin','apron'))]
        trees=[BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(f.vertices) for f in o.data.polygons]) for o in refs]
        top=max(v.co.z for v in turf.data.vertices);points=[v.co.copy() for v in turf.data.vertices if abs(v.co.z-top)<.001]
        xmin=min(v.x for v in points);xmax=max(v.x for v in points);ymin=min(v.y for v in points);ymax=max(v.y for v in points)
        def inside(x,y):
            hit=False;j=len(points)-1
            for i,p in enumerate(points):
                q=points[j]
                if (p.y>y)!=(q.y>y) and x<(q.x-p.x)*(y-p.y)/(q.y-p.y)+p.x:hit=not hit
                j=i
            return hit
        rng=random.Random(934);vs=[];fs=[];tones=[]
        # Tufts contain fine bent blades, rather than isolated broad triangles.
        # Concentrate density near the still camera without filling paving/beds.
        for k in range(65000):
            x=rng.uniform(xmin,xmax);y=rng.uniform(ymin,ymax)
            if not inside(x,y) or any(t.ray_cast(Vector((x,y,1)),Vector((0,0,-1)),1)[0] is not None for t in trees):continue
            for blade in range(12 if y>70 else 5):
                a=rng.random()*math.tau;r=rng.random()*.035
                xx=x+r*math.cos(a);yy=y+r*math.sin(a)
                w=rng.uniform(.0009,.002);h=rng.uniform(.023,.050);lean=rng.uniform(.006,.018)
                u=Vector((math.cos(a)*w,math.sin(a)*w,0));b=Vector((xx,yy,top-.002))
                bend=Vector((-math.sin(a)*lean,math.cos(a)*lean,0))
                mid=b+bend*.25+Vector((0,0,h*.58));tip=b+bend+Vector((0,0,h))
                i=len(vs);vs.extend([tuple(b-u),tuple(b+u),tuple(mid-u*.62),tuple(mid+u*.62),tuple(tip)])
                fs.extend([(i,i+1,i+3,i+2),(i+2,i+3,i+4)])
                tone=rng.choices([0,1,2],[60,32,8])[0];tones.extend([tone,tone])
        blade_mat=material('Polish Site | Mown grass blade',base_color=(.071,.132,.027,1),roughness=.8)
        grass=_mesh('Courtyard | fine turf blades',vs,fs,root,blade_mat)
        for name in ('Polish Site | Leaf olive','Polish Site | Dry grass'):grass.data.materials.append(bpy.data.materials[name])
        for polygon,tone in zip(grass.data.polygons,tones):polygon.material_index=tone;polygon.use_smooth=True
    # Low circular ground uplights on the feature flare walls for dusk still.
    for x,y in ((167,35),(177,20),(182,3),(180,-17),(170,-37)):
        _tube('Flare | recessed uplight can',(x,y,.15),(x,y,.22),.12,root,metal,24)
        d=bpy.data.lights.new('FD | Flare ground uplight','SPOT');d.energy=0;d.color=(1,.57,.28);d.spot_size=math.radians(62);d.spot_blend=.65;d.shadow_soft_size=.18
        o=bpy.data.objects.new(d.name,d);root.objects.link(o);o.location=(x,y,.3);point_at(o,(x-6,y,24));o['sdb_fixture']=True;o['sdb_day_energy']=0;o['sdb_dusk_energy']=1100
    # Representative recessed wall washers illuminate the exposed Club face.
    # Lighting positions are a visualization assumption, not surveyed fixtures.
    for angle in (35,65,95):
        a=math.radians(angle);x=cx+19.2*math.cos(a);y=cy+25.5*math.sin(a)
        _tube('Club | recessed wall washer',(x,y,.15),(x,y,.20),.10,root,metal,24)
        d=bpy.data.lights.new('FD | Club architectural wall wash','SPOT');d.energy=0;d.color=(1,.72,.46)
        d.spot_size=math.radians(72);d.spot_blend=.7;d.shadow_soft_size=.12
        o=bpy.data.objects.new(d.name,d);root.objects.link(o);o.location=(x,y,.26)
        point_at(o,(cx+17.8*math.cos(a),cy+23.8*math.sin(a),7.5))
        o['sdb_fixture']=True;o['sdb_day_energy']=0;o['sdb_dusk_energy']=500
    cam=camera('CAM Diamond Club',location=(205,133,9),target=(150,55,9),focal_length=30,collection=root)
    cam.data.clip_end=2000
    return {'club_opening':'north photographic approach','club_shell':'hollow','camera':cam.name}
