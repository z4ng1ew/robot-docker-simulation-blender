# -*- coding: utf-8 -*-
"""
animate3d.py — 3D-анимация системы: три яруса роботов, шахты, зона КТЯ.
Вид «в объёме» с медленно облетающей камерой.

Как и animate.py — это ИЛЛЮСТРАТИВНАЯ кинематика на реальной геометрии
из config.py (числа берите из results/, ролик показывает устройство).

Запуск:
    python sim/animate3d.py                          # 24 c, 60 роботов/ярус
    python sim/animate3d.py --robots 90 --seconds 30 --out docs/anim3d.mp4

Выход: MP4 (нужен ffmpeg) или GIF (запасной вариант).
Генерация ~2-4 минуты: в 3D перерисовка кадра дороже, чем в 2D.
"""

import argparse
import os
import random
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import make_config  # noqa: E402

AMBER = "#ffb703"
NAVY = "#13294b"
PORT = "#8ecae6"
IND = "#90be6d"
CHUTE = "#e07b3a"
BOX = "#c9a26b"
SLAB = "#9db4cc"


class Bot:
    """Г-образные поездки «станция -> порт -> ближайшая станция»."""

    def __init__(self, rng, stations, ports, speed, z):
        self.rng, self.stations, self.ports = rng, stations, ports
        self.speed, self.z = speed, z
        self.x, self.y = rng.choice(stations)
        self.loaded = False
        self.pause = 0.0
        self._new_target()

    def _new_target(self):
        if self.loaded:
            self.tx, self.ty = min(self.stations,
                                   key=lambda s: abs(s[0] - self.x) + abs(s[1] - self.y))
        else:
            self.tx, self.ty = self.rng.choice(self.ports)
        self.loaded = not self.loaded

    def step(self, dt):
        if self.pause > 0:
            self.pause -= dt
            return
        d = self.speed * dt
        if abs(self.tx - self.x) > 0.05:
            self.x += max(-d, min(d, self.tx - self.x))
        elif abs(self.ty - self.y) > 0.05:
            self.y += max(-d, min(d, self.ty - self.y))
        else:
            self.pause = 2.0 if self.loaded else 1.2
            self._new_target()


def slab(ax, W, H, z, alpha=0.28):
    """Полупрозрачная плита яруса."""
    verts = [[(0, 0, z), (W, 0, z), (W, H, z), (0, H, z)]]
    ax.add_collection3d(Poly3DCollection(
        verts, facecolors=SLAB, edgecolors=NAVY, linewidths=1.2, alpha=alpha))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robots", type=int, default=60,
                    help="роботов НА ЯРУС в кадре (реально 460 — для читаемости меньше)")
    ap.add_argument("--seconds", type=float, default=24.0)
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--speedup", type=float, default=2.0)
    ap.add_argument("--out", default="docs/anim3d.mp4")
    ap.add_argument("--chutes", type=int, default=48,
                    help="сколько шахт показать (образец из 420)")
    a = ap.parse_args()

    c = make_config("S0_base")
    rng = random.Random(11)
    W, H = c.field_w, c.field_h
    tiers_z = [3.6, 6.8, 10.0]

    # геометрия портов и станций — как в модели
    mx, px, py = c.perimeter_margin, c.port_pitch_x, c.port_pitch_y
    ports = [(mx + col * px, mx + row * py)
             for col in range(20) for row in range(c.port_rows)]
    n_side = c.inductions_per_tier // 4
    stations = []
    for i in range(n_side):
        t = (i + 0.5) / n_side
        stations += [(t * W, 0.0), (t * W, H), (0.0, t * H), (W, t * H)]

    bots = [Bot(rng, stations, ports, c.robot_speed, z)
            for z in tiers_z for _ in range(a.robots)]

    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_box_aspect((W, H, 40))          # вертикаль слегка растянута для читаемости
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_zlim(0, 13)
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

    # статика: пол, плиты, порты, индукции, шахты-образцы, КТЯ
    slab(ax, W, H, 0.0, alpha=0.15)
    for z in tiers_z:
        slab(ax, W, H, z)
        pxs = [p[0] for p in ports[:: max(1, len(ports) // 240)]]
        pys = [p[1] for p in ports[:: max(1, len(ports) // 240)]]
        ax.scatter(pxs, pys, [z + 0.06] * len(pxs), s=4, c=PORT,
                   marker="s", depthshade=False)
        sxs = [s_[0] for s_ in stations]
        sys_ = [s_[1] for s_ in stations]
        ax.scatter(sxs, sys_, [z + 0.15] * len(sxs), s=34, c=IND,
                   marker="s", depthshade=False)
    sample = rng.sample(ports, a.chutes)
    for (x, y) in sample:                   # шахты вниз и короб под ними
        ax.plot([x, x], [y, y], [0.9, tiers_z[0]], c=CHUTE, lw=1.3, alpha=0.85)
        ax.bar3d(x - 0.5, y - 0.35, 0.0, 1.0, 0.7, 0.7,
                 color=BOX, edgecolor="#6b4f1d", alpha=0.95, shade=True)

    dots = ax.scatter([b.x for b in bots], [b.y for b in bots],
                      [b.z + 0.25 for b in bots], s=26, c=AMBER,
                      edgecolors="#7a5200", linewidths=0.4, depthshade=False)
    ax.set_title("АСР-100/400 «Рой» — 3 яруса, шахты, зона КТЯ "
                 f"(роботов в кадре: {a.robots}×3, время ×{a.speedup:g}; "
                 "иллюстративная кинематика)", fontsize=12, color=NAVY, pad=0)

    dt = a.speedup / a.fps
    frames = int(a.seconds * a.fps)

    def update(i):
        for b in bots:
            b.step(dt)
        dots._offsets3d = ([b.x for b in bots], [b.y for b in bots],
                           [b.z + 0.25 for b in bots])
        ax.view_init(elev=22 + 4 * (i / frames),      # лёгкий подъём камеры
                     azim=-55 + 70 * (i / frames))    # облёт на 70°
        return (dots,)

    ani = animation.FuncAnimation(fig, update, frames=frames,
                                  interval=1000 / a.fps, blit=False)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        ani.save(a.out, writer=animation.FFMpegWriter(fps=a.fps, bitrate=3600))
        print("[animate3d] сохранено:", a.out)
    except (FileNotFoundError, RuntimeError):
        gif = os.path.splitext(a.out)[0] + ".gif"
        ani.save(gif, writer=animation.PillowWriter(fps=min(a.fps, 10)))
        print("[animate3d] ffmpeg не найден — сохранён GIF:", gif)


if __name__ == "__main__":
    main()
