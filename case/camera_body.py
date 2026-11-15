import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

WALL = 2.2
LEFT_IN = -30.0
RIGHT_IN = 28.6
LEFT_OUT = LEFT_IN - WALL
RIGHT_OUT = RIGHT_IN + WALL
CENTER = (LEFT_OUT + RIGHT_OUT) / 2
FLOOR_OUT = -WALL
ROOF_IN = 44.0
ROOF_OUT = ROOF_IN + WALL
FRONT = 3.0
BOARD_START = 21.0
DEPTH = BOARD_START + 86.0
LEDGE = 3.5

SEAT = 12.6
LENS_Y = 21.0
BLOCK_HALF = 15.5
BLOCK_BOTTOM = LENS_Y - 16.8
BLOCK_TOP = LENS_Y + 11.5
BOARD_HALF = 12.75
LENS = 11.7
HOLE_X = 10.5

FOOT_HALF = 21.5
RIDGE = 1.6
RIDGE_RISE = 1.5
FOOT_LENGTH = 66.0

LOGO_Y = 36.6
WORD_Y = 6.4
WORD_WIDTH = 40.0
ENGRAVE = 0.6


def link(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def frustum(name, cx, cy, z0, sx0, sy0, z1, sx1, sy1):
    verts = []
    for z, sx, sy in ((z0, sx0, sy0), (z1, sx1, sy1)):
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append((cx + dx * sx / 2, cy + dy * sy / 2, z))
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return link(name, mesh)


def box(name, xa, xb, ya, yb, za, zb):
    x0, x1 = sorted((xa, xb))
    y0, y1 = sorted((ya, yb))
    z0, z1 = sorted((za, zb))
    return frustum(name, (x0 + x1) / 2, (y0 + y1) / 2, z0, x1 - x0, y1 - y0, z1, x1 - x0, y1 - y0)


def cone(name, cx, cy, z0, z1, r0, r1=None):
    mesh = bpy.data.meshes.new(name)
    work = bmesh.new()
    bmesh.ops.create_cone(work, cap_ends=True, segments=48, radius1=r0, radius2=r0 if r1 is None else r1, depth=z1 - z0)
    bmesh.ops.translate(work, verts=work.verts, vec=Vector((cx, cy, (z0 + z1) / 2)))
    work.to_mesh(mesh)
    work.free()
    return link(name, mesh)


def prism(name, outline, y0, y1):
    count = len(outline)
    verts = [(x, y0, z) for x, z in outline] + [(x, y1, z) for x, z in outline]
    faces = [tuple(range(count)), tuple(range(2 * count - 1, count - 1, -1))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, i + count, j + count, j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    work = bmesh.new()
    work.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(mesh)
    work.free()
    return link(name, mesh)


def combine(target, tool, operation):
    modifier = target.modifiers.new("step", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = tool
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(tool, do_unlink=True)


def add(body, tool):
    combine(body, tool, "UNION")


def cut(body, tool):
    combine(body, tool, "DIFFERENCE")


def shell():
    body = box("camera_body", LEFT_OUT, RIGHT_OUT, FLOOR_OUT, ROOF_OUT, 0, DEPTH)
    cut(body, box("inside", LEFT_IN, RIGHT_IN, 0, ROOF_IN, FRONT, DEPTH + 1))
    add(body, box("block", CENTER - BLOCK_HALF, CENTER + BLOCK_HALF, BLOCK_BOTTOM, BLOCK_TOP, FRONT - 0.1, SEAT + 0.8))
    add(body, box("ledge_left", LEFT_IN - 0.05, LEFT_IN + 5.0, -0.05, LEDGE, FRONT - 0.1, DEPTH))
    add(body, box("ledge_right", RIGHT_IN + 0.05, RIGHT_IN - 4.6, -0.05, LEDGE, FRONT - 0.1, DEPTH))
    add(body, box("stop_left", LEFT_IN - 0.05, LEFT_IN + 5.0, 0, 5.5, FRONT - 0.1, BOARD_START))
    add(body, box("stop_right", RIGHT_IN + 0.05, RIGHT_IN - 4.6, 0, 10.0, FRONT - 0.1, BOARD_START))
    add(body, box("lip", RIGHT_IN + 0.05, RIGHT_IN - 1.3, 5.6, 7.6, FRONT - 0.1, BOARD_START + 62.0))
    cut(body, box("power_window", LEFT_OUT - 1, LEFT_IN + 0.1, 1.0, 16.0, 14.0, 50.0))
    for low in (12.0, 20.0, 28.0):
        cut(body, box("vent_right", RIGHT_IN - 0.1, RIGHT_OUT + 1, low, low + 4.0, 30.0, 92.0))
    for low in (24.0, 32.0):
        cut(body, box("vent_left", LEFT_OUT - 1, LEFT_IN + 0.1, low, low + 4.0, 58.0, 92.0))
    top = ROOF_OUT - 0.05
    add(body, box("ridge_a", CENTER - FOOT_HALF - RIDGE, CENTER - FOOT_HALF, top, ROOF_OUT + RIDGE_RISE, 0, FOOT_LENGTH))
    add(body, box("ridge_b", CENTER + FOOT_HALF, CENTER + FOOT_HALF + RIDGE, top, ROOF_OUT + RIDGE_RISE, 0, FOOT_LENGTH))
    add(body, box("ridge_front", CENTER - FOOT_HALF - RIDGE, CENTER + FOOT_HALF + RIDGE, top, ROOF_OUT + RIDGE_RISE, 0, RIDGE))
    return body


def pocket(body):
    cx, cy = CENTER, LENS_Y
    cut(body, box("board", cx - BOARD_HALF, cx + BOARD_HALF, cy - 14.8, cy + 12.6, SEAT, SEAT + 3))
    cut(body, box("lens", cx - LENS / 2, cx + LENS / 2, cy - LENS / 2, cy + LENS / 2, 2.6, SEAT + 1))
    cut(body, box("parts", cx - 8.0, cx + 8.0, cy - 12.6, cy - LENS / 2 + 0.1, SEAT - 2.5, SEAT + 1))
    cut(body, frustum("window", cx, cy, -0.01, 23.1, 10.5, 0.8, 21.5, 8.9))
    cut(body, box("plate", cx - 11.65, cx + 11.65, cy - 5.35, cy + 5.35, 0.8, 3.0))
    cut(body, box("entry", cx - 11.95, cx + 11.95, cy - 5.65, cy + 5.65, 3.0, SEAT + 1))
    for rib_x in (-8.5, 8.5):
        for side in (-1, 1):
            add(body, box("rib", cx + rib_x - 0.4, cx + rib_x + 0.4, cy + side * 5.45, cy + side * 5.0, 0.8, 3.0))
    for side in (-1, 1):
        add(body, cone("peg", cx + side * HOLE_X, cy - 12.5, SEAT - 0.5, SEAT + 2.6, 1.08, 0.9))
        cut(body, box("relief", cx + side * 11.95, cx + side * 15.7, cy - 1.1, cy + 5.1, 1.0, SEAT + 3))
        add(body, box("arm", cx + side * BOARD_HALF, cx + side * (BOARD_HALF + 1.0), cy - 0.5, cy + 4.5, 0.9, SEAT + 2.6))
        barb = [
            (cx + side * (BOARD_HALF + 0.05), SEAT + 1.05),
            (cx + side * (BOARD_HALF - 0.8), SEAT + 1.85),
            (cx + side * (BOARD_HALF + 0.05), SEAT + 2.6),
        ]
        add(body, prism("barb", barb, cy - 0.5, cy + 4.5))


def mark(body):
    ring = cone("ring", CENTER, LOGO_Y, -0.2, ENGRAVE, 7.0)
    combine(ring, cone("ring_hole", CENTER, LOGO_Y, -0.5, ENGRAVE + 0.3, 5.9), "DIFFERENCE")
    cut(body, ring)
    eye = cone("lid_a", CENTER, LOGO_Y + 3.28, -0.2, ENGRAVE, 5.98)
    combine(eye, cone("lid_b", CENTER, LOGO_Y - 3.28, -0.5, ENGRAVE + 0.3, 5.98), "INTERSECT")
    combine(eye, cone("pupil", CENTER, LOGO_Y, -0.5, ENGRAVE + 0.3, 1.7), "DIFFERENCE")
    cut(body, eye)


def word(body):
    curve = bpy.data.curves.new("word", "FONT")
    curve.body = "blackout"
    curve.font = bpy.data.fonts.load(FONT)
    curve.extrude = 0.5
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    text = bpy.data.objects.new("word", curve)
    bpy.context.scene.collection.objects.link(text)
    bpy.ops.object.select_all(action="DESELECT")
    text.select_set(True)
    bpy.context.view_layer.objects.active = text
    bpy.ops.object.convert(target="MESH")
    text = bpy.context.view_layer.objects.active
    xs = [v.co.x for v in text.data.vertices]
    scale = WORD_WIDTH / (max(xs) - min(xs))
    middle = (max(xs) + min(xs)) / 2
    ys = [v.co.y for v in text.data.vertices]
    y_middle = (max(ys) + min(ys)) / 2
    for v in text.data.vertices:
        v.co.x = CENTER - (v.co.x - middle) * scale
        v.co.y = WORD_Y + (v.co.y - y_middle) * scale
        v.co.z = ENGRAVE if v.co.z > 0 else -0.3
    work = bmesh.new()
    work.from_mesh(text.data)
    bmesh.ops.remove_doubles(work, verts=work.verts, dist=0.001)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(text.data)
    work.free()
    cut(body, text)
    return (max(ys) - min(ys)) * scale


def report(body, word_height):
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    size = [round(high[i] - low[i], 1) for i in range(3)]
    print(f"REPORT size_mm={size} volume_cm3={round(volume / 1000, 1)} open_edges={loose} word_height={round(word_height, 1)}")


def picture(name, position, aim):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_cavity = True
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 800
    data = bpy.data.cameras.new(name)
    data.lens = 55
    data.clip_end = 3000
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    camera.location = position
    camera.rotation_euler = (Vector(aim) - Vector(position)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.render.filepath = str(OUT / name)
    bpy.ops.render.render(write_still=True)


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    body = shell()
    pocket(body)
    mark(body)
    height = word(body)
    report(body, height)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.stl_export(filepath=str(OUT / "camera_body.stl"), export_selected_objects=True)
    if "--pictures" in sys.argv:
        middle = (CENTER, 22, 50)
        picture("body_front.png", (-150, 110, -210), middle)
        picture("body_back.png", (150, 150, 330), middle)
        picture("body_face.png", (CENTER, 22, -260), (CENTER, 22, 0))
        picture("body_inside.png", (CENTER + 18, 40, 150), (CENTER, 20, 8))


main()
