# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and render the reference-informed Surat Diamond Bourse reconstruction.

Run in Blender's Python Console:
  p = '/absolute/path/to/build_sdb.py'
  exec(compile(open(p).read(), p, 'exec'), {'__file__': p, '__name__': '__main__'})
Configuration is read from job.json beside this file. No third-party libraries.
"""
import bpy, sys, os, json, math, traceback, importlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import sdb_utils as U
import sdb_architecture as A
importlib.reload(U)
importlib.reload(A)

JOB = json.loads((SCRIPT_DIR/'job.json').read_text()) if (SCRIPT_DIR/'job.json').exists() else {'phase':'massing'}
LOG = PROJECT / 'build_status.json'

def status(stage, **kw):
    LOG.write_text(json.dumps({'stage':stage, **kw}, indent=2))
    print('SDB:',stage,flush=True)

def setup_presentation(collections, draft=False):
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC'
    scene.unit_settings.scale_length=1.0
    scene.render.engine='CYCLES'
    scene.cycles.samples=32 if draft else 96
    scene.cycles.use_denoising=True
    scene.cycles.max_bounces=6
    scene.cycles.diffuse_bounces=3
    scene.cycles.glossy_bounces=3
    scene.cycles.transmission_bounces=3
    try:
        pref=bpy.context.preferences.addons['cycles'].preferences
        pref.compute_device_type='METAL'
        pref.get_devices()
        found=False
        for dev in pref.devices:
            dev.use=dev.type=='METAL'
            if dev.use: found=True
        scene.cycles.device='GPU' if found else 'CPU'
    except Exception:
        scene.cycles.device='CPU'
    scene.render.resolution_x=1600
    scene.render.resolution_y=1000
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.render.image_settings.color_depth='8'
    scene.render.film_transparent=False
    scene.render.use_file_extension=True
    scene.view_settings.view_transform='AgX'
    try: scene.view_settings.look='AgX - Medium High Contrast'
    except: pass
    scene.view_settings.exposure=-0.6
    world=bpy.data.worlds.new('Surat | clear warm daylight')
    scene.world=world
    world.use_nodes=True
    nodes=world.node_tree.nodes
    sky=nodes.new('ShaderNodeTexSky')
    sky_types={e.identifier for e in sky.bl_rna.properties['sky_type'].enum_items}
    sky.sky_type='NISHITA' if 'NISHITA' in sky_types else 'SINGLE_SCATTERING'
    sky.sun_elevation=math.radians(36)
    sky.sun_rotation=math.radians(125)
    sky.sun_disc=True
    sky.sun_intensity=0.8
    sky.air_density=1.0
    if hasattr(sky,'dust_density'): sky.dust_density=0.55
    elif hasattr(sky,'aerosol_density'): sky.aerosol_density=0.55
    world.node_tree.links.new(sky.outputs['Color'],nodes.get('Background').inputs['Color'])
    nodes.get('Background').inputs['Strength'].default_value=0.32
    lc=collections['Lighting']
    data=bpy.data.lights.new('Sun | afternoon west light','SUN')
    data.energy=2.2
    data.angle=math.radians(2)
    obj=bpy.data.objects.new('Sun | afternoon west light',data)
    lc.objects.link(obj)
    obj.location=(200,160,300)
    U.point_at(obj,(0,0,0))
    cc=collections['Cameras']
    cameras={}
    specs=[
        ('Aerial',(460,440,370),(0,4,26),44),
        ('Hero',(340,330,70),(30,15,32),46),
        ('Courtyard',(-86,104,2.0),(-82,20,26),22),
        ('Spine entrance',(251,5,3.0),(144,15,34),24),
        ('Site plan',(0,0,680),(0,0,0),50),
        ('Facade reference',(-25,260,50),(-25,8,34),55),
    ]
    for name,loc,target,lens in specs:
        cameras[name]=U.camera('CAM '+name,location=loc,target=target,collection=cc,focal_length=lens)
        cameras[name].data.clip_end=5000
        cameras[name].data.lens=lens
    cameras['Site plan'].data.type='ORTHO'
    cameras['Site plan'].data.ortho_scale=490
    scene.camera=cameras['Aerial']
    return cameras

def finish_materials():
    # Real-scale joints and restrained stone variation, generated in object space.
    for name,scale in [('SDB Sandstone Cream',0.75),('SDB Red Granite',0.85)]:
        mat=bpy.data.materials.get(name)
        if not mat: continue
        nt=mat.node_tree; n=nt.nodes; p=n.get('Principled BSDF')
        base=tuple(p.inputs['Base Color'].default_value)
        tex=n.new('ShaderNodeTexNoise'); tex.name='Subtle mineral variation'
        tex.inputs['Scale'].default_value=2.0
        tex.inputs['Detail'].default_value=2.0
        coord=n.new('ShaderNodeTexCoord')
        nt.links.new(coord.outputs['Object'],tex.inputs['Vector'])
        ramp=n.new('ShaderNodeValToRGB'); ramp.name='Stone color range'
        ramp.color_ramp.elements[0].position=0.18
        ramp.color_ramp.elements[0].color=tuple(v*.84 for v in base[:3])+(1,)
        ramp.color_ramp.elements[1].position=0.82
        ramp.color_ramp.elements[1].color=tuple(min(1,v*1.14) for v in base[:3])+(1,)
        nt.links.new(tex.outputs['Fac'],ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'],p.inputs['Base Color'])
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10
        bump.inputs['Distance'].default_value=.008
        nt.links.new(tex.outputs['Fac'],bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'],p.inputs['Normal'])
    mat=bpy.data.materials.get('SDB Dark Blue Glazing')
    if mat:
        p=mat.node_tree.nodes.get('Principled BSDF')
        p.inputs['Metallic'].default_value=.48
        p.inputs['Roughness'].default_value=.16

def save(name):
    path=PROJECT/name
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    status('saved',file=str(path))

def render(cameras, keys, prefix='', width=1600, samples=96):
    scene=bpy.context.scene
    for name in keys:
        scene.camera=cameras[name]
        scene.view_settings.exposure=.35 if name=='Courtyard' else -.6
        scene.render.resolution_x=width
        scene.render.resolution_y=round(width*.625)
        scene.cycles.samples=samples
        scene.render.filepath=str(PROJECT/'renders'/(prefix+name.lower().replace(' ','_')+'.png'))
        status('rendering',camera=name,path=scene.render.filepath)
        bpy.ops.render.render(write_still=True)
        status('rendered',camera=name,path=scene.render.filepath)

def main():
    phase=JOB.get('phase','massing')
    status('starting',phase=phase)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # Rebuild removes generated collections only after deleting scene objects.
    for coll in list(bpy.data.collections):
        if coll.users==0: bpy.data.collections.remove(coll)
    collections=U.create_collection_tree()
    mats=U.build_material_library()
    params=dict(A.PARAMS)
    params.update(JOB.get('params',{}))
    result=A.build_massing(params,collections,mats)
    cameras=setup_presentation(collections,draft=phase=='massing')
    neutral=U.material('Clay | warm grey',base_color=(.55,.53,.49,1),roughness=.8)
    U.MeshBatch('Site datum',collections['Podium'],mats['SDB Concrete']).add_box((-225,-128,-.65),(225,130,-.05)).commit()
    if phase=='massing':
        bpy.context.view_layer.material_override=neutral
        save(JOB.get('save','checkpoints/SDB_01_research_blockout.blend'))
        render(cameras,JOB.get('cameras',['Aerial','Hero']),prefix=JOB.get('prefix','clay_'),width=1000,samples=24)
    else:
        if hasattr(A,'build_structure'):
            A.build_structure(params,collections,mats)
        save('checkpoints/SDB_03_architecture.blend')
        A.build_details(params,collections,mats)
        finish_materials()
        save('checkpoints/SDB_04_facades.blend')
        import sdb_site as S;importlib.reload(S)
        S.build_site(params,collections,mats)
        save('checkpoints/SDB_05_site.blend')
        import sdb_refine as R;importlib.reload(R)
        R.apply(params,collections,mats)
        # Put each tower pivot at its own spine junction, preserving geometry.
        for spec in params['towers']:
            root=bpy.data.objects.get('Tower '+spec['name']+' Root')
            if root:
                children=[(o,o.matrix_world.copy()) for o in root.children]
                root.location=(spec['x'],A.north_spine_y(spec['x']) if spec['side']=='north' else -9.5,0)
                bpy.context.view_layer.update()
                for child,world_matrix in children:child.matrix_world=world_matrix
        bpy.context.view_layer.material_override=None
        # Store source code and assumptions inside the .blend for portability.
        for src in SCRIPT_DIR.glob('*.py'):
            txt=bpy.data.texts.get(src.name) or bpy.data.texts.new(src.name)
            txt.clear();txt.write(src.read_text())
        for src in PROJECT.glob('*.md'):
            txt=bpy.data.texts.get(src.name) or bpy.data.texts.new(src.name)
            txt.clear();txt.write(src.read_text())
        bpy.context.scene['Model purpose']='Exterior architectural reconstruction from public references; not a surveyed BIM.'
        bpy.context.scene['Dimensions']='Metres. Ground floor 6.4m; office floor spacing3.9m. Plan lengths estimated.'
        bpy.context.scene['Tower count']=9
        scene=bpy.context.scene
        scene.camera=cameras['Aerial']
        scene.view_settings.exposure=-.6
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_distance=460
                area.spaces.active.clip_end=5000
        save(JOB.get('save','Surat Diamond Bourse.blend'))
        render(cameras,JOB.get('cameras',['Aerial','Hero','Courtyard']),prefix=JOB.get('prefix',''),width=JOB.get('width',2000),samples=JOB.get('samples',96))
        scene.camera=cameras['Aerial']
        scene.view_settings.exposure=-.6
        scene.frame_set(1)
        if JOB.get('final',False):
            # Remove unused bundled brush links left by a prior sculpt workspace.
            for brush in list(bpy.data.brushes):
                if brush.library and brush.users==0:
                    bpy.data.brushes.remove(brush)
            for library in list(bpy.data.libraries):
                if not any(item.library==library for item in bpy.data.all_ids):
                    bpy.data.libraries.remove(library)
            scene.render.filepath='//renders/aerial.png'
            scene.camera.data.passepartout_alpha=1
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type=='CONSOLE':
                        area.type='VIEW_3D'
                    if area.type=='VIEW_3D':
                        area.spaces.active.region_3d.view_perspective='CAMERA'
                        area.spaces.active.region_3d.view_camera_zoom=22
                        area.spaces.active.clip_end=5000
                        area.spaces.active.shading.type='SOLID'
                        area.spaces.active.shading.color_type='MATERIAL'
                        area.spaces.active.overlay.show_overlays=False
            save('Surat Diamond Bourse.blend')
        audit={'tower_roots':[o.name for o in bpy.data.objects if o.type=='EMPTY' and o.name.startswith('Tower ') and o.name.endswith(' Root')],
               'objects':len(bpy.context.scene.objects),'mesh_objects':sum(o.type=='MESH' for o in bpy.context.scene.objects),
               'unique_meshes_used':len({o.data.name for o in bpy.context.scene.objects if o.type=='MESH'}),
               'cameras':[o.name for o in bpy.context.scene.objects if o.type=='CAMERA'],
               'render_engine':scene.render.engine,'render_device':scene.cycles.device,
               'render_resolution':[scene.render.resolution_x,scene.render.resolution_y],
               'samples':scene.cycles.samples,'external_images':[im.filepath for im in bpy.data.images if im.source=='FILE' and im.users>0]}
        (PROJECT/'scene_audit.json').write_text(json.dumps(audit,indent=2))
    status('complete',phase=phase,objects=len(bpy.data.objects),meshes=len(bpy.data.meshes))

try:
    main()
except Exception:
    status('error',traceback=traceback.format_exc())
    traceback.print_exc()
    raise
