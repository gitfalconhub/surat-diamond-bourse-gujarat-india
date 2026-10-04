# SPDX-License-Identifier: GPL-3.0-or-later
"""Primary architectural massing for the Surat Diamond Bourse reconstruction.

This module contains no scene setup or render invocation.  The build runner
owns that work and calls ``build_massing`` first, followed later by the more
granular facade work in ``build_details``.
"""

from __future__ import annotations

from math import cos, pi, sin
from typing import Any, Sequence

import bpy
from mathutils import Vector

from sdb_utils import MeshBatch, ensure_collection, mesh_instance, polygon_prism, unlink_and_remove_object


BASE_Z = 0.3
OFFICE_BASE_Z = 6.4
GLAZING_TOP_Z = 66.5
SPINE_TOP_Z = 69.0


def north_spine_y(x: float) -> float:
    """The shallow concave edge of the north side of the central spine."""
    return 8.0 + 10.0 * (x / 175.0) ** 2


# The explicit configuration is intentionally public: it is the single source
# of truth for an artist adjusting the nine tower positions or special widths.
PARAMS: dict[str, Any] = {
    "base_z": BASE_Z,
    "office_base_z": OFFICE_BASE_Z,
    "glazing_top_z": GLAZING_TOP_Z,
    "spine_top_z": SPINE_TOP_Z,
    "spine_x_extent": 175.0,
    "spine_south_y": -9.0,
    "tower_default_width": 16.0,
    "tower_north_length": 90.0,
    "tower_south_length": 85.0,
    "towers": (
        {"name": "North 01", "side": "north", "x": -117.0},
        {"name": "North 02", "side": "north", "x": -57.0},
        {"name": "North 03", "side": "north", "x": 3.0},
        {"name": "North 04", "side": "north", "x": 68.0, "width": 28.0},
        {"name": "South 01", "side": "south", "x": -143.0},
        {"name": "South 02", "side": "south", "x": -83.0},
        {"name": "South 03", "side": "south", "x": -23.0},
        {"name": "South 04", "side": "south", "x": 42.0, "width": 23.0},
        {"name": "South 05", "side": "south", "x": 120.0, "width": 32.0},
    ),
}


def _material(mats: dict[str, bpy.types.Material], name: str) -> bpy.types.Material:
    """Fetch an expected named material with a useful error if setup was skipped."""
    try:
        return mats[name]
    except KeyError as exc:
        raise KeyError(f"build_massing requires material {name!r}") from exc


def _tower_collection(
    towers_collection: bpy.types.Collection,
    tower_name: str,
) -> tuple[bpy.types.Collection, bpy.types.Object]:
    collection = ensure_collection(f"Tower {tower_name}", towers_collection)
    parent_name = f"Tower {tower_name} Root"
    parent = bpy.data.objects.get(parent_name)
    if parent is None:
        parent = bpy.data.objects.new(parent_name, None)
        parent.empty_display_type = "CUBE"
        parent.empty_display_size = 3.0
        collection.objects.link(parent)
    return collection, parent


def _shared_box(
    cache: dict[tuple[Any, ...], bpy.types.Object],
    *,
    name: str,
    width: float,
    length: float,
    z_bottom: float,
    z_top: float,
    location: Sequence[float],
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    """Place a box whose mesh is reused for every identical mass component."""
    key = (mat.name, round(width, 3), round(length, 3), round(z_bottom, 3), round(z_top, 3))
    source = cache.get(key)
    if source is None:
        source = MeshBatch(name, collection, mat).add_box(
            (-width / 2.0, 0.0, z_bottom), (width / 2.0, length, z_top)
        ).commit()
        source.location = location
        cache[key] = source
        obj = source
    else:
        obj = mesh_instance(name, source, location=location, collection=collection)
    obj.parent = parent
    obj["sdb_component"] = "massing"
    obj["shared_mesh_key"] = ",".join(str(value) for value in key)
    return obj


def _tower_massing(
    config: dict[str, Any],
    towers_collection: bpy.types.Collection,
    mats: dict[str, bpy.types.Material],
    cache: dict[tuple[Any, ...], bpy.types.Object],
    params: dict[str, Any],
) -> bpy.types.Object:
    """Build two sequential, laterally stepped slabs around a central core seam."""
    tower_collection, parent = _tower_collection(towers_collection, config["name"])
    width = float(config.get("width", params["tower_default_width"]))
    side = config["side"]
    x = float(config["x"])
    length = float(config.get("length", params[f"tower_{side}_length"]))
    # North towers leave the spine at its concave edge.  South towers depart
    # from the straight southern wall and extend in the negative Y direction.
    direction = 1.0 if side == "north" else -1.0
    y_start = north_spine_y(x) + 1.5 if side == "north" else -9.5
    front_length = round(length * 0.48, 2)
    rear_length = length - front_length
    step_x = float(config.get("step_x", width * .35))
    glazed = _material(mats, "SDB Dark Blue Glazing")
    red = _material(mats, "SDB Red Granite")
    concrete = _material(mats, "SDB Concrete")
    cream = _material(mats, "SDB Sandstone Cream")
    metal = _material(mats, "SDB Dark Metal")
    base_z = float(params["base_z"])
    office_base_z = float(params["office_base_z"])

    # `_shared_box` is local Y-positive, so south tower parts rotate 180°.
    rotation = (0.0, 0.0, 0.0 if direction > 0 else pi)
    if direction > 0:
        front_loc = (x, y_start, 0.0)
        rear_loc = (x + step_x, y_start + front_length, 0.0)
        seam_y = y_start + front_length - 1.75
    else:
        front_loc = (x, y_start, 0.0)
        rear_loc = (x + step_x, y_start - front_length, 0.0)
        seam_y = y_start - front_length - 1.75

    # The first office floor floats above a glazed public level.  Keeping the
    # ground plane open is essential: a continuous opaque plinth made the
    # wings read as nine solid blocks in aerial and street-level views.
    for section_name, section_loc, section_length in (
        ("Front", front_loc, front_length), ("Rear", rear_loc, rear_length),
    ):
        for local_y in range(4, max(5, int(section_length - 3)), 8):
            for local_x in (-width / 2.0 + 1.1, width / 2.0 - 1.1):
                column = _shared_box(
                    cache, name=f"{config['name']} {section_name} Pilotis", width=.62,
                    length=.62, z_bottom=base_z, z_top=office_base_z,
                    location=(section_loc[0] + local_x, section_loc[1] + local_y * direction, 0.0),
                    collection=tower_collection, parent=parent, mat=concrete,
                )
                column.rotation_euler = rotation
        # A recessed, continuous entrance line makes the open public datum
        # legible without filling it with cream walling.
        entry = _shared_box(
            cache, name=f"{config['name']} {section_name} Glazed Entrance Line", width=width - 1.2,
            length=.10, z_bottom=base_z + .15, z_top=office_base_z - .18,
            location=(section_loc[0], section_loc[1] + 1.15 * direction, 0.0),
            collection=tower_collection, parent=parent, mat=glazed,
        )
        entry.rotation_euler = rotation
    front = _shared_box(
        cache, name=f"{config['name']} Front Glazed Slab", width=width,
        length=front_length, z_bottom=office_base_z, z_top=GLAZING_TOP_Z,
        location=front_loc, collection=tower_collection, parent=parent, mat=glazed,
    )
    front.rotation_euler = rotation
    rear = _shared_box(
        cache, name=f"{config['name']} Rear Glazed Slab", width=width,
        length=rear_length, z_bottom=office_base_z, z_top=GLAZING_TOP_Z,
        location=rear_loc, collection=tower_collection, parent=parent, mat=glazed,
    )
    rear.rotation_euler = rotation

    # Thin, inset roof decks and cream perimeter upstands replace the former
    # blue 4.5 m boxes.  Plant and repeated solar arrays give the roofscape a
    # credible working scale while retaining the pale full-height end caps.
    for section_name, section_loc, section_length in (
        ("Front", front_loc, front_length), ("Rear", rear_loc, rear_length),
    ):
        roof = _shared_box(
            cache, name=f"{config['name']} {section_name} Cream Roof Slab", width=width - .9,
            length=section_length - .9, z_bottom=GLAZING_TOP_Z, z_top=GLAZING_TOP_Z + .38,
            location=(section_loc[0], section_loc[1] + .45 * direction, 0.0),
            collection=tower_collection, parent=parent, mat=cream,
        )
        roof.rotation_euler = rotation
        for edge, edge_width, edge_length, offset_x, offset_y in (
            ("West", .32, section_length - .5, -width / 2.0 + .26, .25),
            ("East", .32, section_length - .5, width / 2.0 - .58, .25),
            ("Near", width - .5, .32, -.25, .25),
            ("Far", width - .5, .32, -.25, section_length - .57),
        ):
            parapet = _shared_box(
                cache, name=f"{config['name']} {section_name} Roof Parapet {edge}",
                width=edge_width, length=edge_length, z_bottom=GLAZING_TOP_Z + .35,
                z_top=GLAZING_TOP_Z + 1.48,
                location=(section_loc[0] + offset_x, section_loc[1] + offset_y * direction, 0.0),
                collection=tower_collection, parent=parent, mat=cream,
            )
            parapet.rotation_euler = rotation
        core = _shared_box(
            cache, name=f"{config['name']} {section_name} Roof Service Core", width=4.2,
            length=5.6, z_bottom=GLAZING_TOP_Z + .38, z_top=GLAZING_TOP_Z + 3.15,
            location=(section_loc[0] - width * .17, section_loc[1] + (section_length * .55) * direction, 0.0),
            collection=tower_collection, parent=parent, mat=concrete,
        )
        core.rotation_euler = rotation
        for row in range(6):
            panel = _shared_box(
                cache, name=f"{config['name']} {section_name} Solar Panel {row + 1}", width=3.2,
                length=1.35, z_bottom=GLAZING_TOP_Z + .48, z_top=GLAZING_TOP_Z + .62,
                location=(section_loc[0] + width * .14, section_loc[1] + (section_length * (.16 + row * .105)) * direction, 0.0),
                collection=tower_collection, parent=parent, mat=glazed,
            )
            panel.rotation_euler = rotation
        hvac = _shared_box(
            cache, name=f"{config['name']} {section_name} Roof HVAC", width=3.4,
            length=2.2, z_bottom=GLAZING_TOP_Z + .40, z_top=GLAZING_TOP_Z + 1.25,
            location=(section_loc[0] + width * .17, section_loc[1] + section_length * .72 * direction, 0.0),
            collection=tower_collection, parent=parent, mat=metal,
        )
        hvac.rotation_euler = rotation

    seam = _shared_box(
        cache, name=f"{config['name']} Central Seam Core", width=width + 3.0,
        length=3.5, z_bottom=base_z, z_top=SPINE_TOP_Z,
        location=(x + step_x / 2.0, seam_y, 0.0), collection=tower_collection,
        parent=parent, mat=red,
    )
    seam.rotation_euler = rotation
    parent["side"] = side
    parent["anchor_x"] = x
    parent["overall_length"] = length
    parent["slab_width"] = width
    parent["front_y_start"] = y_start
    parent["front_y_end"] = y_start + direction * front_length
    parent["rear_y_end"] = y_start + direction * length
    parent["detail_parenting"] = "tower-root; facade objects retain this root"
    return parent


def _spine_path() -> list[tuple[float, float]]:
    return [(x, north_spine_y(x)) for x in range(-175, 176, 10)]


def _spine_massing(
    collection: bpy.types.Collection,
    red: bpy.types.Material,
    base_z: float,
) -> list[bpy.types.Object]:
    """Build the continuous tall red walls of the central spine as one volume."""
    north = _spine_path()
    south = [(175.0, -9.0), (-175.0, -9.0)]
    footprint = north + south
    body = polygon_prism("Central Spine Tall Red Mass", footprint, base_z, SPINE_TOP_Z, collection, red)
    body["sdb_component"] = "central_spine_massing"
    return [body]


def _miter_offsets(points: Sequence[tuple[float, float]], half_width: float) -> list[Vector]:
    offsets: list[Vector] = []
    vectors = [Vector(point) for point in points]
    for index, point in enumerate(vectors):
        if index == 0:
            direction = (vectors[1] - point).normalized()
            offsets.append(Vector((-direction.y, direction.x)) * half_width)
            continue
        if index == len(vectors) - 1:
            direction = (point - vectors[index - 1]).normalized()
            offsets.append(Vector((-direction.y, direction.x)) * half_width)
            continue
        previous = (point - vectors[index - 1]).normalized()
        following = (vectors[index + 1] - point).normalized()
        normal_a = Vector((-previous.y, previous.x))
        normal_b = Vector((-following.y, following.x))
        miter = normal_a + normal_b
        if miter.length < 0.00001:
            offsets.append(normal_b * half_width)
        else:
            miter.normalize()
            offsets.append(miter * (half_width / max(abs(miter.dot(normal_b)), 0.35)))
    return offsets


def _sloped_vertical_fin(
    name: str,
    path: Sequence[tuple[float, float]],
    *,
    z_start: float,
    z_end: float,
    z_bottom: float,
    thickness: float,
    collection: bpy.types.Collection,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    """Make a thin curved wall with a roof edge that rises along the curve."""
    offsets = _miter_offsets(path, thickness / 2.0)
    left = [Vector(point) + offset for point, offset in zip(path, offsets)]
    right = [Vector(point) - offset for point, offset in zip(path, offsets)]
    count = len(path)
    vertices: list[tuple[float, float, float]] = []
    vertices.extend((point.x, point.y, z_bottom) for point in left)
    vertices.extend((point.x, point.y, z_bottom) for point in right)
    vertices.extend(
        (point.x, point.y, z_start + (z_end - z_start) * index / (count - 1))
        for index, point in enumerate(left)
    )
    vertices.extend(
        (point.x, point.y, z_start + (z_end - z_start) * index / (count - 1))
        for index, point in enumerate(right)
    )
    lb, rb, lt, rt = 0, count, count * 2, count * 3
    faces: list[tuple[int, ...]] = [(lb, rb, rt, lt), (lb + count - 1, lt + count - 1, rt + count - 1, rb + count - 1)]
    for index in range(count - 1):
        nxt = index + 1
        faces.extend([
            (lb + index, lb + nxt, lt + nxt, lt + index),
            (rb + nxt, rb + index, rt + index, rt + nxt),
            (lt + index, lt + nxt, rt + nxt, rt + index),
        ])
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj["sdb_component"] = "vertical_flare_fin"
    return obj


def _quadratic_path(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    segments: int = 18,
) -> list[tuple[float, float]]:
    return [
        (
            (1.0 - t) ** 2 * start[0] + 2.0 * (1.0 - t) * t * control[0] + t * t * end[0],
            (1.0 - t) ** 2 * start[1] + 2.0 * (1.0 - t) * t * control[1] + t * t * end[1],
        )
        for t in (index / segments for index in range(segments + 1))
    ]


def _tip_fins(
    collection: bpy.types.Collection,
    red: bpy.types.Material,
    base_z: float,
) -> list[bpy.types.Object]:
    """The six upright, rising fins that form the two distinctive end flares."""
    fins: list[bpy.types.Object] = []
    # These are deliberately broad, divergent blades, based on the plan's
    # fan rather than three short parallel plates gathered at one endpoint.
    # The first east blade continues the north spine behind the Diamond Club.
    east_paths = (
        ((105.0, north_spine_y(105.0)), (154.0, 24.0), (200.0, 64.0)),
        ((145.0, 8.0), (179.0, 18.0), (203.0, 42.0)),
        ((171.0, 0.0), (191.0, 5.0), (205.0, 20.0)),
    )
    west_paths = (
        ((-115.0, north_spine_y(-115.0)), (-162.0, 28.0), (-201.0, 32.0)),
        ((-145.0, 5.0), (-178.0, 14.0), (-203.0, 16.0)),
        ((-171.0, 0.0), (-191.0, 2.0), (-205.0, 0.0)),
    )
    for side, paths in (("East", east_paths), ("West", west_paths)):
        for index, values in enumerate(paths, 1):
            fins.append(_sloped_vertical_fin(
                f"{side} Flare Fin {index}", _quadratic_path(*values), z_start=SPINE_TOP_Z,
                z_end=76.0, z_bottom=base_z, thickness=1.35, collection=collection, mat=red,
            ))
    # Low cross-headers make the fin roots read as an entrance structure and
    # leave the dramatic upper blades free-standing.
    headers = MeshBatch("Entrance Flare Root Headers", collection, red)
    headers.add_box((104.0, north_spine_y(105.0) - .7, 19.4), (147.0, north_spine_y(105.0) + .7, 20.8))
    headers.add_box((-147.0, north_spine_y(-115.0) - .7, 19.4), (-114.0, north_spine_y(-115.0) + .7, 20.8))
    headers.commit()["sdb_component"] = "entrance_flare_root_headers"
    return fins


def _ellipse(center: tuple[float, float], radius_x: float, radius_y: float, segments: int = 40) -> list[tuple[float, float]]:
    return [
        (center[0] + radius_x * cos(2.0 * pi * index / segments),
         center[1] + radius_y * sin(2.0 * pi * index / segments))
        for index in range(segments)
    ]


def _diamond_club(
    collection: bpy.types.Collection,
    cream: bpy.types.Material,
    red: bpy.types.Material,
    base_z: float,
) -> list[bpy.types.Object]:
    """Massing for the separate, wrapped Diamond Club at the eastern end."""
    center = (150.0, 55.0)
    club: list[bpy.types.Object] = []
    inner = polygon_prism("Diamond Club Cream Inner Cylinder", _ellipse(center, 18.0, 24.0), base_z, 15.0, collection, cream)
    inner["sdb_component"] = "diamond_club_inner_volume"
    club.append(inner)
    # The enclosing red wall stays open at the south/front approach.  Its top
    # follows a 9 m front to 22 m rear slope rather than reading as a canopy.
    arc: list[tuple[float, float]] = []
    for index in range(38):
        angle = -0.15 * pi + (1.30 * pi) * index / 37.0
        arc.append((center[0] + 25.0 * cos(angle), center[1] + 31.0 * sin(angle)))
    outer = _sloped_vertical_fin(
        "Diamond Club Red Outer Wrap", arc, z_start=9.0, z_end=22.0,
        z_bottom=base_z, thickness=1.35, collection=collection, mat=red,
    )
    outer["sdb_component"] = "diamond_club_outer_wrap"
    club.append(outer)
    return club


def build_massing(
    params: dict[str, Any],
    collections: dict[str, bpy.types.Collection],
    mats: dict[str, bpy.types.Material],
) -> dict[str, Any]:
    """Build only the project silhouette and structural mass relationships.

    ``params`` may override any public ``PARAMS`` value, including the tower
    tuple.  It returns the roots and source-cache so a caller can inspect the
    generated structure before facade/detail generation.
    """
    merged = dict(PARAMS)
    merged.update(params or {})
    towers_collection = collections.get("Office Wings") or ensure_collection("Office Wings")
    spine_collection = collections.get("Podium") or ensure_collection("Podium")
    roof_collection = collections.get("Roofscape") or ensure_collection("Roofscape")
    cream = _material(mats, "SDB Sandstone Cream")
    red = _material(mats, "SDB Red Granite")
    cache: dict[tuple[Any, ...], bpy.types.Object] = {}
    tower_roots = [
        _tower_massing(config, towers_collection, mats, cache, merged)
        for config in merged["towers"]
    ]
    base_z = float(merged["base_z"])
    spine_objects = _spine_massing(spine_collection, red, base_z)
    fin_objects = _tip_fins(roof_collection, red, base_z)
    club_objects = _diamond_club(spine_collection, cream, red, base_z)
    return {
        "tower_roots": tower_roots,
        "spine": spine_objects,
        "fins": fin_objects,
        "diamond_club": club_objects,
        "shared_massing_meshes": cache,
    }


def _tower_sections(config: dict[str, Any], params: dict[str, Any]) -> list[dict[str, float]]:
    """Return world-space extents for the two serial slabs of one tower."""
    width = float(config.get("width", params["tower_default_width"]))
    side = config["side"]
    x = float(config["x"])
    length = float(config.get("length", params[f"tower_{side}_length"]))
    front_length = round(length * 0.48, 2)
    rear_length = length - front_length
    y_start = north_spine_y(x) + 1.5 if side == "north" else -9.5
    direction = 1.0 if side == "north" else -1.0
    step_x = float(config.get("step_x", width * .35))
    result: list[dict[str, float]] = []
    for section_x, section_y, section_length in (
        (x, y_start, front_length),
        (x + step_x, y_start + direction * front_length, rear_length),
    ):
        y_end = section_y + direction * section_length
        result.append({
            "x": section_x, "width": width, "y_min": min(section_y, y_end),
            "y_max": max(section_y, y_end), "direction": direction,
        })
    return result


def _tower_glazing_and_frames(
    params: dict[str, Any],
    collection: bpy.types.Collection,
    mats: dict[str, bpy.types.Material],
) -> dict[str, bpy.types.Object]:
    """Batch the X-normal glazed sides, stone surround, and fine aluminium grid."""
    cream = _material(mats, "SDB Sandstone Cream")
    metal = _material(mats, "SDB Dark Metal")
    glass = _material(mats, "SDB Dark Blue Glazing")
    office_base = float(params["office_base_z"])
    top = GLAZING_TOP_Z
    tower_results: dict[str, dict[str, bpy.types.Object]] = {}
    for tower_index, config in enumerate(params["towers"]):
        # Keep each tower's facade meshes independently selectable while their
        # source geometry remains repeated within each batch.
        frames = MeshBatch(f"{config['name']} | Cream Frames", collection, cream)
        glass_planes = MeshBatch(f"{config['name']} | Glazing Face Liners", collection, glass)
        grid = MeshBatch(f"{config['name']} | Fine Aluminium Grid", collection, metal)
        floors = MeshBatch(f"{config['name']} | Floor Edges", collection, metal)
        for section in _tower_sections(config, params):
            x, width = section["x"], section["width"]
            y0, y1 = section["y_min"], section["y_max"]
            for sign in (-1.0, 1.0):
                face_x = x + sign * width / 2.0
                # A thin liner gives the visible external glazed plane while
                # the shared dark mass behind it still reads as occupied depth.
                glass_planes.add_box((face_x - .035, y0, office_base), (face_x + .035, y1, top))
                # 3 m cream end caps and 1 m high top/base rails enclose each side.
                frames.add_box((face_x - .20, y0, office_base), (face_x + .20, y0 + 3.0, 71.0))
                frames.add_box((face_x - .20, y1 - 3.0, office_base), (face_x + .20, y1, 71.0))
                frames.add_box((face_x - .20, y0, office_base), (face_x + .20, y1, office_base + 1.0))
                frames.add_box((face_x - .20, y0, top - 1.0), (face_x + .20, y1, top))
                # 1.5 m facade grid, deliberately thin and subordinate to the stone frame.
                y = y0 + 3.0
                while y < y1 - 3.0:
                    grid.add_box((face_x - .060, y - .018, office_base + 1.0), (face_x + .060, y + .018, top - 1.0))
                    y += 1.5
                z = office_base + 1.0
                while z < top - 1.0:
                    grid.add_box((face_x - .060, y0 + 3.0, z - .018), (face_x + .060, y1 - 3.0, z + .018))
                    z += 1.5
            # Floor-edge bands give the office rhythm at the actual 3.9 m spacing.
            z = office_base
            while z < top - .1:
                floors.add_box((x - width / 2.0 - .055, y0 + .12, z - .045), (x + width / 2.0 + .055, y1 - .12, z + .045))
                z += 3.9
        parent = bpy.data.objects.get(f"Tower {config['name']} Root")
        detail_objects = {
            "frames": frames.commit(), "glazing": glass_planes.commit(),
            "grid": grid.commit(), "floor_edges": floors.commit(),
        }
        for obj in detail_objects.values():
            obj.parent = parent
            obj["sdb_component"] = "tower_facade"
            obj["tower_name"] = config["name"]
        tower_results[config["name"]] = detail_objects
    return tower_results


def _tower_end_screens(params, collection, mats):
    """Continuous granite screens, with smaller clustered square apertures."""
    red, cream = mats["SDB Red Granite"], mats["SDB Sandstone Cream"]
    results = {}
    for ti, config in enumerate(params["towers"]):
        screen = MeshBatch(config['name']+' | Perforated Red Screens', collection, red)
        caps = MeshBatch(config['name']+' | Cream End Caps', collection, cream)
        bridges = MeshBatch(config['name']+' | Screen Bridges', collection, cream)
        sections = _tower_sections(config, params)
        ends = [(sections[0], -sections[0]['direction']), (sections[-1], sections[-1]['direction'])]
        for ei, (sec, outward) in enumerate(ends):
            face_y = sec['y_max'] if outward > 0 else sec['y_min']
            x, w = sec['x'], sec['width']
            for dx0, dx1, depth, top in [(-w/2-.35,-.65,1.3,70.5),(.65,w/2+.35,0,68.5)]:
                yy = face_y + outward*depth
                caps.add_box((x+dx0,yy-.27,6.4),(x+dx1,yy+.27,top))
            yy = face_y + outward*3.0
            pitch=.25; left=x-3; bottom=.3
            for row in range(242):
                # Irregular, clustered perforations preserve broad solid stone areas.
                cells=[]
                for col in range(24):
                    noise=(row*173+col*67+row*col*19+ti*47+ei*31)%101
                    cluster=(sin(row*.105+ti*.6)+sin(col*.43+row*.018))
                    is_hole=1<col<22 and noise < (24 if cluster>.65 else 3)
                    cells.append(not is_hole)
                col=0
                while col<24:
                    if not cells[col]: col+=1; continue
                    start=col
                    while col<24 and cells[col]: col+=1
                    screen.add_box((left+start*pitch,yy-.15,bottom+row*pitch),(left+col*pitch,yy+.15,bottom+(row+1)*pitch))
            for z in (7,22.6,38.2,53.8):
                y0,y1=sorted((face_y,yy))
                bridges.add_box((x-2.4,y0,z-.2),(x+2.4,y1,z+.2))
        parent=bpy.data.objects.get('Tower '+config['name']+' Root')
        results[config['name']]={}
        for name,batch in [('screens',screen),('caps',caps),('bridges',bridges)]:
            obj=batch.commit();obj.parent=parent;obj['tower_name']=config['name']
            results[config['name']][name]=obj
    return results


def _spine_perforated_facades(
    params: dict[str, Any],
    collection: bpy.types.Collection,
    mats: dict[str, bpy.types.Material],
) -> dict[str, bpy.types.Object]:
    """Replace the opaque spine with two real perforated facade grids and voids."""
    old = bpy.data.objects.get("Central Spine Tall Red Mass")
    if old is not None:
        unlink_and_remove_object(old)
    red = _material(mats, "SDB Red Granite")
    concrete = _material(mats, "SDB Concrete")
    base_z = float(params["base_z"])
    # The perforated field stops before the flares.  The remaining outer
    # portions are intentionally bare red wall, which preserves the strong
    # tall silhouette visible behind the end entrances.
    x_min, x_max, columns = -135.0, 120.0, 106
    pitch_x = (x_max - x_min) / columns
    hole_width, pitch_z, rows = 1.0, 2.0, 30
    vertical_width = pitch_x - hole_width
    grids = MeshBatch("Central Spine | Real Perforated Granite", collection, red)
    floors = MeshBatch("Central Spine | Atrium Floor Slabs", collection, concrete)
    for side in ("north", "south"):
        for column in range(columns + 1):
            x = x_min + column * pitch_x
            y = north_spine_y(x) if side == "north" else -9.0
            grids.add_box((x - vertical_width / 2.0, y - .45, 4.0), (x + vertical_width / 2.0, y + .45, 66.0))
        # Each horizontal band is segmented to follow the concave north wall.
        for row in range(rows + 1):
            z = 4.0 + row * pitch_z
            for column in range(columns):
                x0 = x_min + column * pitch_x + vertical_width / 2.0
                x1 = x0 + hole_width
                xmid = (x0 + x1) / 2.0
                y = north_spine_y(xmid) if side == "north" else -9.0
                grids.add_box((x0, y - .45, z - .50), (x1, y + .45, z + .50))
        # Segmented upper/lower bands follow the north curvature too, keeping
        # the enclosing perimeter solid instead of flattening it at midspan.
        for column in range(columns):
            x0 = x_min + column * pitch_x
            x1 = x0 + pitch_x
            y = north_spine_y((x0 + x1) / 2.0) if side == "north" else -9.0
            grids.add_box((x0, y - .45, base_z), (x1, y + .45, 4.0))
            grids.add_box((x0, y - .45, 66.0), (x1, y + .45, SPINE_TOP_Z))
    tails = MeshBatch("Central Spine | Solid Flare Tail Walls", collection, red)
    for x0, x1 in ((-175.0, -135.0), (120.0, 175.0)):
        for side in ("north", "south"):
            y = north_spine_y((x0 + x1) / 2.0) if side == "north" else -9.0
            tails.add_box((x0, y - .52, base_z), (x1, y + .52, SPINE_TOP_Z))
    # Break slabs around the major courtyards.  Those physical voids are seen
    # through the square facade openings instead of reading as dark decals.
    floor_spans = ((-174.0, -145.0), (-115.0, -85.0), (-55.0, -25.0), (5.0, 35.0), (65.0, 95.0), (125.0, 174.0))
    z = 6.4
    while z < 66.0:
        for x0, x1 in floor_spans:
            floors.add_box((x0, -8.0, z - .13), (x1, 7.5, z + .13))
        z += 3.9
    return {"perforated_spine": grids.commit(), "solid_flare_tails": tails.commit(), "atrium_floors": floors.commit()}


def build_details(
    params: dict[str, Any],
    collections: dict[str, bpy.types.Collection],
    mats: dict[str, bpy.types.Material],
) -> dict[str, Any]:
    """Add the editable facade, frames, screens, spine perforations, and floors."""
    merged = dict(PARAMS)
    merged.update(params or {})
    facade = collections.get("Facade") or ensure_collection("Facade")
    spine = collections.get("Podium") or ensure_collection("Podium")
    tower_facades = _tower_glazing_and_frames(merged, facade, mats)
    screens = _tower_end_screens(merged, facade, mats)
    perforated_spine = _spine_perforated_facades(merged, spine, mats)
    return {"tower_facades": tower_facades, "end_screens": screens, "spine": perforated_spine}
