# -*- coding: utf-8 -*-
"""
generate_layout.py — параметрическая 3D-компоновка АСР-100/400 «Рой»
для FreeCAD 0.21+ (проверено на 0.21.2 и 1.0).

Что строит (упрощённые твёрдые тела, для компоновочной проверки
и рендеров, не для деталировки):
  * плиты трёх ярусов с вырезами-портами 21×20;
  * колонны каркаса;
  * шахты (трубы) от портов первого яруса до отм. КТЯ (образец: первые
    3 ряда, чтобы модель оставалась лёгкой; полный режим — FULL_CHUTES);
  * КТЯ-станции (короб + рамка) под шахтами-образцами;
  * индукционные станции по периметру каждого яруса;
  * 12 наклонных лент подачи;
  * 20 отводящих лент на отм. 0;
  * роботы-габариты (по 24 шт/ярус для наглядности).

Как запустить:
  1) FreeCAD → Macro → Macros… → создать «robozon_layout» → вставить файл
     → Execute;  или из консоли:
       freecadcmd cad/generate_layout.py
  2) Результат: документ «ASR100_400» + экспорт cad/asr100_400.step
     (и cad/asr100_400_preview.png, если запущено с GUI).

Все размеры — в мм (стандарт FreeCAD). Параметры — блок PARAMS.
"""

import os

import FreeCAD as App
import Part

# --------------------------------------------------------------- PARAMS
PARAMS = dict(
    tiers=3,
    tier_z=[3600.0, 6800.0, 10000.0],   # отметки ярусов, мм
    slab_t=180.0,                        # толщина плиты
    field_w=60000.0, field_h=46200.0,    # поле яруса
    margin=3000.0,                       # периметр до первого порта
    port_cols=21, port_rows=20,
    pitch_x=2400.0, pitch_y=1800.0,
    port_w=800.0, port_l=600.0,          # вырез порта
    chute_d=500.0, chute_wall=6.0,
    col_step=12000.0, col_a=400.0,       # колонны
    box_w=600.0, box_l=400.0, box_h=400.0,
    robot=(720.0, 540.0, 330.0),
    robots_preview_per_tier=24,
    FULL_CHUTES=False,                    # True = все 1254 шахты (тяжело)
)

DOCNAME = "ASR100_400"
HERE = os.path.dirname(os.path.abspath(__file__)) or "."


def make_doc():
    if DOCNAME in App.listDocuments():
        App.closeDocument(DOCNAME)
    return App.newDocument(DOCNAME)


def add(doc, shape, name, color=(0.7, 0.7, 0.7)):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    if App.GuiUp:
        obj.ViewObject.ShapeColor = color
    return obj


def port_centers(p):
    xs = [p["margin"] + c * p["pitch_x"] for c in range(p["port_cols"])]
    ys = [p["margin"] + r * p["pitch_y"] for r in range(p["port_rows"])]
    return xs, ys


def build():
    p = PARAMS
    doc = make_doc()
    xs, ys = port_centers(p)

    # ---- плиты ярусов с вырезами портов
    for ti in range(p["tiers"]):
        z = p["tier_z"][ti]
        slab = Part.makeBox(p["field_w"], p["field_h"], p["slab_t"],
                            App.Vector(0, 0, z))
        holes = []
        for x in xs:
            for y in ys:
                holes.append(Part.makeBox(
                    p["port_w"], p["port_l"], p["slab_t"] + 2,
                    App.Vector(x - p["port_w"] / 2, y - p["port_l"] / 2,
                               z - 1)))
        slab = slab.cut(Part.makeCompound(holes))
        add(doc, slab, f"Slab_T{ti+1}", (0.55, 0.68, 0.80))

        # индукции по периметру: 5 на сторону
        for i in range(5):
            t = (i + 0.5) / 5
            for (x, y) in [(t * p["field_w"], -1500.0),
                           (t * p["field_w"], p["field_h"] + 300.0),
                           (-1500.0, t * p["field_h"]),
                           (p["field_w"] + 300.0, t * p["field_h"])]:
                st = Part.makeBox(1200, 1200, 900,
                                  App.Vector(x - 600, y - 600,
                                             z + p["slab_t"]))
                add(doc, st, f"Induct_T{ti+1}_{i}_{int(x)}_{int(y)}",
                    (0.42, 0.72, 0.35))

        # роботы-габариты для наглядности
        rw, rl, rh = p["robot"]
        n = p["robots_preview_per_tier"]
        for k in range(n):
            gx = p["margin"] + (k % 8) * 7000.0 + 1200.0
            gy = p["margin"] + (k // 8) * 13000.0 + 900.0
            rb = Part.makeBox(rw, rl, rh,
                              App.Vector(gx, gy, z + p["slab_t"]))
            add(doc, rb, f"Robot_T{ti+1}_{k}", (1.0, 0.72, 0.02))

    # ---- колонны каркаса
    nx = int(p["field_w"] // p["col_step"]) + 1
    ny = int(p["field_h"] // p["col_step"]) + 1
    top = p["tier_z"][-1] + p["slab_t"]
    for i in range(nx):
        for j in range(ny):
            col = Part.makeBox(p["col_a"], p["col_a"], top,
                               App.Vector(i * p["col_step"] - p["col_a"] / 2,
                                          j * p["col_step"] - p["col_a"] / 2,
                                          0))
            add(doc, col, f"Col_{i}_{j}", (0.45, 0.45, 0.5))

    # ---- шахты и КТЯ-станции (образец: первые 3 ряда либо все)
    rows = range(p["port_rows"]) if p["FULL_CHUTES"] else range(3)
    z_top = p["tier_z"][0]
    for r in rows:
        for x in xs[:20]:                      # 20 основных колонок
            y = ys[r]
            outer = Part.makeCylinder(p["chute_d"] / 2, z_top - 900.0,
                                      App.Vector(x, y, 900.0))
            inner = Part.makeCylinder(p["chute_d"] / 2 - p["chute_wall"],
                                      z_top - 900.0,
                                      App.Vector(x, y, 899.0))
            add(doc, outer.cut(inner), f"Chute_{r}_{int(x)}",
                (0.9, 0.55, 0.25))
            box = Part.makeBox(p["box_w"], p["box_l"], p["box_h"],
                               App.Vector(x - p["box_w"] / 2,
                                          y - p["box_l"] / 2, 400.0))
            add(doc, box, f"KTYA_{r}_{int(x)}", (0.82, 0.68, 0.45))

    # ---- наклонные ленты подачи (12) и отводящие (20)
    for k in range(12):
        ti = k % 3
        z = p["tier_z"][ti] + p["slab_t"]
        length = (z ** 2 + (z * 2.2) ** 2) ** 0.5
        belt = Part.makeBox(length, 800, 120)
        belt.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), -24.5)
        belt.translate(App.Vector(-z * 2.2 - 1500,
                                  4000 + (k // 3) * 11000, 0))
        add(doc, belt, f"InfeedBelt_{k}", (0.18, 0.42, 0.31))
    for k in range(20):
        y = p["margin"] + k * p["pitch_y"] - 600
        belt = Part.makeBox(p["field_w"] + 8000, 700, 100,
                            App.Vector(-2000, y, 950))
        add(doc, belt, f"Takeaway_{k}", (0.66, 0.7, 0.74))

    doc.recompute()

    # ---- экспорт
    step_path = os.path.join(HERE, "asr100_400.step")
    Part.export([o for o in doc.Objects], step_path)
    App.Console.PrintMessage(f"[layout] STEP: {step_path}\n")

    if App.GuiUp:
        import FreeCADGui as Gui
        Gui.activeDocument().activeView().viewAxometric()
        Gui.SendMsgToActiveView("ViewFit")
        png = os.path.join(HERE, "asr100_400_preview.png")
        Gui.activeDocument().activeView().saveImage(png, 1920, 1080, "White")
        App.Console.PrintMessage(f"[layout] PNG: {png}\n")


build()
