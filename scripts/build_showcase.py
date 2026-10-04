# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a portable 70 second camera film from the polished model.

Run inside Blender. Preserves the authoritative main .blend on disk.
Only a separate video/Surat Diamond Bourse - Showcase.blend is saved.
"""
from pathlib import Path
import bpy,math,json,sys,time,traceback,hashlib
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import polish_materials as PM
VIDEO=ROOT/'video';VIDEO.mkdir(exist_ok=True)
STATUS=ROOT/'work'/'showcase_build.json'
main=ROOT/'Surat Diamond Bourse.blend'
source_hash=hashlib.sha256(main.read_bytes()).hexdigest()
status={'started':time.time(),'complete':False,'source_sha256':source_hash}
def record(): STATUS.write_text(json.dumps(status,indent=2))
def curves(id):
    ad=getattr(id,'animation_data',None)
    if not ad or not ad.action:return []
    action=ad.action
    if hasattr(action,'fcurves'):return list(action.fcurves)
    result=[]
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip,'channelbags',[]):result.extend(bag.fcurves)
    if not result:raise RuntimeError('Cannot locate action curves: '+action.name)
    return result
def interpolation(id,mode):
    for fc in curves(id):
        for k in fc.keyframe_points:k.interpolation=mode
def day_dusk(scene,cut):
    PM.configure_daylight(scene)
    world=scene.world;nt=world.node_tree
    out=nt.nodes.get('World Output');day=nt.nodes.get('Daylight sky strength')
    tex=nt.nodes.new('ShaderNodeTexCoord');tex.name='Showcase twilight direction'
    sep=nt.nodes.new('ShaderNodeSeparateXYZ');nt.links.new(tex.outputs['Normal'],sep.inputs[0])
    height=PM._math(nt,'MULTIPLY',sep.outputs['Z'],-1)
    fac=PM._scalar_range(nt,height,0,1,'Showcase horizon to zenith')
    colour=PM._ramp(nt,fac,(.095,.111,.150),(.012,.025,.064),'Showcase blue-hour atmosphere')
    night=nt.nodes.new('ShaderNodeBackground');night.name='Showcase twilight';night.inputs['Strength'].default_value=.42
    nt.links.new(colour,night.inputs['Color'])
    mix=nt.nodes.new('ShaderNodeMixShader');mix.name='Showcase day and dusk cut'
    nt.links.new(day.outputs[0],mix.inputs[1]);nt.links.new(night.outputs[0],mix.inputs[2])
    nt.links.new(mix.outputs[0],out.inputs['Surface'])
    for f,v in ((1,0),(cut-1,0),(cut,1),(2100,1)):
        mix.inputs[0].default_value=v;mix.inputs[0].keyframe_insert('default_value',frame=f)
    interpolation(nt,'CONSTANT')
    sun=bpy.data.objects['SDB Polish | sole sun'];sun.hide_render=False
    for f,v in ((1,3),(cut-1,3),(cut,0),(2100,0)):
        sun.data.energy=v;sun.data.keyframe_insert('energy',frame=f)
    interpolation(sun.data,'CONSTANT')
    seen=set()
    for obj in scene.objects:
        if obj.type!='LIGHT' or not obj.get('sdb_fixture') or obj.data.as_pointer() in seen:continue
        seen.add(obj.data.as_pointer())
        day_energy=obj.get('sdb_day_energy',obj.data.energy)
        night_energy=obj.get('sdb_dusk_energy',day_energy*1.7)
        for f,v in ((1,day_energy),(cut-1,day_energy),(cut,night_energy),(2100,night_energy)):
            obj.data.energy=v;obj.data.keyframe_insert('energy',frame=f)
        interpolation(obj.data,'CONSTANT')
    for mat in bpy.data.materials:
        if not mat.use_nodes or 'sdb_day_emission' not in mat:continue
        p=mat.node_tree.nodes.get('Principled BSDF')
        if p is None:continue
        sock=p.inputs.get('Emission Strength')
        if sock is None:continue
        for f,v in ((1,mat['sdb_day_emission']),(cut-1,mat['sdb_day_emission']),
                    (cut,mat.get('sdb_dusk_emission',mat['sdb_day_emission'])),(2100,mat.get('sdb_dusk_emission',mat['sdb_day_emission']))):
            sock.default_value=v;sock.keyframe_insert('default_value',frame=f)
        interpolation(mat.node_tree,'CONSTANT')
    return len(seen)

SHOTS=[
 ('01 Hero approach','CAM Hero',5,(348,342,72),(330,315,67),(30,15,32),(30,15,32)),
 ('02 Aerial arc','CAM Aerial',8,(460,440,370),(505,382,350),(0,4,26),(0,4,26)),
 ('03 Facade track','CAM Facade reference',6,(-25,260,50),(3,260,50),(-25,8,34),(3,8,34)),
 ('04 Courtyard walk','CAM Courtyard detail',7,(-82,99,1.85),(-84,94,1.85),(-88,60,2.7),(-88,57,2.7)),
 ('05 Public hall','CAM Lobby',6,(-46,0,1.9),(-41,0,1.9),(8,0,2.45),(13,0,2.45)),
 ('06 Planted corridor','CAM Planted Corridor',4,(-22,1.75,1.9),(-19,1.75,1.9),(16,4.1,2.2),(19,4.1,2.2)),
 ('07 Lift cabin','CAM Lift Lobby',4,(20.6,-.7,1.8),(20.4,-1.3,1.8),(25,-4.45,1.8),(25,-4.45,1.8)),
 ('08 Public stair','CAM Stair',3,(30,-1.5,2),(31,-1.5,2),(39,1,4.3),(39,1,4.3)),
 ('09 Planted gallery','CAM Atrium',6,(-45,-3.2,8.05),(-43.5,-3.2,8.05),(-32,.8,9.8),(-30.5,.8,9.8)),
 ('10 Representative office','CAM Office',5,(3,10.5,8.15),(4,10.5,8.15),(2.5,23,8.1),(3.5,23,8.1)),
 ('11 Parking ramp approach','CAM Parking Ramp',3,(-190,-113,1.7),(-190,-105,1.23),(-190,-82,-1.4),(-190,-74,-2.2)),
 ('12 Parking aisle','CAM Parking',3,(-155,-66,-2.6),(-153,-66,-2.6),(-109,-77,-2.4),(-107,-77,-2.4)),
 ('13 Parking lift core','CAM Parking Core',3,(16,2,-2.6),(16.5,1.5,-2.6),(25,-5,-2.7),(25,-5,-2.7)),
 ('14 Diamond Club dusk','CAM Diamond Club',7,(205,133,9),(194.6,139.4,9),(150,55,9),(150,55,9)),
]

try:
    record();s=bpy.context.scene
    # A pristine source is required; this script is not a procedural rebuild.
    assert len(bpy.data.actions)==0,'Load the polished main file before building the film.'
    assert len([o for o in s.objects if o.name.startswith('Tower ') and o.name.endswith(' Root')])==9
    coll=bpy.data.collections.new('Showcase | Animated cameras');s.collection.children.link(coll)
    s.frame_start=1;s.frame_end=2100;s.render.fps=30;s.render.fps_base=1
    s.render.resolution_x=2560;s.render.resolution_y=1440;s.render.resolution_percentage=100
    fixture_count=day_dusk(s,1891)
    s.render.engine='CYCLES';s.cycles.samples=512;s.cycles.use_adaptive_sampling=True
    s.cycles.adaptive_threshold=.005;s.cycles.adaptive_min_samples=32
    s.cycles.max_bounces=12;s.cycles.diffuse_bounces=6;s.cycles.glossy_bounces=6
    s.cycles.transmission_bounces=8;s.cycles.transparent_max_bounces=12
    s.cycles.use_denoising=True;s.cycles.denoiser='OPENIMAGEDENOISE'
    s.cycles.denoising_prefilter='ACCURATE';s.cycles.denoising_quality='HIGH'
    s.cycles.seed=42;s.cycles.use_animated_seed=False
    s.render.use_motion_blur=True;s.render.motion_blur_shutter=.35
    s.render.use_persistent_data=True;s.render.use_sequencer=False
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
    s.render.image_settings.color_depth='16';s.render.image_settings.compression=20
    s.render.filepath='//frames/frame_';s.render.use_simplify=False
    s.timeline_markers.clear();shots=[];frame=1
    for title,source,duration,a,b,ta,tb in SHOTS:
        src=bpy.data.objects[source];data=src.data.copy();data.name='Showcase | '+title
        data.dof.use_dof=False;data.passepartout_alpha=1
        cam=bpy.data.objects.new('Showcase | '+title,data);coll.objects.link(cam)
        cam.rotation_mode='QUATERNION';cam['source_camera']=source
        end=frame+duration*30-1
        # Holds outside this shot keep motion blur at cuts self-contained.
        last_q=None
        for f in range(max(0,frame-1),min(2101,end+1)+1):
            t=max(0,min(1,(f-frame)/(end-frame)));u=t*t*(3-2*t)
            if 'Aerial arc' in title:
                center=Vector((0,4,0));pa=Vector(a)-center;pb=Vector(b)-center
                theta_a=math.atan2(pa.y,pa.x);theta_b=math.atan2(pb.y,pb.x)
                theta=theta_a+(theta_b-theta_a)*u
                radius=math.hypot(pa.x,pa.y)+(math.hypot(pb.x,pb.y)-math.hypot(pa.x,pa.y))*u
                cam.location=(center.x+radius*math.cos(theta),center.y+radius*math.sin(theta),a[2]+(b[2]-a[2])*u)
            elif 'Club dusk' in title:
                center=Vector((150,55,0));radius=math.hypot(a[0]-150,a[1]-55)
                angle=math.atan2(a[1]-55,a[0]-150)+math.radians(8)*u
                cam.location=(150+radius*math.cos(angle),55+radius*math.sin(angle),9)
            else:cam.location=Vector(a).lerp(Vector(b),u)
            target=Vector(ta).lerp(Vector(tb),u)
            q=(target-cam.location).to_track_quat('-Z','Y')
            if last_q and q.dot(last_q)<0:q.negate()
            cam.rotation_quaternion=q;last_q=q.copy()
            cam.keyframe_insert('location',frame=f);cam.keyframe_insert('rotation_quaternion',frame=f)
        interpolation(cam,'LINEAR')
        marker=s.timeline_markers.new(title,frame=frame);marker.camera=cam
        exposure=PM.exposure_for_camera(source,dusk=title.startswith('14 '))
        for f in (frame,end):
            s.view_settings.exposure=exposure;s.view_settings.keyframe_insert('exposure',frame=f)
        shots.append({'title':title,'camera':cam.name,'source':source,'start':frame,'end':end,
                      'seconds':duration,'lens':data.lens,'exposure':exposure})
        frame=end+1
    interpolation(s,'CONSTANT')
    assert frame==2101
    s.camera=bpy.data.objects[shots[0]['camera']];s.frame_set(1)
    # Review centerline clearance at 11 samples for every shot.
    near=[];poses=[]
    directions=[Vector(v) for v in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
    for shot in shots:
        cam=bpy.data.objects[shot['camera']]
        for i in range(11):
            f=round(shot['start']+(shot['end']-shot['start'])*i/10);s.frame_set(f)
            assert s.camera==cam,(f,s.camera.name,cam.name)
            dg=bpy.context.evaluated_depsgraph_get();origin=cam.matrix_world.translation.copy()
            for direction in directions:
                hit,loc,norm,face,obj,matrix=s.ray_cast(dg,origin,direction,distance=.22)
                if hit and not obj.hide_render:
                    near.append({'shot':shot['title'],'frame':f,'object':obj.name,'distance':(loc-origin).length})
            if i in (0,5,10):poses.append({'shot':shot['title'],'frame':f,'camera':cam.name,'location':list(origin)})
    s.frame_set(1)
    s['Showcase']='70 seconds, 1440p, 30 fps; animated camera markers and saved day/dusk lighting.'
    s['Showcase fidelity']='Reference-led reconstruction; tenant offices and underground circulation include inferred details.'
    s['Showcase render status']='Camera setup prepared; complete movie requires frame rendering and encoding.'
    for path in (Path(__file__),ROOT/'scripts'/'inspect_showcase_runtime.py'):
        t=bpy.data.texts.get(path.name) or bpy.data.texts.new(path.name);t.clear();t.write(path.read_text())
    bpy.ops.file.pack_all()
    for wm in bpy.data.window_managers:
        for w in wm.windows:
            for area in w.screen.areas:
                if area.type=='CONSOLE':area.type='VIEW_3D'
                if area.type=='VIEW_3D':
                    sp=area.spaces.active;sp.overlay.show_overlays=False;sp.show_gizmo=False
                    sp.shading.type='MATERIAL';sp.shading.use_scene_world=True;sp.shading.use_scene_lights=True
                    sp.region_3d.view_perspective='CAMERA';sp.region_3d.view_camera_zoom=0;sp.clip_end=5000
    target=VIDEO/'Surat Diamond Bourse - Showcase.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    assert hashlib.sha256(main.read_bytes()).hexdigest()==source_hash,'Main file changed unexpectedly.'
    settings={'width':2560,'height':1440,'fps':30,'seconds':70,'frame_start':1,'frame_end':2100,
              'engine':'CYCLES','max_samples':512,'adaptive_threshold':.005,'adaptive_min_samples':32,
              'denoising':'OpenImageDenoise High / Accurate','motion_blur_shutter':.35,
              'source_sha256':source_hash,'shots':shots}
    (VIDEO/'showcase_settings.json').write_text(json.dumps(settings,indent=2))
    status.update(complete=True,file=str(target),bytes=target.stat().st_size,shots=shots,
                  review_poses=poses,near_geometry=near,fixture_data_animated=fixture_count,
                  packed_images=sum(bool(i.packed_file) for i in bpy.data.images),actions=len(bpy.data.actions))
except Exception:
    status['error']=traceback.format_exc();print(status['error'])
finally:status['finished']=time.time();record()
