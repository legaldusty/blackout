import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"

LEFT, RIGHT = -2.2, 87.5
TOP, BOTTOM = 2.6, -54.3
SIDE_WALL, END_WALL = 3.0, 2.0
OUT_LEFT, OUT_RIGHT = LEFT - SIDE_WALL, RIGHT + SIDE_WALL
OUT_TOP, OUT_BOTTOM = TOP + END_WALL, BOTTOM - END_WALL
FLOOR = 1.6
WALL_TOP = 18.6
SKIN = 2.0
FACE = WALL_TOP + SKIN
CENTER = 42.64
HEAD_TOP = 13.0

EYE = (79.0, -20.67)
WINK = (85.28 - 79.0, -20.67)
INFRARED = (4.1, -30.06)
CHEEK = (85.28 - 4.1, -30.06)
BUTTON = (85.28 - 35.15, -49.41)
BUTTON_TOP = 16.15
USB = (35.6, 49.6)
CUT_LOW, CUT_HIGH = FACE - 0.6, FACE + 0.2


def link(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def extrude(name, outline, z0, z1):
    count = len(outline)
    verts = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, 2 * count))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    work = bmesh.new()
    work.from_mesh(mesh)
    bmesh.ops.triangulate(work, faces=work.faces)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(mesh)
    work.free()
    return link(name, mesh)


def box(name, xa, xb, ya, yb, za, zb):
    x0, x1 = sorted((xa, xb))
    y0, y1 = sorted((ya, yb))
    return extrude(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], min(za, zb), max(za, zb))


def disc(name, center, radius, z0, z1, steps=64):
    ring = [(center[0] + radius * math.cos(2 * math.pi * i / steps), center[1] + radius * math.sin(2 * math.pi * i / steps)) for i in range(steps)]
    return extrude(name, ring, z0, z1)


def rounded(x0, x1, y0, y1, radius, steps=10):
    points = []
    for cx, cy, start in ((x1 - radius, y0 + radius, -90), (x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90), (x0 + radius, y0 + radius, 180)):
        for i in range(steps + 1):
            angle = math.radians(start + 90 * i / steps)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


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


def ring(center, inner, outer):
    shape = disc("ring", center, outer, CUT_LOW, CUT_HIGH)
    combine(shape, disc("hole", center, inner, CUT_LOW - 0.3, CUT_HIGH + 0.3), "DIFFERENCE")
    return shape


def arc(center, inner, outer, upper):
    shape = ring(center, inner, outer)
    keep_low, keep_high = (center[1], center[1] + outer + 1) if upper else (center[1] - outer - 1, center[1])
    combine(shape, box("half", center[0] - outer - 1, center[0] + outer + 1, keep_low, keep_high, CUT_LOW - 0.5, CUT_HIGH + 0.5), "INTERSECT")
    return shape


def word(body, text, center, width):
    curve = bpy.data.curves.new("word", "FONT")
    curve.body = text
    curve.font = bpy.data.fonts.load(FONT)
    curve.extrude = 0.5
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    holder = bpy.data.objects.new("word", curve)
    bpy.context.scene.collection.objects.link(holder)
    bpy.ops.object.select_all(action="DESELECT")
    holder.select_set(True)
    bpy.context.view_layer.objects.active = holder
    bpy.ops.object.convert(target="MESH")
    holder = bpy.context.view_layer.objects.active
    xs = [v.co.x for v in holder.data.vertices]
    ys = [v.co.y for v in holder.data.vertices]
    scale = width / (max(xs) - min(xs))
    mid_x, mid_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    for v in holder.data.vertices:
        v.co.x = center[0] + (v.co.x - mid_x) * scale
        v.co.y = center[1] + (v.co.y - mid_y) * scale
        v.co.z = CUT_HIGH if v.co.z > 0 else CUT_LOW
    work = bmesh.new()
    work.from_mesh(holder.data)
    bmesh.ops.remove_doubles(work, verts=work.verts, dist=0.001)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(holder.data)
    work.free()
    cut(body, holder)


def tray():
    body = extrude("badge_tray", rounded(OUT_LEFT, OUT_RIGHT, OUT_BOTTOM, OUT_TOP, 5.0), -FLOOR, WALL_TOP)
    cut(body, box("inside", LEFT, RIGHT, BOTTOM, TOP, 0, WALL_TOP + 1))
    cut(body, box("usb", USB[0], USB[1], OUT_BOTTOM - 1, BOTTOM + 0.1, 10.5, WALL_TOP + 1))
    cut(body, box("catch_a", LEFT - 0.45, LEFT + 0.1, -40, -12, 16.3, 17.3))
    cut(body, box("catch_b", RIGHT - 0.1, RIGHT + 0.45, -40, -12, 16.3, 17.3))
    return body


def lid(kind):
    body = extrude("lid_" + kind, rounded(OUT_LEFT, OUT_RIGHT, OUT_BOTTOM, HEAD_TOP, 6.0), WALL_TOP, FACE)
    if kind == "cat":
        ears = (((OUT_LEFT + 0.6, HEAD_TOP - 7), (21.0, HEAD_TOP - 1), (3.5, HEAD_TOP + 16)),)
    else:
        ears = (((OUT_LEFT + 0.6, HEAD_TOP - 7), (12.0, HEAD_TOP - 1), (-2.0, HEAD_TOP + 11)),)
    for ear in ears:
        add(body, extrude("ear", list(ear), WALL_TOP, FACE))
        mirrored = [(2 * CENTER - x, y) for x, y in reversed(ear)]
        add(body, extrude("ear", mirrored, WALL_TOP, FACE))
    lip_low = WALL_TOP - 4.0
    for x0, x1 in ((LEFT + 0.2, LEFT + 1.6), (RIGHT - 1.6, RIGHT - 0.2)):
        add(body, box("lip", x0, x1, BOTTOM + 0.2, TOP - 0.2, lip_low, WALL_TOP + 0.1))
    for y0, y1 in ((TOP - 1.6, TOP - 0.2), (BOTTOM + 0.2, BOTTOM + 1.6)):
        add(body, box("lip", LEFT + 0.2, 27.0, y0, y1, lip_low, WALL_TOP + 0.1))
        add(body, box("lip", 59.0, RIGHT - 0.2, y0, y1, lip_low, WALL_TOP + 0.1))
    add(body, box("snap", LEFT - 0.2, LEFT + 0.3, -39, -13, 16.5, 17.1))
    add(body, box("snap", RIGHT - 0.3, RIGHT + 0.2, -39, -13, 16.5, 17.1))
    cut(body, box("lanyard", CENTER - 7, CENTER + 7, 7.0, 10.5, WALL_TOP - 1, FACE + 1))

    cut(body, disc("eye", EYE, 3.25, WALL_TOP - 1, FACE + 1))
    tongue_x0, tongue_x1 = BUTTON[0] - 4.5, BUTTON[0] + 4.5
    tip_y = -48.6
    gap = box("gap", tongue_x0 - 0.8, tongue_x1 + 0.8, tip_y, -37.5, WALL_TOP - 1, FACE + 1)
    add(gap, disc("gap_tip", (BUTTON[0], tip_y), 5.3, WALL_TOP - 1, FACE + 1))
    tongue = box("tongue", tongue_x0, tongue_x1, tip_y, -36.0, WALL_TOP - 2, FACE + 2)
    add(tongue, disc("tongue_tip", (BUTTON[0], tip_y), 4.5, WALL_TOP - 2, FACE + 2))
    combine(gap, tongue, "DIFFERENCE")
    cut(body, gap)
    thin = box("thin", tongue_x0 - 0.1, tongue_x1 + 0.1, tip_y, -38.6, WALL_TOP - 0.2, FACE - 1.2)
    add(thin, disc("thin_tip", (BUTTON[0], tip_y), 4.6, WALL_TOP - 0.2, FACE - 1.2))
    cut(body, thin)
    add(body, disc("post", BUTTON, 2.0, BUTTON_TOP + 0.3, FACE - 1.1))

    if kind == "cat":
        cut(body, disc("infrared", INFRARED, 3.6, WALL_TOP - 1, FACE + 1))
        cut(body, ring(EYE, 4.5, 5.7))
        cut(body, arc((WINK[0], WINK[1] - 1.0), 3.6, 4.8, True))
        cut(body, ring(CHEEK, 2.2, 3.2))
        nose = [(CENTER - 2.6, -26.0), (CENTER + 2.6, -26.0), (CENTER, -29.4)]
        cut(body, extrude("nose", nose, CUT_LOW, CUT_HIGH))
        cut(body, arc((CENTER - 3.0, -30.6), 2.45, 3.55, False))
        cut(body, arc((CENTER + 3.0, -30.6), 2.45, 3.55, False))
        for sign in (-1, 1):
            cut(body, extrude("inner_ear", [(CENTER + sign * 39.6, HEAD_TOP + 9.5), (CENTER + sign * 43.3, HEAD_TOP - 1.5) if sign < 0 else (CENTER + sign * 29.5, HEAD_TOP - 1.5), (CENTER + sign * 29.5, HEAD_TOP - 1.5) if sign < 0 else (CENTER + sign * 43.3, HEAD_TOP - 1.5)], CUT_LOW, CUT_HIGH))
            for tilt, level in ((1.8, -27.5), (-1.8, -32.5)):
                near, far = CENTER + sign * 13.0, CENTER + sign * 29.0
                line = [(near, level - 0.55), (far, level + tilt - 0.55), (far, level + tilt + 0.55), (near, level + 0.55)]
                cut(body, extrude("whisker", line if sign > 0 else list(reversed(line)), CUT_LOW, CUT_HIGH))
        word(body, "blackout", (CENTER, 0.5), 30.0)
    else:
        cut(body, ring(EYE, 4.4, 5.5))
        cut(body, ring(EYE, 8.0, 9.2))
        cut(body, ring(WINK, 8.0, 9.2))
        cut(body, arc((WINK[0], WINK[1] + 1.2), 3.6, 4.8, False))
        beak = [(CENTER - 3.6, -23.5), (CENTER + 3.6, -23.5), (CENTER, -31.5)]
        cut(body, extrude("beak", beak, CUT_LOW, CUT_HIGH))
        for cx, cy in ((16.0, -41.0), (25.0, -41.0), (20.5, -47.0)):
            cut(body, arc((cx, cy), 2.6, 3.7, False))
            cut(body, arc((2 * CENTER - cx, cy), 2.6, 3.7, False))
        word(body, "blackout", (CENTER, 0.5), 30.0)
    return body


def report(body):
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    print(f"REPORT {body.name} size_mm={[round(high[i] - low[i], 1) for i in range(3)]} volume_cm3={round(volume / 1000, 1)} open_edges={loose}")


def flip_for_printing(body):
    for v in body.data.vertices:
        v.co.y = -v.co.y
        v.co.z = FACE - v.co.z
    body.data.update()


def export(body, name):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.stl_export(filepath=str(OUT / name), export_selected_objects=True)


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
    pictures = "--pictures" in sys.argv
    base = tray()
    report(base)
    export(base, "badge_tray.stl")
    if pictures:
        picture("badge_tray.png", (CENTER + 60, -150, 190), (CENTER, -26, 8))
    base.hide_render = True
    for kind in ("cat", "owl"):
        cover = lid(kind)
        report(cover)
        if pictures:
            picture(f"badge_{kind}.png", (CENTER, -20, 330), (CENTER, -20, FACE))
            picture(f"badge_{kind}_under.png", (CENTER - 70, -150, -160), (CENTER, -22, WALL_TOP))
        flip_for_printing(cover)
        export(cover, f"badge_lid_{kind}.stl")
        cover.hide_render = True


main()
