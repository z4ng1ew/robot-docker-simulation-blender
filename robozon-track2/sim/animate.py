# -*- coding: utf-8 -*-
"""
animate.py — 2D-анимация движения роботов по ярусу (вид сверху).

Назначение: наглядный ролик для видеодемонстрации и презентации.
Это ИЛЛЮСТРАТИВНАЯ кинематика (роботы ездят по реальной геометрии яруса
по манхэттеновским маршрутам «станция → порт → ближайшая станция»),
а не покадровая выгрузка DES-модели: числа берите из results/, а этот
ролик показывает, КАК устроено движение.

Запуск:
    python sim/animate.py                    # 20 c ролика, robots=140
    python sim/animate.py --robots 200 --seconds 30 --out docs/tier_anim.mp4

Выход: MP4 (нужен ffmpeg) или GIF (без ffmpeg, автоматический запасной
вариант). ~1-2 мин генерации.
"""

import argparse
import os
import random
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation, patches

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import make_config  # noqa: E402

AMBER = "#ffb703"
NAVY = "#13294b"
PORT = "#8ecae6"
RESV = "#ffd166"
REJ = "#e63946"
IND = "#90be6d"


class Bot:
    """Робот: едет по Г-образному маршруту (сначала X, потом Y)."""

    def __init__(self, rng, stations, ports, speed):
        self.rng = rng
        self.stations = stations
        self.ports = ports
        self.speed = speed
        self.x, self.y = rng.choice(stations)
        self.loaded = False
        self._new_target()

    def _new_target(self):
        if self.loaded:                       # порожний -> к ближайшей станции
            self.tx, self.ty = min(
                self.stations, key=lambda s: abs(s[0] - self.x) + abs(s[1] - self.y))
        else:                                 # гружёный -> случайный порт
            self.tx, self.ty = self.rng.choice(self.ports)
        self.loaded = not self.loaded
        self.pause = 0.0

    def step(self, dt):
        if self.pause > 0:                    # посадка/сброс
            self.pause -= dt
            return
        d = self.speed * dt
        if abs(self.tx - self.x) > 0.05:      # сначала по X
            self.x += max(-d, min(d, self.tx - self.x))
        elif abs(self.ty - self.y) > 0.05:    # потом по Y
            self.y += max(-d, min(d, self.ty - self.y))
        else:                                  # приехали
            self.pause = 2.0 if self.loaded else 1.2
            self._new_target()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robots", type=int, default=140,
                    help="роботов в кадре (для наглядности меньше реальных 460)")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--speedup", type=float, default=2.0,
                    help="ускорение времени в ролике")
    ap.add_argument("--out", default="docs/tier_anim.mp4")
    a = ap.parse_args()

    c = make_config("S0_base")
    rng = random.Random(7)

    # геометрия из конфига — та же, что в модели
    mx, px, py = c.perimeter_margin, c.port_pitch_x, c.port_pitch_y
    ports, resv, rej = [], [], []
    for col in range(c.port_cols):
        for row in range(c.port_rows):
            xy = (mx + col * px, mx + row * py)
            if col < 20:
                ports.append(xy)
            elif row < 16:
                resv.append(xy)
            elif row < 18:
                rej.append(xy)
    W, H = c.field_w, c.field_h
    stations = []
    for i in range(c.inductions_per_tier // 4):
        t = (i + 0.5) / (c.inductions_per_tier // 4)
        stations += [(t * W, 0.0), (t * W, H), (0.0, t * H), (W, t * H)]

    bots = [Bot(rng, stations, ports, c.robot_speed) for _ in range(a.robots)]

    fig, ax = plt.subplots(figsize=(12.8, 9.6), dpi=100)
    ax.set_xlim(-3, W + 3)
    ax.set_ylim(-3, H + 3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(patches.Rectangle((0, 0), W, H, fc="#f7f7f7", ec=NAVY, lw=2))
    ax.scatter(*zip(*ports), s=14, c=PORT, marker="s", zorder=2)
    if resv:
        ax.scatter(*zip(*resv), s=14, c=RESV, marker="s", zorder=2)
    if rej:
        ax.scatter(*zip(*rej), s=18, c=REJ, marker="s", zorder=2)
    ax.scatter(*zip(*stations), s=90, c=IND, marker="s", zorder=3,
               edgecolors="#2d6a4f")
    dots = ax.scatter([b.x for b in bots], [b.y for b in bots],
                      s=42, c=AMBER, edgecolors="#7a5200", zorder=4)
    ax.set_title(
        f"АСР-100/400 «Рой» — ярус, вид сверху (роботов в кадре: {a.robots}, "
        f"время ×{a.speedup:g}; иллюстративная кинематика)",
        fontsize=13, color=NAVY)

    dt = a.speedup / a.fps

    def update(_):
        for b in bots:
            b.step(dt)
        dots.set_offsets([(b.x, b.y) for b in bots])
        return (dots,)

    frames = int(a.seconds * a.fps)
    ani = animation.FuncAnimation(fig, update, frames=frames,
                                  interval=1000 / a.fps, blit=True)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        ani.save(a.out, writer=animation.FFMpegWriter(fps=a.fps, bitrate=3200))
        print("[animate] сохранено:", a.out)
    except (FileNotFoundError, RuntimeError):
        gif = os.path.splitext(a.out)[0] + ".gif"
        ani.save(gif, writer=animation.PillowWriter(fps=min(a.fps, 12)))
        print("[animate] ffmpeg не найден — сохранён GIF:", gif)


if __name__ == "__main__":
    main()
