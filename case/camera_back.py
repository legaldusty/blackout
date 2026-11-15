import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent

WALL_IN = 31.0
WALL_OUT = 33.2
FLOOR = -2.2
BACK = 108.0
PLATE = 2.4
GAP = 0.2
BOARD_HALF = 28.0
BOARD_END = 107.0
SIDE = WALL_IN - GAP
GRIP = BOARD_HALF + 0.3
REST = BACK + 0.05
FAR = REST + PLATE

ARM = 2.4
ARM_LOW, ARM_HIGH = 12.3, 35.7
CATCH = 0.9
SLOTS = {-1: (84.0, 88.0), 1: (80.0, 84.0)}
POSTS = (-8.0, 10.0)
POST_WIDE = 2.0


def link(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def box(name, xa, xb, ya, yb, za, zb):
    x0, x1 = sorted((xa, xb))
    y0, y1 = sorted((ya, yb))
    z0, z1 = sorted((za, zb))
    work = bmesh.new()
    bmesh.ops.create_cube(work, size=1.0)
    for v in work.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    mesh = bpy.data.meshes.new(name)
    work.to_mesh(mesh)
    work.free()
    return link(name, mesh)


def ramp(name, outline, y0, y1):
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


def keeper():
    part = box("camera_back", -WALL_OUT, WALL_OUT, FLOOR, 1.0, REST, FAR)
    for side in (-1, 1):
        add(part, box("upright", side * WALL_OUT, side * (SIDE - ARM), FLOOR, 37.5, REST, FAR))
        add(part, box("foot", side * (SIDE - ARM), side * (GRIP - 1.5), FLOOR, 5.5, REST, FAR))
        add(part, box("jaw", side * SIDE, side * GRIP, 0.1, 5.5, 100.0, REST + 0.1))
        add(part, box("corner", side * GRIP, side * (GRIP - 1.5), 0.1, 5.5, BOARD_END + 0.35, REST + 0.1))
        low, high = SLOTS[side]
        tip = low - 4.5
        add(part, box("arm", side * SIDE, side * (SIDE - ARM), ARM_LOW, ARM_HIGH, tip, REST + 0.1))
        flat = high - 0.3
        outline = [(side * (SIDE - 0.1), low - 0.5), (side * (SIDE + CATCH), low + 2.2), (side * (SIDE + CATCH), flat - 0.4), (side * (SIDE + CATCH - 0.4), flat), (side * (SIDE - 0.1), flat)]
        add(part, ramp("catch", outline, ARM_LOW, ARM_HIGH))
    for x in POSTS:
        add(part, box("post", x - POST_WIDE / 2, x + POST_WIDE / 2, FLOOR, 8.0, REST, FAR))
        add(part, box("post_tip", x - POST_WIDE / 2, x + POST_WIDE / 2, 0.1, 8.0, BOARD_END + 0.35, REST + 0.1))
    return part


def report(body):
    work = bmesh.new()
    work.from_mesh(body.data)
    loose = sum(1 for edge in work.edges if not edge.is_manifold)
    volume = work.calc_volume()
    work.free()
    low = [min(v.co[i] for v in body.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in body.data.vertices) for i in range(3)]
    size = [round(high[i] - low[i], 1) for i in range(3)]
    print(f"REPORT {body.name} size_mm={size} volume_cm3={round(abs(volume) / 1000, 1)} open_edges={loose}")


def overlap(a, b):
    probe = a.copy()
    probe.data = a.data.copy()
    bpy.context.scene.collection.objects.link(probe)
    tool = b.copy()
    tool.data = b.data.copy()
    bpy.context.scene.collection.objects.link(tool)
    combine(probe, tool, "INTERSECT")
    work = bmesh.new()
    work.from_mesh(probe.data)
    volume = abs(work.calc_volume()) if work.faces else 0.0
    work.free()
    bpy.data.objects.remove(probe, do_unlink=True)
    return round(volume, 2)


def housing():
    source = (OUT / "camera_body.py").read_text()
    space = {"__file__": str(OUT / "camera_body.py"), "__name__": "case"}
    exec(compile(source[: source.rindex("\nmain()")], "camera_body.py", "exec"), space)
    body = space["shell"]()
    space["pocket"](body)
    lid = space["roof"]()
    for v in lid.data.vertices:
        v.co.y, v.co.z = space["ROOF_IN"] + space["ROOF_PLATE"] - v.co.z, v.co.y
    lid.data.update()
    work = bmesh.new()
    work.from_mesh(lid.data)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(lid.data)
    work.free()
    return body, lid


def board():
    pi = box("pi", -BOARD_HALF, BOARD_HALF, 1.4, 3.0, 22.0, BOARD_END)
    for name, left, right, tall in (("network", 2.25, 18.25, 13.5), ("usb", 21.75, 36.25, 16.0), ("usb", 39.75, 54.25, 16.0)):
        add(pi, box(name, left - BOARD_HALF, right - BOARD_HALF, 3.0, 3.0 + tall, 86.0, 110.0))
    return pi


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


def tint(obj, color):
    material = bpy.data.materials.new(obj.name)
    material.diffuse_color = (*color, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(material)


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    part = keeper()
    report(part)
    body, lid = housing()
    pi = board()
    print(f"FIT body overlap_mm3={overlap(part, body)}")
    print(f"FIT roof overlap_mm3={overlap(part, lid)}")
    print(f"FIT pi overlap_mm3={overlap(part, pi)}")
    if "--pictures" in sys.argv:
        tint(part, (0.9, 0.14, 0.1))
        tint(body, (0.85, 0.85, 0.83))
        tint(lid, (0.85, 0.85, 0.83))
        tint(pi, (0.15, 0.45, 0.25))
        for obj in (part, body, lid, pi):
            for v in obj.data.vertices:
                v.co.y, v.co.z = -v.co.z, v.co.y
            obj.data.update()
            work = bmesh.new()
            work.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(work, faces=work.faces)
            work.to_mesh(obj.data)
            work.free()
        picture("back_fitted.png", (85, -290, 95), (0, -95, 16))
        body.hide_render = lid.hide_render = pi.hide_render = True
        picture("back_alone.png", (-95, -10, 95), (0, -98, 14))
        for v in part.data.vertices:
            v.co.y, v.co.z = v.co.z, -v.co.y
        part.data.update()
    for v in part.data.vertices:
        v.co.y, v.co.z = -v.co.y, FAR - v.co.z
    part.data.update()
    work = bmesh.new()
    work.from_mesh(part.data)
    bmesh.ops.recalc_face_normals(work, faces=work.faces)
    work.to_mesh(part.data)
    work.free()
    report(part)
    bpy.ops.object.select_all(action="DESELECT")
    part.select_set(True)
    bpy.context.view_layer.objects.active = part
    bpy.ops.wm.stl_export(filepath=str(OUT / "camera_back.stl"), export_selected_objects=True)


main()
