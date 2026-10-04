# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable Blender building blocks for the Surat Diamond Bourse scene.

The scene scripts use metres and Z-up coordinates.  This module deliberately
keeps geometry construction explicit: major facade masses can be inspected,
edited, and regenerated without relying on opaque modifiers or operators.
It is compatible with Blender 4.x and newer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, pi, sin
from typing import Iterable, Mapping, Sequence

import bpy
from mathutils import Vector


Color = tuple[float, float, float, float]
Point2 = tuple[float, float]
Point3 = tuple[float, float, float]


# Restrained materials intended for an architectural daylight render.  These
# are deliberately named and stable so an artist can adjust them in Blender.
MATERIAL_SPECS: dict[str, dict[str, object]] = {
    "SDB Sandstone Cream": {
        "base_color": (0.65, 0.61, 0.50, 1.0),
        "roughness": 0.76,
        "metallic": 0.0,
    },
    "SDB Red Granite": {
        "base_color": (0.32, 0.10, 0.065, 1.0),
        "roughness": 0.42,
        "metallic": 0.03,
    },
    "SDB Dark Blue Glazing": {
        "base_color": (0.012, 0.045, 0.082, 1.0),
        "roughness": 0.16,
        "metallic": 0.18,
        "transmission": 0.0,
    },
    "SDB Concrete": {
        "base_color": (0.31, 0.30, 0.275, 1.0),
        "roughness": 0.82,
        "metallic": 0.0,
    },
    "SDB Landscape": {
        "base_color": (0.075, 0.18, 0.055, 1.0),
        "roughness": 0.94,
        "metallic": 0.0,
    },
    "SDB Water": {
        "base_color": (0.008, 0.10, 0.16, 1.0),
        "roughness": 0.10,
        "metallic": 0.1,
    },
    "SDB Dark Metal": {
        "base_color": (0.025, 0.029, 0.032, 1.0),
        "roughness": 0.28,
        "metallic": 0.72,
    },
}


def _as_vector(value: Sequence[float]) -> Vector:
    return Vector(value)


def ensure_collection(
    name: str,
    parent: bpy.types.Collection | None = None,
) -> bpy.types.Collection:
    """Return a named collection, linking it to ``parent`` or the scene root."""
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    owner = parent or bpy.context.scene.collection
    if owner.children.get(collection.name) is None:
        owner.children.link(collection)
    return collection


def create_collection_tree(
    root_name: str = "SDB Project",
    groups: Sequence[str] = (
        "Site & Landscape",
        "Podium",
        "Office Wings",
        "Facade",
        "Roofscape",
        "Vegetation",
        "Cameras",
        "Lighting",
    ),
) -> dict[str, bpy.types.Collection]:
    """Create the scene hierarchy used by the architecture script."""
    root = ensure_collection(root_name)
    result = {"root": root}
    for group in groups:
        result[group] = ensure_collection(group, root)
    return result


def unlink_and_remove_object(obj: bpy.types.Object) -> None:
    """Remove an object and its mesh/curve data when it has no other users."""
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)


def clear_collection(collection: bpy.types.Collection, recursive: bool = False) -> None:
    """Clear generated objects in a collection without touching unrelated scene data."""
    for obj in list(collection.objects):
        unlink_and_remove_object(obj)
    if recursive:
        for child in collection.children:
            clear_collection(child, recursive=True)


def material(
    name: str,
    *,
    base_color: Color,
    roughness: float = 0.5,
    metallic: float = 0.0,
    transmission: float = 0.0,
    alpha: float = 1.0,
) -> bpy.types.Material:
    """Get or create an editable Principled BSDF material."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = base_color[:3] + (alpha,)
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled is None:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.inputs["Base Color"].default_value = base_color
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    if "Transmission Weight" in principled.inputs:
        principled.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in principled.inputs:
        principled.inputs["Transmission"].default_value = transmission
    if "Alpha" in principled.inputs:
        principled.inputs["Alpha"].default_value = alpha
    return mat


def build_material_library() -> dict[str, bpy.types.Material]:
    """Return the standard project materials, creating any that are absent."""
    return {
        name: material(name, **spec)  # type: ignore[arg-type]
        for name, spec in MATERIAL_SPECS.items()
    }


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material | None) -> None:
    if mat is None:
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)


@dataclass
class MeshBatch:
    """Accumulate simple solids in one mesh object per material.

    Batching keeps a facade with hundreds of mullion blocks or panels editable
    while avoiding Blender object-count overhead.  Call :meth:`commit` after
    adding all solids.
    """

    name: str
    collection: bpy.types.Collection
    material: bpy.types.Material | None = None
    vertices: list[Point3] = field(default_factory=list)
    faces: list[tuple[int, ...]] = field(default_factory=list)

    def add_box(
        self,
        minimum: Sequence[float],
        maximum: Sequence[float],
    ) -> "MeshBatch":
        """Add an axis-aligned closed box using opposite lower/upper corners."""
        x0, y0, z0 = minimum
        x1, y1, z1 = maximum
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            raise ValueError("Box maximum must be greater than minimum on every axis")
        start = len(self.vertices)
        self.vertices.extend(
            [
                (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
            ]
        )
        self.faces.extend(
            [
                (start, start + 3, start + 2, start + 1),
                (start + 4, start + 5, start + 6, start + 7),
                (start, start + 1, start + 5, start + 4),
                (start + 1, start + 2, start + 6, start + 5),
                (start + 2, start + 3, start + 7, start + 6),
                (start + 3, start, start + 4, start + 7),
            ]
        )
        return self

    def add_polygon_extrusion(
        self,
        points: Sequence[Point2],
        z_bottom: float,
        z_top: float,
    ) -> "MeshBatch":
        """Add a vertical extrusion of a simple, non-self-intersecting polygon."""
        if len(points) < 3:
            raise ValueError("An extruded polygon requires at least three points")
        if z_top <= z_bottom:
            raise ValueError("z_top must be greater than z_bottom")
        clean = list(points)
        if clean[0] == clean[-1]:
            clean.pop()
        if len(clean) < 3:
            raise ValueError("Polygon must have at least three distinct points")
        start = len(self.vertices)
        count = len(clean)
        self.vertices.extend([(x, y, z_bottom) for x, y in clean])
        self.vertices.extend([(x, y, z_top) for x, y in clean])
        self.faces.append(tuple(start + i for i in reversed(range(count))))
        self.faces.append(tuple(start + count + i for i in range(count)))
        for i in range(count):
            nxt = (i + 1) % count
            self.faces.append((start + i, start + nxt, start + count + nxt, start + count + i))
        return self

    def commit(self, *, smooth: bool = False) -> bpy.types.Object:
        """Create one mesh object, link it to the batch collection, and return it."""
        mesh = bpy.data.meshes.new(f"{self.name} Mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.materials.clear()
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(self.name, mesh)
        self.collection.objects.link(obj)
        if self.material:
            mesh.materials.append(self.material)
        if smooth:
            for polygon in mesh.polygons:
                polygon.use_smooth = True
        return obj


def polygon_prism(
    name: str,
    points: Sequence[Point2],
    z_bottom: float,
    z_top: float,
    collection: bpy.types.Collection,
    mat: bpy.types.Material | None = None,
) -> bpy.types.Object:
    """Create one named polygon extrusion; use MeshBatch for many same-material solids."""
    return MeshBatch(name, collection, mat).add_polygon_extrusion(points, z_bottom, z_top).commit()


def _path_offsets(points: Sequence[Point2], half_width: float, closed: bool) -> list[Vector]:
    """Calculate mitered side offsets for a polyline in the XY plane."""
    vectors = [Vector(p) for p in points]
    if len(vectors) < 2:
        raise ValueError("Wall path needs at least two points")
    offsets: list[Vector] = []
    count = len(vectors)
    for i, point in enumerate(vectors):
        before_i = (i - 1) % count
        after_i = (i + 1) % count
        if not closed and i == 0:
            direction = (vectors[1] - point).normalized()
            offsets.append(Vector((-direction.y, direction.x)) * half_width)
            continue
        if not closed and i == count - 1:
            direction = (point - vectors[-2]).normalized()
            offsets.append(Vector((-direction.y, direction.x)) * half_width)
            continue
        previous = (point - vectors[before_i]).normalized()
        following = (vectors[after_i] - point).normalized()
        normal_a = Vector((-previous.y, previous.x))
        normal_b = Vector((-following.y, following.x))
        miter = normal_a + normal_b
        if miter.length < 1e-7:
            offsets.append(normal_b * half_width)
            continue
        miter.normalize()
        denominator = max(abs(miter.dot(normal_b)), 0.35)
        offsets.append(miter * (half_width / denominator))
    return offsets


def shaped_wall(
    name: str,
    path: Sequence[Point2],
    *,
    height: float,
    thickness: float,
    z_bottom: float = 0.0,
    closed: bool = False,
    collection: bpy.types.Collection,
    mat: bpy.types.Material | None = None,
) -> bpy.types.Object:
    """Create a mitered, vertical wall following a straight or curved polyline."""
    if height <= 0 or thickness <= 0:
        raise ValueError("Wall height and thickness must be positive")
    points = list(path)
    if closed and points[0] == points[-1]:
        points.pop()
    offsets = _path_offsets(points, thickness / 2.0, closed)
    left = [Vector(p) + offset for p, offset in zip(points, offsets)]
    right = [Vector(p) - offset for p, offset in zip(points, offsets)]
    z_top = z_bottom + height
    vertices: list[Point3] = []
    for z in (z_bottom, z_top):
        vertices.extend([(p.x, p.y, z) for p in left])
        vertices.extend([(p.x, p.y, z) for p in right])
    count = len(points)
    lb, rb, lt, rt = 0, count, count * 2, count * 3
    faces: list[tuple[int, ...]] = []
    edge_count = count if closed else count - 1
    for i in range(edge_count):
        j = (i + 1) % count
        faces.extend(
            [
                (lb + i, lb + j, lt + j, lt + i),
                (rb + j, rb + i, rt + i, rt + j),
                (lb + j, rb + j, rt + j, lt + j),
                (rb + i, rt + i, lt + i, lb + i),
            ]
        )
    if not closed:
        # Close the two exposed ends; top and base are already added per span.
        faces.append((lb, rb, rt, lt))
        last = count - 1
        faces.append((lb + last, lt + last, rt + last, rb + last))
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    return obj


def arc_points(
    center: Point2,
    radius: float,
    start_degrees: float,
    end_degrees: float,
    segments: int = 24,
) -> list[Point2]:
    """Return evenly sampled XY points for a circular arc, inclusive of its ends."""
    if radius <= 0 or segments < 1:
        raise ValueError("Arc radius and segment count must be positive")
    start, end = start_degrees * pi / 180.0, end_degrees * pi / 180.0
    return [
        (center[0] + radius * cos(start + (end - start) * i / segments),
         center[1] + radius * sin(start + (end - start) * i / segments))
        for i in range(segments + 1)
    ]


def polyline_curve(
    name: str,
    points: Sequence[Sequence[float]],
    *,
    collection: bpy.types.Collection,
    mat: bpy.types.Material | None = None,
    bevel_depth: float = 0.0,
    bevel_resolution: int = 2,
    cyclic: bool = False,
) -> bpy.types.Object:
    """Create an editable poly spline; use bevel depth for railings or seams."""
    if len(points) < 2:
        raise ValueError("A curve needs at least two points")
    curve = bpy.data.curves.new(f"{name} Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = bevel_resolution
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        xyz = list(co)[:3]
        xyz.extend([0.0] * (3 - len(xyz)))
        point.co = (xyz[0], xyz[1], xyz[2], 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    assign_material(obj, mat)
    return obj


def mesh_instance(
    name: str,
    source: bpy.types.Object,
    location: Sequence[float] = (0.0, 0.0, 0.0),
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    scale: Sequence[float] = (1.0, 1.0, 1.0),
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    """Add an object sharing source data, suitable for repeated towers or trees."""
    duplicate = bpy.data.objects.new(name, source.data)
    duplicate.location = location
    duplicate.rotation_euler = rotation
    duplicate.scale = scale
    (collection or bpy.context.collection).objects.link(duplicate)
    return duplicate


def point_at(obj: bpy.types.Object, target: Sequence[float], track: str = "-Z", up: str = "Y") -> None:
    """Orient a camera or light so its local tracking axis faces target."""
    direction = _as_vector(target) - obj.location
    if direction.length < 1e-8:
        raise ValueError("Cannot point an object at its own location")
    obj.rotation_euler = direction.to_track_quat(track, up).to_euler()


def camera(
    name: str,
    *,
    location: Sequence[float],
    target: Sequence[float],
    collection: bpy.types.Collection,
    focal_length: float = 42.0,
    sensor_width: float = 36.0,
    make_active: bool = False,
) -> bpy.types.Object:
    """Create a perspective camera and aim it at a scene location."""
    data = bpy.data.cameras.new(f"{name} Camera")
    data.lens = focal_length
    data.sensor_width = sensor_width
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    collection.objects.link(obj)
    point_at(obj, target)
    if make_active:
        bpy.context.scene.camera = obj
    return obj
