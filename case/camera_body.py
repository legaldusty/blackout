import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

WALL = 2.2
LEFT_IN = -31.0
RIGHT_IN = 31.0
LEFT_OUT = LEFT_IN - WALL
RIGHT_OUT = RIGHT_IN + WALL
CENTER = 0.0
FLOOR_OUT = -WALL
ROOF_IN = 44.0
FRONT = 3.0
BOARD_START = 22.0
DEPTH = BOARD_START + 86.0

SEAT = 12.6
LENS_Y = 19.0
BLOCK_HALF = 16.8
BLOCK_BOTTOM = -0.05
BLOCK_TOP = LENS_Y + 11.5
BOARD_HALF = 12.75
LENS = 11.7
KEY_LOW = 5.2
KEY_SLOT = 1.95
KEY_THICK = 1.5

RAIL_OUT = 1.8
RAIL_FACE = 2.8
GAP = 0.4
SKIRT = 2.2
LIP = 0.8
ROOF_HALF = RIGHT_OUT + RAIL_OUT + GAP + SKIRT
STOP = 2.3

FOOT_HALF = 21.3
FOOT_START = 2.0
FOOT_LENGTH = 63.4
GUIDE = 1.0
ROOF_PLATE = 2.4

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


def along(name, outline, z0, z1):
    count = len(outline)
    verts = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
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
    body = box("camera_body", LEFT_OUT, RIGHT_OUT, FLOOR_OUT, ROOF_IN, 0, DEPTH)
    cut(body, box("inside", LEFT_IN, RIGHT_IN, 0, ROOF_IN + 5, FRONT, DEPTH + 1))
    add(body, box("block", -BLOCK_HALF, BLOCK_HALF, BLOCK_BOTTOM, BLOCK_TOP, FRONT - 0.1, SEAT + 0.8))
    add(body, box("stop_right", RIGHT_IN + 0.05, 17.5, -0.05, 8.0, FRONT - 0.1, BOARD_START))
    for side in (-1, 1):
        wall = side * (RIGHT_OUT - 0.2)
        edge = side * (RIGHT_OUT + RAIL_OUT)
        low = ROOF_IN - RAIL_FACE
        add(body, along("rail", [(wall, low - RAIL_OUT - 0.2), (edge, low), (edge, ROOF_IN), (wall, ROOF_IN)], 0, DEPTH))
    cut(body, box("power_window", LEFT_OUT - 1, LEFT_IN + 0.1, 0.5, 16.0, 20.0, 47.0))
    for start in range(30, 95, 10):
        cut(body, box("vent_right", RIGHT_IN - 0.1, RIGHT_OUT + 1, 12.0, 36.0, start, start + 4.0))
    for start in range(54, 95, 10):
        cut(body, box("vent_left", LEFT_OUT - 1, LEFT_IN + 0.1, 12.0, 36.0, start, start + 4.0))
    return body


def pocket(body):
    cx, cy = CENTER, LENS_Y
    for side in (-1, 1):
        add(body, box("cheek", cx + side * BOARD_HALF, cx + side * BLOCK_HALF, BLOCK_BOTTOM, BLOCK_TOP, SEAT + 0.7, SEAT + 5.0))
    cut(body, box("board", cx - BOARD_HALF, cx + BOARD_HALF, cy - 14.8, cy + 12.6, SEAT, SEAT + 6))
    cut(body, box("lens", cx - LENS / 2, cx + LENS / 2, cy - LENS / 2, cy + LENS / 2, 2.6, SEAT + 1))
    cut(body, box("parts", cx - 8.0, cx + 8.0, cy - 12.6, cy - LENS / 2 + 0.1, SEAT - 2.5, SEAT + 1))
    cut(body, box("recess", cx - 11.6, cx + 11.6, cy - 5.3, cy + 5.3, -0.01, 1.5))
    cut(body, box("light", cx - 11.95, cx + 11.95, cy - 4.2, cy + 4.2, 1.4, SEAT + 1))
    cut(body, box("tab_room", cx - 3.5, cx + 3.5, cy - 5.65, cy + 5.65, 1.4, SEAT + 1))
    for rib_x in (-7.5, 7.5):
        for side in (-1, 1):
            add(body, box("rib", cx + rib_x - 0.3, cx + rib_x + 0.3, cy + side * 5.35, cy + side * 5.0, 0.3, 1.5))
    for side in (-1, 1):
        add(body, box("rib", cx + side * 11.65, cx + side * 11.3, cy - 0.3, cy + 0.3, 0.3, 1.5))
        cut(body, box("groove", cx + side * (BOARD_HALF - 0.05), cx + side * 14.75, KEY_LOW, BLOCK_TOP + 1, SEAT + 1.15, SEAT + 1.15 + KEY_SLOT))


def keys():
    length = BLOCK_TOP - KEY_LOW
    parts = []
    for index in range(3):
        left = index * 12.0
        key = box("camera_keys", left, left + 3.1, 0, length, 0, KEY_THICK)
        add(key, box("head", left - 1.6, left + 4.7, length - 0.1, length + 6.0, 0, KEY_THICK))
        parts.append(key)
    for other in parts[1:]:
        add(parts[0], other)
    return parts[0]


def roof():
    length = DEPTH + STOP
    plate = box("camera_roof", -ROOF_HALF, ROOF_HALF, 0, length, 0, ROOF_PLATE)
    inner = ROOF_HALF - SKIRT
    hook = RIGHT_OUT + GAP
    catch = ROOF_PLATE + RAIL_FACE
    tip = catch + inner - hook
    foot = tip + LIP
    for side in (-1, 1):
        outline = [
            (side * inner, ROOF_PLATE - 0.1),
            (side * inner, catch),
            (side * hook, tip),
            (side * hook, foot),
            (side * ROOF_HALF, foot),
            (side * ROOF_HALF, ROOF_PLATE - 0.1),
        ]
        skirt = along("skirt", outline, 0, length)
        for v in skirt.data.vertices:
            v.co.y, v.co.z = v.co.z, v.co.y
        skirt.data.update()
        tidy(skirt)
        add(plate, skirt)
        add(plate, box("guide", side * (RIGHT_IN - 0.8), side * (RIGHT_IN - 2.4), FRONT + 0.6, DEPTH, ROOF_PLATE - 0.1, ROOF_PLATE + 2.0))
        add(plate, box("stop", side * (RIGHT_IN + 0.5), side * ROOF_HALF, DEPTH + 0.3, length, ROOF_PLATE - 0.1, foot))
    outer = box("foot_mark", -FOOT_HALF - GUIDE, FOOT_HALF + GUIDE, FOOT_START - GUIDE, FOOT_START + FOOT_LENGTH + GUIDE, -0.1, 0.4)
    combine(outer, box("foot_inside", -FOOT_HALF, FOOT_HALF, FOOT_START, FOOT_START + FOOT_LENGTH, -0.5, 0.8), "DIFFERENCE")
    cut(plate, outer)
    return plate


def tidy(obj):
    work = bmesh.new()
    work.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(obj.data)
    work.free()


def overlap(body, tool):
    probe = body.copy()
    probe.data = body.data.copy()
    bpy.context.scene.collection.objects.link(probe)
    combine(probe, tool, "INTERSECT")
    work = bmesh.new()
    work.from_mesh(probe.data)
    volume = abs(work.calc_volume()) if work.faces else 0.0
    work.free()
    bpy.data.objects.remove(probe, do_unlink=True)
    return round(volume, 2)


def fit(body, lid):
    cy = LENS_Y
    seated = lid.copy()
    seated.data = lid.data.copy()
    bpy.context.scene.collection.objects.link(seated)
    for v in seated.data.vertices:
        v.co.y, v.co.z = ROOF_IN + ROOF_PLATE - v.co.z, v.co.y
    seated.data.update()
    tidy(seated)
    checks = {
        "pi": box("pi", -29.25, 29.25, 0.3, 17.8, BOARD_START + 0.3, DEPTH + 3),
        "power_plug": box("plug", LEFT_OUT - 20, LEFT_IN + 1, 2.0, 10.5, 26.0, 40.5),
        "camera_board": box("cam", -12.5, 12.5, cy - 14.5, cy + 9.5, SEAT + 0.05, SEAT + 1.1),
        "camera_lens": box("lens", -5.45, 5.45, cy - 5.45, cy + 5.45, 3.4, SEAT + 0.05),
        "key_left": box("key", -14.7, -11.6, KEY_LOW + 0.1, BLOCK_TOP, SEAT + 1.3, SEAT + 1.3 + KEY_THICK),
        "key_right": box("key", 11.6, 14.7, KEY_LOW + 0.1, BLOCK_TOP, SEAT + 1.3, SEAT + 1.3 + KEY_THICK),
        "window": box("window", -11.45, 11.45, cy - 5.15, cy + 5.15, 0.1, 1.4),
        "roof": seated,
    }
    for name, tool in checks.items():
        print(f"FIT {name} overlap_mm3={overlap(body, tool)}")


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


def report(body):
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    size = [round(high[i] - low[i], 1) for i in range(3)]
    print(f"REPORT {body.name} size_mm={size} volume_cm3={round(volume / 1000, 1)} open_edges={loose}")


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


def export(body, name):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.stl_export(filepath=str(OUT / name), export_selected_objects=True)


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    body = shell()
    pocket(body)
    mark(body)
    word(body)
    lid = roof()
    fit(body, lid)
    for v in body.data.vertices:
        v.co.y, v.co.z = -v.co.z, v.co.y
    body.data.update()
    report(body)
    export(body, "camera_body.stl")
    if "--pictures" in sys.argv:
        lid.hide_render = True
        picture("body_front.png", (-100, 150, 80), (0, -40, 20))
        picture("body_back.png", (90, -270, 120), (0, -50, 18))
        picture("body_top.png", (0, -150, 260), (0, -52, 0))
        shown = lid.copy()
        shown.data = lid.data.copy()
        bpy.context.scene.collection.objects.link(shown)
        for v in shown.data.vertices:
            v.co.y, v.co.z = -v.co.y - 40.0, ROOF_IN + ROOF_PLATE - v.co.z
        shown.data.update()
        tidy(shown)
        shown.hide_render = False
        picture("body_roof.png", (-130, 110, 120), (0, -70, 25))
        picture("body_roof_back.png", (60, -290, 75), (0, -90, 30))
        bpy.data.objects.remove(shown, do_unlink=True)
        body.hide_render = True
        lid.hide_render = False
        picture("roof_under.png", (-90, -60, 110), (0, 55, 0))
    body.hide_render = True
    lid.hide_render = True
    for part, name in ((lid, "camera_roof.stl"), (keys(), "camera_keys.stl")):
        report(part)
        export(part, name)
        part.hide_render = True


main()
