# -*- coding: utf-8 -*-
"""
blender_anim.py — фотореалистичная 3D-анимация АСР-100/400 «Рой» в Blender.

Скрипт сам строит сцену (3 яруса, порты, шахты, короба, роботы),
анимирует роботов той же Г-образной кинематикой, что animate.py,
ставит камеру с облётом, свет — и рендерит MP4.

УСТАНОВКА Blender на Fedora (любой вариант):
    sudo dnf install blender
    # или: flatpak install flathub org.blender.Blender

ЗАПУСК (фоновый рендер, без окна):
    blender -b -P cad/blender_anim.py
    # flatpak-вариант:
    flatpak run org.blender.Blender -b -P cad/blender_anim.py

Результат: cad/roy_3d.mp4 (1920×1080, 24 кадра/с, ~20 c).
На RTX 3060 рендер ~3-8 минут (EEVEE) или ~15-25 минут (Cycles).

Если фоновый EEVEE-рендер упадёт с ошибкой про GPU/EGL (бывает без
монитора) — запусти БЕЗ «-b»: откроется окно с готовой сценой,
дальше просто нажми Ctrl+F12 (рендер анимации).

Параметры — в блоке НАСТРОЙКИ ниже.
"""

import math
import random

import bpy

# ----------------------------------------------------------- НАСТРОЙКИ
SECONDS = 20          # длительность ролика
FPS = 24
ROBOTS_PER_TIER = 70  # в кадре (реально 460 — для читаемости меньше)
SPEEDUP = 2.0         # ускорение времени
CHUTES_SAMPLE = 40    # сколько шахт показать (из 420)
RES_X, RES_Y = 1920, 1080
OUT_PATH = "//roy_3d.mp4"   # '//' = рядом с .blend/скриптом

# геометрия (метры) — синхронизирована с sim/config.py
FIELD_W, FIELD_H = 60.0, 46.2
TIERS_Z = [3.6, 6.8, 10.0]
SLAB_T = 0.18
MARGIN, PITCH_X, PITCH_Y = 3.0, 2.4, 1.8
PORT_COLS, PORT_ROWS = 20, 20      # рисуем основные 20×20
INDUCTIONS = 20
ROBOT_SPEED = 3.0
ROBOT_DIMS = (0.72, 0.54, 0.33)

rng = random.Random(7)

# ----------------------------------------------------------- сцена с нуля
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = SECONDS * FPS

# движок: пробуем EEVEE Next (Blender 4.2+) -> EEVEE -> Cycles на GPU
engine_set = False
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = eng
        engine_set = True
        break
    except TypeError:
        continue
if engine_set and hasattr(scene, "eevee"):
    try:
        scene.eevee.taa_render_samples = 24
    except AttributeError:
        pass
if not engine_set:
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                break
            except TypeError:
                continue
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception:
        pass  # останется CPU — просто медленнее

# вывод в MP4
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "HIGH"
scene.render.ffmpeg.audio_codec = "NONE"
scene.render.filepath = OUT_PATH

# мир (фон)
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.93, 0.95, 0.98, 1.0)
    bg.inputs[1].default_value = 1.0

# ----------------------------------------------------------- материалы
def mat(name, rgba, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        try:
            b.inputs["Emission Color"].default_value = rgba
            b.inputs["Emission Strength"].default_value = emit
        except KeyError:
            pass
    return m

M_SLAB = mat("slab", (0.62, 0.70, 0.80, 1), rough=0.7)
M_PORT = mat("port", (0.10, 0.16, 0.28, 1), rough=0.6)
M_ROBOT = mat("robot", (1.00, 0.72, 0.02, 1), rough=0.35, metal=0.2, emit=0.25)
M_IND = mat("induct", (0.42, 0.72, 0.35, 1), rough=0.5)
M_CHUTE = mat("chute", (0.88, 0.48, 0.16, 1), rough=0.4, metal=0.4)
M_BOX = mat("box", (0.79, 0.64, 0.42, 1), rough=0.8)
M_FLOOR = mat("floor", (0.85, 0.87, 0.90, 1), rough=0.9)
M_COL = mat("col", (0.45, 0.48, 0.53, 1), rough=0.6, metal=0.5)

coll = scene.collection

def add_cube(name, size, loc, material):
    """Куб-примитив: size=(x,y,z), loc — центр."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(material)
    return o

def clone(src, name, loc):
    """Дешёвая копия: общий меш, свой объект."""
    o = bpy.data.objects.new(name, src.data)
    o.location = loc
    o.scale = src.scale
    coll.objects.link(o)
    return o

# ----------------------------------------------------------- статика
add_cube("floor", (FIELD_W + 8, FIELD_H + 8, 0.2),
         (FIELD_W / 2, FIELD_H / 2, -0.1), M_FLOOR)

for z in TIERS_Z:                              # плиты ярусов
    add_cube(f"slab_{z}", (FIELD_W, FIELD_H, SLAB_T),
             (FIELD_W / 2, FIELD_H / 2, z - SLAB_T / 2), M_SLAB)

for i in range(0, 6):                          # колонны каркаса
    for j in range(0, 5):
        add_cube(f"col_{i}_{j}", (0.4, 0.4, TIERS_Z[-1]),
                 (i * 12.0, j * 11.5, TIERS_Z[-1] / 2), M_COL)

ports_xy = [(MARGIN + c * PITCH_X, MARGIN + r * PITCH_Y)
            for c in range(PORT_COLS) for r in range(PORT_ROWS)]

port_proto = add_cube("port_proto", (0.8, 0.6, 0.06),
                      (ports_xy[0][0], ports_xy[0][1], TIERS_Z[0] + 0.03),
                      M_PORT)
for z in TIERS_Z:                              # тёмные плашки портов
    for k, (x, y) in enumerate(ports_xy):
        if z == TIERS_Z[0] and k == 0:
            continue
        clone(port_proto, f"port_{z}_{k}", (x, y, z + 0.03))

n_side = INDUCTIONS // 4
ind_xy = []
for i in range(n_side):
    t = (i + 0.5) / n_side
    ind_xy += [(t * FIELD_W, -0.9), (t * FIELD_W, FIELD_H + 0.9),
               (-0.9, t * FIELD_H), (FIELD_W + 0.9, t * FIELD_H)]
ind_proto = add_cube("ind_proto", (1.2, 1.2, 0.9),
                     (ind_xy[0][0], ind_xy[0][1], TIERS_Z[0] + 0.45), M_IND)
for z in TIERS_Z:                              # индукционные станции
    for k, (x, y) in enumerate(ind_xy):
        if z == TIERS_Z[0] and k == 0:
            continue
        clone(ind_proto, f"ind_{z}_{k}", (x, y, z + 0.45))

chute_sample = rng.sample(ports_xy, CHUTES_SAMPLE)
bpy.ops.mesh.primitive_cylinder_add(radius=0.25,
                                    depth=TIERS_Z[0] - 0.9,
                                    location=(chute_sample[0][0],
                                              chute_sample[0][1],
                                              (TIERS_Z[0] - 0.9) / 2 + 0.9))
chute_proto = bpy.context.active_object
chute_proto.data.materials.append(M_CHUTE)
box_proto = add_cube("box_proto", (0.6, 0.4, 0.4),
                     (chute_sample[0][0], chute_sample[0][1], 0.6), M_BOX)
for k, (x, y) in enumerate(chute_sample):      # шахты + короба под ними
    if k:
        clone(chute_proto, f"chute_{k}",
              (x, y, (TIERS_Z[0] - 0.9) / 2 + 0.9))
        clone(box_proto, f"box_{k}", (x, y, 0.6))

# ----------------------------------------------------------- роботы + анимация
class Bot:
    def __init__(self, z):
        self.z = z
        self.x, self.y = rng.choice(ind_xy)
        self.loaded = False
        self.pause = 0.0
        self._retarget()

    def _retarget(self):
        if self.loaded:
            self.tx, self.ty = min(ind_xy, key=lambda s: abs(s[0] - self.x)
                                   + abs(s[1] - self.y))
        else:
            self.tx, self.ty = rng.choice(ports_xy)
        self.loaded = not self.loaded

    def step(self, dt):
        if self.pause > 0:
            self.pause -= dt
            return
        d = ROBOT_SPEED * dt
        if abs(self.tx - self.x) > 0.05:
            self.x += max(-d, min(d, self.tx - self.x))
        elif abs(self.ty - self.y) > 0.05:
            self.y += max(-d, min(d, self.ty - self.y))
        else:
            self.pause = 2.0 if self.loaded else 1.2
            self._retarget()


robot_proto = add_cube("robot_proto", ROBOT_DIMS, (0, 0, -5), M_ROBOT)
robot_proto.hide_render = True
bots, objs = [], []
for z in TIERS_Z:
    for i in range(ROBOTS_PER_TIER):
        b = Bot(z)
        o = clone(robot_proto, f"bot_{z}_{i}",
                  (b.x, b.y, z + ROBOT_DIMS[2] / 2))
        o.hide_render = False
        bots.append(b)
        objs.append(o)

KEY_EVERY = 4                                   # ключевой кадр раз в 4 кадра
dt = SPEEDUP / FPS
for f in range(1, scene.frame_end + 1):
    for b in bots:
        b.step(dt)
    if f % KEY_EVERY == 0 or f == 1:
        for b, o in zip(bots, objs):
            o.location = (b.x, b.y, b.z + ROBOT_DIMS[2] / 2)
            o.keyframe_insert("location", frame=f)

for o in objs:                                  # линейное движение без «плаваний»
    if o.animation_data and o.animation_data.action:
        for fc in o.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

# ----------------------------------------------------------- свет и камера
bpy.ops.object.light_add(type="SUN", location=(30, -40, 60))
sun = bpy.context.active_object
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(20))
bpy.ops.object.light_add(type="AREA",
                         location=(FIELD_W / 2, FIELD_H / 2, 30))
area = bpy.context.active_object
area.data.energy = 6000
area.data.size = 60

target = bpy.data.objects.new("target", None)   # центр интереса
target.location = (FIELD_W / 2, FIELD_H / 2, 5.5)
coll.objects.link(target)
rig = bpy.data.objects.new("cam_rig", None)      # вращающийся штатив
rig.location = target.location
coll.objects.link(rig)

bpy.ops.object.camera_add(location=(FIELD_W / 2 + 78, FIELD_H / 2 - 62, 42))
cam = bpy.context.active_object
cam.data.lens = 40
tr = cam.constraints.new("TRACK_TO")
tr.target = target
cam.parent = rig
cam.matrix_parent_inverse = rig.matrix_world.inverted()
scene.camera = cam

rig.rotation_euler = (0, 0, 0)                   # облёт на 70°
rig.keyframe_insert("rotation_euler", frame=1)
rig.rotation_euler = (0, 0, math.radians(70))
rig.keyframe_insert("rotation_euler", frame=scene.frame_end)
for fc in rig.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

# ----------------------------------------------------------- рендер
if bpy.app.background:                           # запущено с «-b» — рендерим
    print(f"[blender_anim] движок: {scene.render.engine}, "
          f"кадров: {scene.frame_end}, вывод: {OUT_PATH}")
    bpy.ops.render.render(animation=True)
    print("[blender_anim] готово:", OUT_PATH)
else:
    print("[blender_anim] сцена построена. Рендер анимации: Ctrl+F12")
