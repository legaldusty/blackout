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
RISE = 0.8
RELIEF = (FACE - 0.05, FACE + RISE)
PEGS = ((1.3, -51.9), (83.9, -51.8), (CENTER - 9.2, 8.7), (CENTER + 9.2, 8.7))


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


def ring(center, inner, outer, span=RELIEF):
    shape = disc("ring", center, outer, span[0], span[1])
    combine(shape, disc("hole", center, inner, span[0] - 0.3, span[1] + 0.3), "DIFFERENCE")
    return shape


def arc(center, inner, outer, upper, span=RELIEF):
    shape = ring(center, inner, outer, span)
    low, high = (center[1], center[1] + outer + 1) if upper else (center[1] - outer - 1, center[1])
    combine(shape, box("half", center[0] - outer - 1, center[0] + outer + 1, low, high, span[0] - 0.5, span[1] + 0.5), "INTERSECT")
    return shape


def bar(a, b, width, span=RELIEF):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    shape = extrude("bar", [(a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny), (b[0] + nx, b[1] + ny), (a[0] + nx, a[1] + ny)], span[0], span[1])
    for end in (a, b):
        combine(shape, disc("cap", end, width / 2, span[0], span[1], 24), "UNION")
    return shape


def poly(points, span=RELIEF):
    return extrude("poly", points, span[0], span[1])


def merged(name, shapes):
    first = shapes[0]
    first.name = name
    for other in shapes[1:]:
        combine(first, other, "UNION")
    return first


def mirror(point):
    return (2 * CENTER - point[0], point[1])


def word_mesh(text, center, width, z_low, z_high, flip):
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
        v.co.x = center[0] + (-1 if flip else 1) * (v.co.x - mid_x) * scale
        v.co.y = center[1] + (v.co.y - mid_y) * scale
        v.co.z = z_high if v.co.z > 0 else z_low
    work = bmesh.new()
    work.from_mesh(holder.data)
    bmesh.ops.remove_doubles(work, verts=work.verts, dist=0.001)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(holder.data)
    work.free()
    return holder


def tray():
    body = extrude("badge_tray", rounded(OUT_LEFT, OUT_RIGHT, OUT_BOTTOM, OUT_TOP, 5.0), -FLOOR, WALL_TOP)
    cut(body, box("inside", LEFT, RIGHT, BOTTOM, TOP, 0, WALL_TOP + 1))
    cut(body, box("usb", USB[0], USB[1], OUT_BOTTOM - 1, BOTTOM + 0.1, 10.5, WALL_TOP + 1))
    add(body, box("corner", LEFT - 0.1, 4.6, BOTTOM - 0.1, -49.6, -0.1, WALL_TOP))
    add(body, box("corner", 80.7, RIGHT + 0.1, BOTTOM - 0.1, -49.6, -0.1, WALL_TOP))
    add(body, box("hanger", CENTER - 11.5, CENTER + 11.5, OUT_TOP - 0.1, 12.6, -FLOOR, WALL_TOP))
    cut(body, box("hanger_slot", CENTER - 7, CENTER + 7, 7.0, 10.5, -FLOOR - 1, WALL_TOP + 1))
    for peg in PEGS:
        add(body, cone_peg(peg))
    cut(body, word_mesh("blackout", (CENTER, -26.0), 56.0, -FLOOR - 0.3, -FLOOR + 0.5, True))
    return body


def cone_peg(center):
    mesh = bpy.data.meshes.new("peg")
    work = bmesh.new()
    bmesh.ops.create_cone(work, cap_ends=True, segments=40, radius1=2.05, radius2=1.88, depth=1.3)
    bmesh.ops.translate(work, verts=work.verts, vec=Vector((center[0], center[1], WALL_TOP + 0.55)))
    work.to_mesh(mesh)
    work.free()
    return link("peg", mesh)


def plate(kind):
    body = extrude("plate", rounded(OUT_LEFT, OUT_RIGHT, OUT_BOTTOM, HEAD_TOP, 7.0), WALL_TOP, FACE)
    if kind == "cat":
        ear = [(OUT_LEFT + 0.6, HEAD_TOP - 8), (22.0, HEAD_TOP - 1), (3.5, HEAD_TOP + 17)]
    else:
        ear = [(OUT_LEFT + 0.6, HEAD_TOP - 8), (13.0, HEAD_TOP - 1), (-2.0, HEAD_TOP + 11)]
    add(body, extrude("ear", ear, WALL_TOP, FACE))
    add(body, extrude("ear", [mirror(p) for p in reversed(ear)], WALL_TOP, FACE))
    cut(body, box("lanyard", CENTER - 7, CENTER + 7, 7.0, 10.5, WALL_TOP - 1, FACE + 1))
    cut(body, disc("eye", EYE, 3.25, WALL_TOP - 1, FACE + 1))
    cut(body, disc("press", BUTTON, 3.95, WALL_TOP - 1, FACE + 1))
    for peg in PEGS:
        cut(body, disc("socket", peg, 2.0, WALL_TOP - 0.5, WALL_TOP + 1.4, 40))
    if kind == "cat":
        cut(body, disc("infrared", INFRARED, 3.6, WALL_TOP - 1, FACE + 1))
    return body


def cat_gold():
    shapes = [
        arc((WINK[0], WINK[1] - 1.6), 4.6, 6.8, True),
        ring(EYE, 3.6, 5.9),
        poly([(CENTER - 3.0, -25.6), (CENTER + 3.0, -25.6), (CENTER, -29.2)]),
        arc((CENTER - 3.3, -30.2), 2.5, 3.9, False),
        arc((CENTER + 3.3, -30.2), 2.5, 3.9, False),
    ]
    for sign in (-1, 1):
        for level, tilt in ((-27.0, 2.2), (-32.0, -1.6)):
            shapes.append(bar((CENTER + sign * 12.5, level), (CENTER + sign * 27.0, level + tilt), 1.3))
    inner = [(1.8, HEAD_TOP - 3.5), (17.0, HEAD_TOP + 0.5), (4.6, HEAD_TOP + 12.0)]
    shapes.append(poly(inner))
    shapes.append(poly([mirror(p) for p in reversed(inner)]))
    return merged("gold", shapes)


def cat_red():
    collar = box("collar", OUT_LEFT + 0.05, OUT_RIGHT - 0.05, -44.6, -41.2, RELIEF[0], RELIEF[1])
    blush = disc("blush", (79.6, -31.4), 3.3, RELIEF[0], RELIEF[1])
    glow = ring(INFRARED, 3.75, 5.3)
    combine(glow, box("trim", OUT_LEFT + 0.05, 20, -40, -20, RELIEF[0] - 1, RELIEF[1] + 1), "INTERSECT")
    return merged("red", [collar, blush, glow])


def owl_gold():
    shapes = [
        ring(EYE, 7.4, 10.3),
        ring(EYE, 3.6, 4.8),
        ring(WINK, 7.4, 10.3),
        arc((WINK[0], WINK[1] + 1.4), 3.4, 5.0, False),
        poly([(CENTER, -21.5), (CENTER + 4.0, -26.0), (CENTER, -32.8), (CENTER - 4.0, -26.0)]),
    ]
    for sign in (-1, 1):
        shapes.append(bar((CENTER + sign * 8.0, -8.0), (CENTER + sign * 25.0, -11.5), 2.0))
    for cx in (20.0, 29.0, 38.0, 47.0, 56.0, 65.0):
        shapes.append(arc((cx, -38.2), 2.9, 4.2, False))
    for cx in (15.5, 24.5, 33.5, 60.5, 69.5):
        shapes.append(arc((cx, -45.6), 2.9, 4.2, False))
    for shape in shapes:
        combine(shape, extrude("clip", rounded(OUT_LEFT + 0.05, OUT_RIGHT - 0.05, OUT_BOTTOM + 0.05, HEAD_TOP, 7.0), RELIEF[0] - 1, RELIEF[1] + 1), "INTERSECT")
    return merged("gold", shapes)


def plunger(kind):
    top = FACE + 1.3
    stem = disc("plunger_" + kind, BUTTON, 3.7, WALL_TOP - 0.15, top, 48)
    add(stem, disc("flange", BUTTON, 4.7, 17.6, WALL_TOP - 0.1, 48))
    mesh = bpy.data.meshes.new("taper")
    work = bmesh.new()
    bmesh.ops.create_cone(work, cap_ends=True, segments=48, radius1=2.2, radius2=4.55, depth=1.5)
    bmesh.ops.translate(work, verts=work.verts, vec=Vector((BUTTON[0], BUTTON[1], BUTTON_TOP + 0.2 + 0.75)))
    work.to_mesh(mesh)
    work.free()
    add(stem, link("taper", mesh))
    low, high = top - 0.45, top + 0.3
    if kind == "bell":
        cut(stem, box("slit", BUTTON[0] - 2.3, BUTTON[0] + 2.3, BUTTON[1] - 0.2, BUTTON[1] + 0.7, low, high))
        cut(stem, disc("dot", (BUTTON[0], BUTTON[1] - 1.6), 0.95, low, high, 24))
    else:
        heart = disc("lobe", (BUTTON[0] - 1.05, BUTTON[1] + 0.7), 1.25, low, high, 32)
        combine(heart, disc("lobe", (BUTTON[0] + 1.05, BUTTON[1] + 0.7), 1.25, low, high, 32), "UNION")
        combine(heart, extrude("point", [(BUTTON[0] - 2.2, BUTTON[1] + 0.2), (BUTTON[0] + 2.2, BUTTON[1] + 0.2), (BUTTON[0], BUTTON[1] - 2.4)], low, high), "UNION")
        cut(stem, heart)
    return stem, top


def copy_of(obj, name):
    twin = obj.copy()
    twin.data = obj.data.copy()
    twin.name = name
    bpy.context.scene.collection.objects.link(twin)
    return twin


def mend(body):
    work = bmesh.new()
    work.from_mesh(body.data)
    bmesh.ops.remove_doubles(work, verts=work.verts, dist=0.02)
    loose = [edge for edge in work.edges if not edge.is_manifold]
    if loose:
        bmesh.ops.holes_fill(work, edges=loose, sides=0)
    lonely = [edge for edge in work.edges if not edge.link_faces]
    if lonely:
        bmesh.ops.delete(work, geom=lonely, context="EDGES")
    bmesh.ops.triangulate(work, faces=work.faces)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(body.data)
    work.free()


def report(body):
    if body.name.endswith(("white", "one_color")) or body.name.startswith("plunger"):
        mend(body)
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    work = bmesh.new()
    work.from_mesh(body.data)
    for edge in work.edges:
        if not edge.is_manifold:
            print("OPEN", body.name, [tuple(round(c, 2) for c in v.co) for v in edge.verts])
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    print(f"REPORT {body.name} size_mm={[round(high[i] - low[i], 1) for i in range(3)]} volume_cm3={round(volume / 1000, 1)} open_edges={loose}")


def export(body, name):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.stl_export(filepath=str(OUT / name), export_selected_objects=True)


def tint(obj, color):
    material = bpy.data.materials.new(obj.name)
    material.diffuse_color = (*color, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def picture(name, position, aim):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 900
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


WHITE, GOLD, RED = (0.93, 0.93, 0.9), (0.83, 0.62, 0.18), (0.82, 0.1, 0.08)


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    pictures = "--pictures" in sys.argv
    base = tray()
    report(base)
    export(base, "badge_tray.stl")
    tint(base, WHITE)
    if pictures:
        picture("badge_tray.png", (CENTER + 70, -170, 200), (CENTER, -24, 8))
    base.hide_render = True
    for kind, button in (("cat", "bell"), ("owl", "heart")):
        white = plate(kind)
        white.name = f"{kind}_white"
        gold = cat_gold() if kind == "cat" else owl_gold()
        parts = [(white, WHITE, "white"), (gold, GOLD, "gold")]
        if kind == "cat":
            parts.append((cat_red(), RED, "red"))
        cap, top = plunger(button)
        for obj, color, label in parts:
            obj.name = f"{kind}_{label}"
            report(obj)
            export(obj, f"badge_{kind}_{label}.stl")
            tint(obj, color)
        report(cap)
        tint(cap, GOLD if button == "bell" else RED)
        if pictures:
            picture(f"badge_{kind}.png", (CENTER, -19, 330), (CENTER, -19, FACE))
            picture(f"badge_{kind}_angle.png", (CENTER - 95, -165, 150), (CENTER, -20, FACE))
        whole = copy_of(white, f"{kind}_one_color")
        for obj, _, label in parts[1:]:
            combine(whole, copy_of(obj, "tmp"), "UNION")
        report(whole)
        export(whole, f"badge_{kind}_one_color.stl")
        for v in cap.data.vertices:
            v.co.z = top - v.co.z
            v.co.x = 2 * BUTTON[0] - v.co.x
        cap.data.update()
        work = bmesh.new()
        work.from_mesh(cap.data)
        bmesh.ops.recalc_face_normals(work, faces=work.faces)
        work.to_mesh(cap.data)
        work.free()
        export(cap, f"badge_button_{button}.stl")
        for obj in [whole, cap] + [p[0] for p in parts]:
            obj.hide_render = True


main()
