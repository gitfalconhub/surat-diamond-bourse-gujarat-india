# SPDX-License-Identifier: GPL-3.0-or-later
"""Site, landscape and entourage generator for the Surat Diamond Bourse scene.

The public site drawing is a presentation plan rather than a surveyed civil
drawing.  This module therefore keeps its dimensions deliberately readable and
parametric: it establishes the road/courtyard character and scale while the
architectural module remains the authority for the office slabs and spine.
"""

from __future__ import annotations

from math import cos, pi, sin, sqrt
from typing import Any, Iterable

import bpy

from sdb_utils import (
    MeshBatch,
    arc_points,
    clear_collection,
    ensure_collection,
    material,
    mesh_instance,
    polygon_prism,
    shaped_wall,
)


SITE_X0, SITE_X1 = -225.0, 225.0
SITE_Y0, SITE_Y1 = -128.0, 130.0
CLUB_CENTER = (150.0, 55.0)


def _mat(mats: dict[str, bpy.types.Material], name: str, color: tuple[float, float, float, float], roughness: float) -> bpy.types.Material:
    return mats.get(name) or material(name, base_color=color, roughness=roughness)


def _ellipse(center: tuple[float, float], rx: float, ry: float, segments: int = 28) -> list[tuple[float, float]]:
    return [
        (center[0] + rx * cos(2.0 * pi * index / segments), center[1] + ry * sin(2.0 * pi * index / segments))
        for index in range(segments)
    ]


def _vegetation_mesh(
    name: str,
    collection: bpy.types.Collection,
    materials: list[bpy.types.Material],
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    face_materials: list[int],
) -> bpy.types.Object:
    """Create a hidden, shared-mesh vegetation source with material variation."""
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(verts, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.hide_render = True
    obj.hide_viewport = True
    return obj


def _add_tapered_tube(
    verts: list[tuple[float, float, float]], faces: list[tuple[int, ...]], face_materials: list[int],
    start: tuple[float, float, float], end: tuple[float, float, float], radius_start: float, radius_end: float,
    material_index: int, sides: int = 7,
) -> None:
    """Add a low-sided branch or rachis aligned between two arbitrary points."""
    dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
    length = sqrt(dx * dx + dy * dy + dz * dz)
    if length < 0.0001:
        return
    ux, uy, uz = dx / length, dy / length, dz / length
    # A stable perpendicular frame, including for near-vertical tree trunks.
    if abs(uz) < 0.92:
        vx, vy, vz = -uy, ux, 0.0
    else:
        vx, vy, vz = 0.0, -uz, uy
    v_length = sqrt(vx * vx + vy * vy + vz * vz)
    vx, vy, vz = vx / v_length, vy / v_length, vz / v_length
    wx, wy, wz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    base = len(verts)
    for point, radius in ((start, radius_start), (end, radius_end)):
        for side in range(sides):
            angle = 2.0 * pi * side / sides
            verts.append((
                point[0] + radius * (vx * cos(angle) + wx * sin(angle)),
                point[1] + radius * (vy * cos(angle) + wy * sin(angle)),
                point[2] + radius * (vz * cos(angle) + wz * sin(angle)),
            ))
    for side in range(sides):
        next_side = (side + 1) % sides
        faces.append((base + side, base + next_side, base + sides + next_side, base + sides + side))
        face_materials.append(material_index)
    faces.extend((tuple(base + side for side in range(sides - 1, -1, -1)), tuple(base + sides + side for side in range(sides))))
    face_materials.extend((material_index, material_index))


def _add_leaf_plate(
    verts: list[tuple[float, float, float]], faces: list[tuple[int, ...]], face_materials: list[int],
    origin: tuple[float, float, float], heading: float, incline: float, length: float, width: float, material_index: int,
) -> None:
    """Add one curved, double-sided three-segment leaf blade.

    Segmenting the blade prevents the crown from reading as a flat card in the
    aerial view while keeping a repeatable source mesh compact enough to instance.
    """
    base = len(verts)
    lateral = (-sin(heading), cos(heading), 0.0)
    for step in range(4):
        t = step / 3.0
        bend = sin(pi * t) * length * 0.10
        center = (
            origin[0] + cos(heading) * length * t,
            origin[1] + sin(heading) * length * t,
            origin[2] + incline * length * t + bend,
        )
        taper = 1.0 - 0.58 * t
        half_width = width * taper
        verts.append((center[0] - lateral[0] * half_width, center[1] - lateral[1] * half_width, center[2] - lateral[2] * half_width))
        verts.append((center[0] + lateral[0] * half_width, center[1] + lateral[1] * half_width, center[2] + lateral[2] * half_width))
    for step in range(3):
        left, right = base + step * 2, base + step * 2 + 1
        next_left, next_right = left + 2, right + 2
        faces.extend(((left, right, next_right, next_left), (next_left, next_right, right, left)))
        face_materials.extend((material_index, material_index))


def _tree_sources(
    collection: bpy.types.Collection,
    trunk: bpy.types.Material,
    leaves: list[bpy.types.Material],
    palm_leaves: list[bpy.types.Material],
) -> dict[str, bpy.types.Object]:
    """Build highly detailed but shared broadleaf and palm meshes.

    Every placed tree below is a linked-data instance.  The broadleaf source has
    440 leaf sprays, each made from three curved blades (7,920 foliage faces),
    so it reads as a dense organic canopy close up as well as from the aerial view.
    """
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    trunk_points = ((0.0, 0.0, 0.0), (0.04, -0.02, 1.6), (-0.10, 0.08, 3.1), (0.10, -0.05, 4.55), (-0.03, 0.04, 5.65))
    trunk_radii = (0.34, 0.29, 0.24, 0.19, 0.14)
    for index in range(len(trunk_points) - 1):
        _add_tapered_tube(verts, faces, face_materials, trunk_points[index], trunk_points[index + 1], trunk_radii[index], trunk_radii[index + 1], 0, 8)
    # Irregular branches are a genuine part of the shared source instead of an
    # extra trunk plus a floating foliage primitive.
    for index in range(18):
        angle = index * 2.39996 + 0.31 * sin(index * 1.7)
        start_z = 3.35 + (index % 6) * 0.36
        start = (0.06 * sin(index), 0.06 * cos(index * 1.4), start_z)
        reach = 1.15 + 0.75 * ((index * 37) % 11) / 10.0
        middle = (cos(angle) * reach * .48, sin(angle) * reach * .48, start_z + .36 + .22 * sin(index))
        end = (cos(angle) * reach, sin(angle) * reach, start_z + .70 + .35 * cos(index * .7))
        _add_tapered_tube(verts, faces, face_materials, start, middle, .12, .075, 0, 6)
        _add_tapered_tube(verts, faces, face_materials, middle, end, .075, .035, 0, 5)
    for index in range(440):
        t = (index + .5) / 440.0
        shell_z = 1.0 - 2.0 * t
        radius = sqrt(max(0.0, 1.0 - shell_z * shell_z))
        angle = index * 2.39996323
        center = (2.42 * radius * cos(angle), 2.18 * radius * sin(angle), 5.88 + 1.62 * shell_z)
        tone = 1 + ((index * 17 + index // 9) % 3)
        # Three differently oriented blades give every spray volume, shadow and
        # a small amount of visible color variation without per-tree duplication.
        for blade in range(3):
            heading = angle + blade * 2.094 + .32 * sin(index * (blade + 1) * .71)
            _add_leaf_plate(
                verts, faces, face_materials, center, heading,
                .55 * sin(index * .43 + blade * 1.9),
                .48 + .20 * ((index + blade * 5) % 7) / 6.0,
                .105 + .045 * ((index + blade * 3) % 5) / 4.0, tone,
            )
    broadleaf = _vegetation_mesh("Broadleaf Tree Source | branches and individual leaves", collection, [trunk, *leaves], verts, faces, face_materials)

    palm_verts: list[tuple[float, float, float]] = []
    palm_faces: list[tuple[int, ...]] = []
    palm_face_materials: list[int] = []
    palm_points: list[tuple[float, float, float]] = []
    for step in range(17):
        t = step / 16.0
        palm_points.append((.14 * sin(t * 6.0), .11 * sin(t * 4.0 + .4), 8.15 * t))
    for index in range(16):
        _add_tapered_tube(palm_verts, palm_faces, palm_face_materials, palm_points[index], palm_points[index + 1], .29 - .11 * index / 16.0, .29 - .11 * (index + 1) / 16.0, 0, 9)
    for frond in range(12):
        angle = 2.0 * pi * frond / 12.0
        rachis: list[tuple[float, float, float]] = []
        for step in range(9):
            t = step / 8.0
            radius = .18 + 4.45 * t
            rachis.append((
                palm_points[-1][0] + radius * cos(angle), palm_points[-1][1] + radius * sin(angle),
                8.17 + .20 * sin(pi * t) - .82 * t * t,
            ))
        for step in range(8):
            _add_tapered_tube(palm_verts, palm_faces, palm_face_materials, rachis[step], rachis[step + 1], .060 - .040 * step / 8.0, .060 - .040 * (step + 1) / 8.0, 1 + (frond % 3), 5)
        for step in range(1, 8):
            t = step / 8.0
            blade_length = 1.16 - .52 * t
            for side in (-1.0, 1.0):
                _add_leaf_plate(
                    palm_verts, palm_faces, palm_face_materials, rachis[step],
                    angle + side * (1.22 - .32 * t), -.12 - .22 * t,
                    blade_length, .070 - .022 * t, 1 + ((frond + step) % 3),
                )
    palm = _vegetation_mesh("Palm Tree Source | ringed trunk and curved leaflets", collection, [trunk, *palm_leaves], palm_verts, palm_faces, palm_face_materials)
    return {"broadleaf": broadleaf, "palm": palm}


def _place_tree(sources: dict[str, bpy.types.Object], collection: bpy.types.Collection, x: float, y: float, variant: int, scale: float = 1.0) -> None:
    tree = mesh_instance(f"Broadleaf tree {variant + 1:02d}", sources["broadleaf"], location=(x, y, 0.08), scale=(scale, scale, scale), collection=collection)
    tree.rotation_euler[2] = (variant * .79 + x * .027 + y * .019) % (2.0 * pi)
    tree["sdb_component"] = "broadleaf_tree"


def _place_palm(sources: dict[str, bpy.types.Object], collection: bpy.types.Collection, x: float, y: float, scale: float = 1.0) -> None:
    palm = mesh_instance("Landscape palm", sources["palm"], location=(x, y, 0.08), scale=(scale, scale, scale), collection=collection)
    palm.rotation_euler[2] = (x * 0.13 + y * 0.07) % (2.0 * pi)
    palm["sdb_component"] = "palm_tree"


def _road_and_markings(site: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> None:
    asphalt = _mat(mats, "SDB Asphalt", (0.045, 0.050, 0.047, 1.0), 0.88)
    paint = _mat(mats, "SDB Road Paint", (0.84, 0.78, 0.61, 1.0), 0.62)
    curb = _mat(mats, "SDB Pale Curb", (0.58, 0.56, 0.51, 1.0), 0.76)
    approach = _mat(mats, "SDB Entry Apron Paving", (0.43, 0.42, 0.37, 1.0), 0.86)
    # Vehicle traffic belongs beyond the boundary wall.  The broad strips inside
    # it are deliberately a quieter pedestrian/drop-off apron around the towers.
    aprons = MeshBatch("Inner arrival and pedestrian aprons", site, approach)
    aprons.add_box((SITE_X0, 105.0, 0.025), (SITE_X1, SITE_Y1, 0.12))
    aprons.add_box((SITE_X0, SITE_Y0, 0.025), (SITE_X1, -105.0, 0.12))
    aprons.add_box((SITE_X0, SITE_Y0, 0.025), (-205.0, SITE_Y1, 0.12))
    aprons.add_box((205.0, SITE_Y0, 0.025), (SITE_X1, SITE_Y1, 0.12))
    aprons.commit()["sdb_component"] = "site_approach_apron"
    roads = MeshBatch("External perimeter roads", site, asphalt)
    roads.add_box((-255.0, SITE_Y1, 0.02), (255.0, 160.0, 0.18))
    roads.add_box((-255.0, -158.0, 0.02), (255.0, SITE_Y0, 0.18))
    roads.add_box((-255.0, -158.0, 0.02), (SITE_X0, 160.0, 0.18))
    roads.add_box((SITE_X1, -158.0, 0.02), (255.0, 160.0, 0.18))
    roads.commit()["sdb_component"] = "external_perimeter_road"
    curbs = MeshBatch("External road curbs", site, curb)
    for x0, y0, x1, y1 in ((-255.0, 130.05, 255.0, 130.90), (-255.0, -128.90, 255.0, -128.05), (-225.90, -158.0, -225.05, 160.0), (225.05, -158.0, 225.90, 160.0)):
        curbs.add_box((x0, y0, 0.18), (x1, y1, 0.47))
    curbs.commit()
    dashes = MeshBatch("Road dashed lane markings", site, paint)
    for x in range(-246, 247, 18):
        dashes.add_box((x, 144.7, 0.195), (x + 7, 145.2, 0.22))
        dashes.add_box((x, -143.2, 0.195), (x + 7, -142.7, 0.22))
    for y in range(-150, 151, 18):
        dashes.add_box((-243.2, y, 0.195), (-242.7, y + 7, 0.22))
        dashes.add_box((242.7, y, 0.195), (243.2, y + 7, 0.22))
    dashes.commit()
    zebra = MeshBatch("South external entry zebra crossing", site, paint)
    for x in range(-17, 18, 4):
        zebra.add_box((x, -147.5, 0.20), (x + 1.8, -136.0, 0.23))
    zebra.commit()


def _terrain_and_context(site: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> None:
    """Ground the presentation view with a low-key, non-site-specific horizon."""
    terrain_mat = _mat(mats, "SDB Context Terrain", (0.135, 0.170, 0.095, 1.0), 1.0)
    context_mat = _mat(mats, "SDB Distant Context", (0.31, 0.30, 0.255, 1.0), 0.92)
    MeshBatch("Presentation terrain plane", site, terrain_mat).add_box((-10000.0, -10000.0, -1.50), (10000.0, 10000.0, -0.90)).commit()["sdb_component"] = "presentation_terrain"
    blocks = MeshBatch("Distant low-rise context blocks", site, context_mat)
    # Kept beyond the outer carriageway: these mass silhouettes give cameras a
    # believable horizon without competing with the bourse architecture.
    for x0, y0, x1, y1, top in (
        (-370.0, 210.0, -300.0, 265.0, 15.0), (-235.0, 228.0, -165.0, 286.0, 10.0),
        (-96.0, 215.0, -20.0, 255.0, 18.0), (50.0, 228.0, 128.0, 290.0, 12.0),
        (215.0, 205.0, 295.0, 270.0, 20.0), (305.0, 88.0, 370.0, 153.0, 14.0),
        (290.0, -110.0, 355.0, -42.0, 11.0), (-365.0, -130.0, -300.0, -60.0, 13.0),
    ):
        blocks.add_box((x0, y0, -.90), (x1, y1, min(top,6.0)))
    blocks.commit()["sdb_component"] = "distant_context"


def _boundary_and_gates(site: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> None:
    cream = mats["SDB Sandstone Cream"]
    metal = mats["SDB Dark Metal"]
    wall = MeshBatch("Boundary cream walls", site, cream)
    # Intentional gaps form the south visitor gate and east service gate.
    wall.add_box((SITE_X0, SITE_Y0, 0.1), (-24, -126.8, 3.2)).add_box((24, SITE_Y0, 0.1), (SITE_X1, -126.8, 3.2))
    wall.add_box((SITE_X0, 126.8, 0.1), (190, SITE_Y1, 3.2))
    wall.add_box((SITE_X0, -126.8, 0.1), (-223.8, 126.8, 3.2))
    wall.add_box((223.8, -104, 0.1), (SITE_X1, 76, 3.2))
    wall.commit()
    # The north-east plot edge bends around the club frontage.
    shaped_wall("Rounded north-east boundary", arc_points((190.0, 95.0), 35.0, 8, 92, 12), height=3.2, thickness=1.2, z_bottom=0.1, collection=site, mat=cream)
    slats = MeshBatch("Boundary dark slat panels", site, metal)
    for x in range(-210, 191, 5):
        if -26 < x < 26:
            continue
        slats.add_box((x, -127.25, 0.55), (x + 0.55, -126.55, 2.95))
    for y in range(-90, 96, 5):
        slats.add_box((-224.25, y, 0.55), (-223.55, y + 0.55, 2.95))
    slats.commit()
    porticos = MeshBatch("Entry gate porticos", site, cream)
    for x, y, wide, deep in ((0, -123.0, 19.0, 8.0), (213.0, 87.0, 8.0, 16.0)):
        porticos.add_box((x - wide / 2, y - deep / 2, 0.1), (x - wide / 2 + 1.2, y + deep / 2, 5.6))
        porticos.add_box((x + wide / 2 - 1.2, y - deep / 2, 0.1), (x + wide / 2, y + deep / 2, 5.6))
        porticos.add_box((x - wide / 2, y - deep / 2, 5.0), (x + wide / 2, y + deep / 2, 5.8))
    porticos.commit()


def _vertical_text(
    name: str,
    body: str,
    location: tuple[float, float, float],
    size: float,
    material_slot: bpy.types.Material,
    collection: bpy.types.Collection,
    face_y: float,
) -> bpy.types.Object:
    """Create centered, shallow, renderable lettering on a Y-facing facade."""
    font = bpy.data.curves.new(f"{name} Font", type="FONT")
    font.body = body
    font.align_x = "CENTER"
    font.align_y = "CENTER"
    font.size = size
    font.extrude = .028
    font.bevel_depth = .008
    font.bevel_resolution = 2
    font.resolution_u = 10
    font.materials.append(material_slot)
    obj = bpy.data.objects.new(name, font)
    collection.objects.link(obj)
    obj.location = location
    # Font geometry begins in XY with its face pointing +Z.  These transforms
    # put its baseline upright in Z and its face toward the requested side.
    if face_y > 0.0:
        obj.rotation_euler = (pi / 2.0, 0.0, pi)
    else:
        obj.rotation_euler = (pi / 2.0, 0.0, 0.0)
    obj["sdb_component"] = "site_wayfinding"
    return obj


def _site_signage(site: bpy.types.Collection, furniture: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> None:
    """Add the discrete public names and tower markers seen at human scale."""
    cream = mats["SDB Sandstone Cream"]
    metal = mats["SDB Dark Metal"]
    panels = MeshBatch("Site signage plinths", site, metal)
    # The north-boundary panel sits above the low wall, clear of the tree line.
    panels.add_box((105.0, 129.10, 1.05), (150.0, 130.30, 3.45))
    # Small markers sit before each office wing base; their letters stay legible
    # without pretending to be architectural massing.
    north_markers = ((-117.0, "D"), (-57.0, "C"), (3.0, "B"), (68.0, "A"))
    south_markers = ((-143.0, "E"), (-83.0, "F"), (-23.0, "G"), (42.0, "H"), (120.0, "J"))
    for x, _label in north_markers:
        panels.add_box((x - 2.25, 4.15, .16), (x + 2.25, 4.82, 1.72))
    for x, _label in south_markers:
        panels.add_box((x - 2.25, -14.62, .16), (x + 2.25, -13.95, 1.72))
    panels.commit()["sdb_component"] = "site_signage_plinth"
    _vertical_text("DIAMOND CLUB lettering", "DIAMOND CLUB", (150.0, 86.72, 7.0), 1.25, cream, furniture, 1.0)
    _vertical_text("Surat Diamond Bourse boundary lettering", "SURAT DIAMOND BOURSE", (126.0, 130.34, 2.25), 1.82, cream, furniture, 1.0)
    for x, label in north_markers:
        _vertical_text(f"Tower {label} designation", label, (x, 4.11, .98), 1.22, cream, furniture, -1.0)
    for x, label in south_markers:
        _vertical_text(f"Tower {label} designation", label, (x, -14.66, .98), 1.22, cream, furniture, -1.0)


def _courtyards(site: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> list[tuple[float, float]]:
    grass = _mat(mats, "SDB Courtyard Grass", (0.065, 0.13, 0.035, 1.0), 0.96)
    path = _mat(mats, "SDB Courtyard Paving", (0.68, 0.64, 0.54, 1.0), 0.84)
    water = mats["SDB Water"]
    hedge_mat = _mat(mats, "SDB Hedge", (0.035, 0.16, 0.035, 1.0), 0.97)
    # These centres sit in the large voids between the thin office slabs; the
    # eastern special buildings are intentionally left open for the Club/food zone.
    courts = [(-87, 63, 17, 35), (-27, 63, 17, 35), (35, 63, 16, 33), (-113, -53, 17, 34), (-53, -53, 17, 34), (9, -53, 17, 34), (80, -53, 14, 30)]
    lawn = MeshBatch("Courtyard lawns", site, grass)
    hedges = MeshBatch("Low courtyard hedge grids", site, hedge_mat)
    for index, (x, y, rx, ry) in enumerate(courts):
        lawn.add_polygon_extrusion(_ellipse((x, y), rx, ry, 24), 0.09, 0.15)
        # Four clipped hedge arms frame the grass without enclosing it as a box.
        hedges.add_box((x - rx - 1.5, y - ry + 4, 0.15), (x - rx - 0.8, y + ry - 4, 0.85))
        hedges.add_box((x + rx + 0.8, y - ry + 4, 0.15), (x + rx + 1.5, y + ry - 4, 0.85))
        hedges.add_box((x - rx + 4, y - ry - 1.5, 0.15), (x + rx - 4, y - ry - 0.8, 0.85))
        hedges.add_box((x - rx + 4, y + ry + 0.8, 0.15), (x + rx - 4, y + ry + 1.5, 0.85))
        # Pale curving paths and one compact circle per court echo the garden reference.
        curve = [(x - rx * .76, y - ry * .55), (x - rx * .25, y - ry * .05), (x + rx * .12, y + ry * .20), (x + rx * .72, y + ry * .62)]
        shaped_wall(f"Courtyard {index + 1:02d} curving path", curve, height=0.055, thickness=2.3, z_bottom=0.155, collection=site, mat=path)
        polygon_prism(f"Courtyard {index + 1:02d} circular plaza", _ellipse((x, y), 4.0, 4.0, 18), 0.15, 0.22, site, path)
        if index % 2 == 0:
            polygon_prism(f"Courtyard {index + 1:02d} water bowl", _ellipse((x, y), 1.75, 1.75, 16), 0.22, 0.31, site, water)
    lawn.commit()
    hedges.commit()
    return [(x, y) for x, y, _rx, _ry in courts]


def _utility_and_entourage(site: bpy.types.Collection, furniture: bpy.types.Collection, mats: dict[str, bpy.types.Material]) -> None:
    cream, metal = mats["SDB Sandstone Cream"], mats["SDB Dark Metal"]
    utility = MeshBatch("West utility building", site, cream)
    utility.add_box((-222, -92.5, 0.3), (-205, 92.5, 6.0)).commit()["sdb_component"] = "utility_building"
    slats = MeshBatch("Utility building slats", site, metal)
    for y in range(-86, 87, 6):
        slats.add_box((-222.7, y, 1.0), (-222.3, y + 2.6, 5.4))
    slats.commit()
    bench_mat = _mat(mats, "SDB Bench Wood", (0.17, 0.075, 0.035, 1.0), 0.6)
    benches = MeshBatch("Courtyard benches", furniture, bench_mat)
    bench_frames = MeshBatch("Courtyard bench dark frames", furniture, metal)
    for x, y in ((-87, 58), (-27, 58), (35, 58), (-113, -58), (-53, -58), (9, -58), (80, -58)):
        benches.add_box((x - 2.0, y - .32, .30), (x + 2.0, y + .32, .65))
        benches.add_box((x - 2.0, y + .23, .66), (x + 2.0, y + .34, 1.22))
        for leg_x in (x - 1.55, x + 1.55):
            bench_frames.add_box((leg_x - .08, y - .22, .10), (leg_x + .08, y + .22, .58))
            bench_frames.add_box((leg_x - .08, y + .20, .55), (leg_x + .08, y + .30, 1.18))
    benches.commit()
    bench_frames.commit()
    car_mat = _mat(mats, "SDB Car neutral", (0.16, 0.19, 0.22, 1.0), 0.35)
    cars = MeshBatch("Perimeter parked cars", furniture, car_mat)
    for index, x in enumerate(range(-176, 181, 44)):
        cars.add_box((x, 108, .22), (x + 4.7, 110.1, 1.65))
        cars.add_box((x + .85, 108.2, 1.65), (x + 3.8, 109.9, 2.3))
    cars.commit()


def _vegetation(veg: bpy.types.Collection, court_centers: Iterable[tuple[float, float]], mats: dict[str, bpy.types.Material]) -> None:
    trunk = _mat(mats, "SDB Tree Bark", (0.12, 0.055, 0.022, 1.0), 0.92)
    # Three close foliage tones provide depth in direct sun without making the
    # restrained architectural render read as a collection of colored assets.
    leaves = [
        _mat(mats, "SDB Tree Leaves Deep", (0.018, 0.105, 0.026, 1.0), 0.91),
        _mat(mats, "SDB Tree Leaves Mid", (0.030, 0.185, 0.048, 1.0), 0.87),
        _mat(mats, "SDB Tree Leaves Sun", (0.085, 0.265, 0.066, 1.0), 0.84),
    ]
    palm_leaves = [
        _mat(mats, "SDB Palm Leaves Deep", (0.020, 0.120, 0.035, 1.0), 0.86),
        _mat(mats, "SDB Palm Leaves Mid", (0.040, 0.220, 0.070, 1.0), 0.80),
        _mat(mats, "SDB Palm Leaves Sun", (0.085, 0.310, 0.105, 1.0), 0.77),
    ]
    sources = _tree_sources(veg, trunk, leaves, palm_leaves)
    placements: list[tuple[float, float, int, float]] = []
    for x in range(-185, 186, 18):
        placements.extend([(x, 94, (x // 18) % 3, .91), (x, -94, (x // 18 + 1) % 3, .88)])
    for y in range(-82, 88, 22):
        placements.extend([(-184, y, (y // 22) % 3, .89), (184, y, (y // 22 + 2) % 3, .88)])
    for index, (x, y) in enumerate(court_centers):
        placements.extend([(x - 10, y - 18, index % 3, .82), (x + 10, y + 18, (index + 1) % 3, .80)])
    for x, y, variant, scale in placements:
        # Club ellipse and flare apron remain deliberately unobstructed.
        if ((x - CLUB_CENTER[0]) / 25.0) ** 2 + ((y - CLUB_CENTER[1]) / 33.0) ** 2 < 1.15:
            continue
        _place_tree(sources, veg, x, y, int(variant), scale)
    for x, y in ((119, 81), (128, 94), (169, 92), (179, 73), (174, 34), (132, 25)):
        _place_palm(sources, veg, x, y, .92)


def build_site(
    params: dict[str, Any] | None,
    collections: dict[str, bpy.types.Collection],
    mats: dict[str, bpy.types.Material],
) -> dict[str, Any]:
    """Build the model's site without requiring any scene-setup side effects.

    ``params`` is accepted for the same driver API as the architecture module;
    current site dimensions intentionally use the public plan's blockout scale.
    The return value is lightweight metadata for the build runner or QA scripts.
    """
    root = collections.get("Site & Landscape") or ensure_collection("Site & Landscape")
    vegetation_parent = collections.get("Vegetation") or ensure_collection("Vegetation")
    site = ensure_collection("SDB Site Geometry", root)
    furniture = ensure_collection("SDB Site Furniture", root)
    veg = ensure_collection("SDB Site Vegetation", vegetation_parent)
    clear_collection(site)
    clear_collection(furniture)
    clear_collection(veg)
    ground_mat = _mat(mats, "SDB Ground Paving", (0.50, 0.48, 0.42, 1.0), 0.92)
    _terrain_and_context(site, mats)
    MeshBatch("Site ground pavement", site, ground_mat).add_box((SITE_X0, SITE_Y0, -0.16), (SITE_X1, SITE_Y1, 0.03)).commit()["sdb_component"] = "ground_pavement"
    _road_and_markings(site, mats)
    _boundary_and_gates(site, mats)
    court_centers = _courtyards(site, mats)
    _utility_and_entourage(site, furniture, mats)
    _site_signage(site, furniture, mats)
    _vegetation(veg, court_centers, mats)
    metadata = {
        "site_bounds_m": (SITE_X0, SITE_X1, SITE_Y0, SITE_Y1),
        "courtyard_count": len(court_centers),
        "collections": {"geometry": site.name, "furniture": furniture.name, "vegetation": veg.name},
        "object_count": len(site.objects) + len(furniture.objects) + len(veg.objects),
        "params_received": bool(params),
    }
    bpy.context.scene["SDB Site metadata"] = str(metadata)
    return metadata
