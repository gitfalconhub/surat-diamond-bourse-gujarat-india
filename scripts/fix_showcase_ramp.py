# SPDX-License-Identifier: GPL-3.0-or-later
"""Reframe the ramp from beyond the overhead sign; review without saving yet."""
from pathlib import Path
import bpy, json, time, traceback
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'video'
scene = bpy.context.scene
settings = json.loads((VIDEO / 'showcase_settings.json').read_text())
shot = settings['shots'][10]
camera = bpy.data.objects[shot['camera']]
result = {'started': time.time(), 'complete': False, 'frames': []}
status_path = ROOT / 'work' / 'showcase_ramp_fix.json'
def record():
    status_path.write_text(json.dumps(result, indent=2))

try:
    assert scene.frame_end == 2100 and len(scene.timeline_markers) == 14
    previous = None
    for frame in range(shot['start'] - 1, shot['end'] + 2):
        t = max(0, min(1, (frame - shot['start']) / (shot['end'] - shot['start'])))
        u = t * t * (3 - 2 * t)
        camera.location = Vector((-190, -113, 1.7)).lerp(Vector((-190, -105, 1.23)), u)
        target = Vector((-190, -82, -1.4)).lerp(Vector((-190, -74, -2.2)), u)
        rotation = (target - camera.location).to_track_quat('-Z', 'Y')
        if previous is not None and rotation.dot(previous) < 0:
            rotation.negate()
        camera.rotation_quaternion = rotation
        previous = rotation.copy()
        camera.keyframe_insert('location', frame=frame)
        camera.keyframe_insert('rotation_quaternion', frame=frame)
    for layer in camera.animation_data.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = 'LINEAR'
    hits = []
    for frame in range(shot['start'], shot['end'] + 1):
        scene.frame_set(frame)
        origin = camera.matrix_world.translation.copy()
        deps = bpy.context.evaluated_depsgraph_get()
        for direction in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            hit, loc, normal, face, obj, matrix = scene.ray_cast(deps, origin, Vector(direction), distance=.22)
            if hit and not obj.hide_render:
                hits.append({'frame': frame, 'object': obj.name})
    assert not hits, hits
    result['clearance_samples'] = shot['end'] - shot['start'] + 1
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.cycles.samples = 32
    scene.cycles.adaptive_threshold = .1
    scene.cycles.adaptive_min_samples = 8
    scene.render.image_settings.color_depth = '8'
    scene.render.use_motion_blur = False
    for frame in (shot['start'], (shot['start'] + shot['end']) // 2, shot['end']):
        scene.frame_set(frame)
        assert scene.camera == camera
        path = VIDEO / 'review' / f'ramp_fixed_{frame:04d}.png'
        scene.render.filepath = str(path)
        record()
        bpy.ops.render.render(write_still=True)
        result['frames'].append({'frame': frame, 'path': str(path), 'location': list(camera.location)})
        record()
    result['complete'] = True
except Exception:
    result['error'] = traceback.format_exc()
    print(result['error'])
finally:
    scene.render.resolution_x = 2560
    scene.render.resolution_y = 1440
    scene.cycles.samples = 512
    scene.cycles.adaptive_threshold = .005
    scene.cycles.adaptive_min_samples = 32
    scene.render.image_settings.color_depth = '16'
    scene.render.use_motion_blur = True
    scene.render.filepath = '//frames/frame_'
    scene.frame_set(1)
    result['finished'] = time.time()
    record()
