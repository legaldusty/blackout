import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent

SEAT = 12.6
WALL_RISE = 0.8
HALF_WIDTH = 29.5
CAMERA_X = 14.25
BLOCK_BOTTOM = -11.5
BLOCK_TOP = 16.8
PLATE_BOTTOM = -33.0
FOOT_DEPTH = 40.0
BOARD_HALF = 12.75
BOARD_TOP = 14.8
LENS = 11.7
HOLE_X = 10.5
HOLE_TOP_Y = 12.5
PEG_RADIUS = 0.9
PEG_RISE = 1.6


def mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def frustum(name, cx, cy, z0, sx0, sy0, z1, sx1, sy1):
    verts = []
    for z, sx, sy in ((z0, sx0, sy0), (z1, sx1, sy1)):
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append((cx + dx * sx / 2, cy + dy * sy / 2, z))
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return mesh_object(name, verts, faces)


def box(name, x0, x1, y0, y1, z0, z1):
    return frustum(name, (x0 + x1) / 2, (y0 + y1) / 2, z0, x1 - x0, y1 - y0, z1, x1 - x0, y1 - y0)


def cylinder(name, cx, cy, z0, z1, radius):
    mesh = bpy.data.meshes.new(name)
    work = bmesh.new()
    bmesh.ops.create_cone(work, cap_ends=True, segments=32, radius1=radius, radius2=radius, depth=z1 - z0)
    bmesh.ops.translate(work, verts=work.verts, vec=Vector((cx, cy, (z0 + z1) / 2)))
    work.to_mesh(mesh)
    work.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def wedge(name, x0, x1, y0, y1, z0, z1):
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1)]
    faces = [(3, 2, 1, 0), (0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)]
    return mesh_object(name, verts, faces)


def combine(target, tool, operation):
    modifier = target.modifiers.new("step", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = tool
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(tool, do_unlink=True)


def build():
    body = box("camera_bar", -HALF_WIDTH, HALF_WIDTH, BLOCK_BOTTOM, BLOCK_TOP, 0, SEAT + WALL_RISE)
    combine(body, box("plate", -HALF_WIDTH, HALF_WIDTH, PLATE_BOTTOM, BLOCK_BOTTOM + 0.5, 0, 3.0), "UNION")
    combine(body, box("foot", -HALF_WIDTH, HALF_WIDTH, PLATE_BOTTOM, PLATE_BOTTOM + 3.0, 0, FOOT_DEPTH), "UNION")
    for side in (-1, 1):
        x0, x1 = sorted((side * HALF_WIDTH, side * (HALF_WIDTH - 2.5)))
        combine(body, wedge("gusset", x0, x1, PLATE_BOTTOM + 2.5, BLOCK_BOTTOM, 2.5, 30.0), "UNION")
        notch_x0, notch_x1 = sorted((side * HALF_WIDTH + side * 0.5, side * (HALF_WIDTH - 1.0)))
        combine(body, box("band_top", notch_x0, notch_x1, 9.0, 12.5, -1, SEAT + 2), "DIFFERENCE")
        combine(body, box("band_low", notch_x0, notch_x1, -9.5, -6.0, 3.0, SEAT + 2), "DIFFERENCE")

    for cx, filtered in ((-CAMERA_X, True), (CAMERA_X, False)):
        combine(body, box("board", cx - BOARD_HALF, cx + BOARD_HALF, BLOCK_BOTTOM - 1, BOARD_TOP, SEAT, SEAT + 3), "DIFFERENCE")
        combine(body, box("lens", cx - LENS / 2, cx + LENS / 2, -LENS / 2, LENS / 2, 2.6, SEAT + 1), "DIFFERENCE")
        combine(body, box("parts", cx - 8.0, cx + 8.0, LENS / 2 - 0.1, 12.6, SEAT - 2.5, SEAT + 1), "DIFFERENCE")
        if filtered:
            combine(body, frustum("window", cx, 0, -0.01, 23.1, 10.5, 0.8, 21.5, 8.9), "DIFFERENCE")
            combine(body, box("pocket", cx - 11.65, cx + 11.65, -5.35, 5.35, 0.8, 3.0), "DIFFERENCE")
            combine(body, box("entry", cx - 11.95, cx + 11.95, -5.65, 5.65, 3.0, SEAT + 1), "DIFFERENCE")
            for rib_x in (-8.5, 8.5):
                for rib_side in (-1, 1):
                    y0, y1 = sorted((rib_side * 5.45, rib_side * 5.1))
                    combine(body, box("rib", cx + rib_x - 0.4, cx + rib_x + 0.4, y0, y1, 0.8, 3.0), "UNION")
        else:
            combine(body, frustum("view", cx, 0, -0.01, 18.0, 12.4, 3.6, LENS, LENS), "DIFFERENCE")
        pegs = [(-HOLE_X, HOLE_TOP_Y), (HOLE_X, HOLE_TOP_Y)]
        if not filtered:
            pegs += [(-HOLE_X, 0.0), (HOLE_X, 0.0)]
        for px, py in pegs:
            combine(body, cylinder("peg", cx + px, py, SEAT - 0.5, SEAT + PEG_RISE, PEG_RADIUS), "UNION")
    return body


def report(body):
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    size = [round(high[i] - low[i], 2) for i in range(3)]
    print(f"REPORT size_mm={size} volume_cm3={round(volume / 1000, 1)} open_edges={loose}")


def picture(body, name, position):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_cavity = True
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 800
    camera_data = bpy.data.cameras.new(name)
    camera_data.lens = 60
    camera_data.clip_end = 2000
    camera = bpy.data.objects.new(name, camera_data)
    scene.collection.objects.link(camera)
    camera.location = position
    aim = Vector((0, -8, 10)) - Vector(position)
    camera.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.render.filepath = str(OUT / name)
    bpy.ops.render.render(write_still=True)


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    body = build()
    report(body)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.stl_export(filepath=str(OUT / "camera_bar.stl"), export_selected_objects=True)
    if "--pictures" in sys.argv:
        picture(body, "preview_back.png", (110, -150, 190))
        picture(body, "preview_front.png", (-90, -120, -170))


main()
