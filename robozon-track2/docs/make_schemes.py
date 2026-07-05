# -*- coding: utf-8 -*-
"""
make_schemes.py — генератор инженерных схем (SVG) для отчёта.

Запуск:  python docs/make_schemes.py
Выход:   docs/schemes/*.svg  (5 схем)
"""

import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemes")
os.makedirs(OUT, exist_ok=True)

FONT = 'font-family="DejaVu Sans, Arial, sans-serif"'


def save(name, w, h, body, title):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">\n'
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>\n'
           f'<text x="{w/2}" y="26" text-anchor="middle" {FONT} '
           f'font-size="17" font-weight="bold" fill="#111">{title}</text>\n'
           f'{body}\n</svg>\n')
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("ok", path)


def txt(x, y, s, size=11, anchor="middle", color="#111", bold=False, rot=None):
    w = ' font-weight="bold"' if bold else ""
    r = f' transform="rotate({rot} {x} {y})"' if rot else ""
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" {FONT} '
            f'font-size="{size}" fill="{color}"{w}{r}>{s}</text>\n')


def rect(x, y, w, h, fill, stroke="#333", sw=1, rx=0, opacity=1):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}" rx="{rx}" '
            f'opacity="{opacity}"/>\n')


def line(x1, y1, x2, y2, stroke="#333", sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}/>\n')


def arrow(x1, y1, x2, y2, color="#c00", sw=1.6):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}" marker-end="url(#arr)"/>\n')


DEFS = ('<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" '
        'refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="context-stroke"/>'
        '</marker></defs>\n')


# =========================================================== 1. план яруса
def scheme_layout():
    W, H = 980, 700
    b = DEFS
    # масштаб: поле 60×46.2 м -> 780×600 px, старт (110, 60)
    sx, sy, k = 110, 60, 13.0
    fw, fh = 60.0 * k, 46.2 * k
    b += rect(sx, sy, fw, fh, "#f7f7f7", "#222", 2)
    # порты 21×20
    mx = 3.0
    for col in range(21):
        for row in range(20):
            x = sx + (mx + col * 2.4) * k - 5
            y = sy + (mx + row * 1.8) * k - 4
            if col < 20:
                fill = "#8ecae6"          # основные 400
            elif row < 16:
                fill = "#ffb703"          # резервные 16
            elif row < 18:
                fill = "#e63946"          # реджект 2
            else:
                continue
            b += rect(x, y, 10, 8, fill, "#456", 0.5)
    # индукционные станции по периметру (по 5 на сторону)
    for i in range(5):
        t = (i + 0.5) / 5
        for (x, y, w, h) in [(sx + t * fw - 14, sy - 16, 28, 12),
                             (sx + t * fw - 14, sy + fh + 4, 28, 12),
                             (sx - 16, sy + t * fh - 6, 12, 28),
                             (sx + fw + 4, sy + t * fh - 6, 12, 28)]:
            b += rect(x, y, w, h, "#90be6d", "#2d6a4f", 1.2, rx=2)
    # зоны зарядки в углах
    for (x, y) in [(sx + 6, sy + 6), (sx + fw - 66, sy + 6),
                   (sx + 6, sy + fh - 26), (sx + fw - 66, sy + fh - 26)]:
        b += rect(x, y, 60, 20, "#dcd6f7", "#5a4fcf", 1, rx=3)
        b += txt(x + 30, y + 14, "зарядка", 10, color="#3a2fb0")
    # подписи
    b += txt(sx + fw / 2, sy + fh + 44, "60,0 м", 13, bold=True)
    b += line(sx, sy + fh + 30, sx + fw, sy + fh + 30, "#111", 1)
    b += txt(sx - 60, sy + fh / 2, "46,2 м", 13, bold=True, rot=-90)
    b += line(sx - 44, sy, sx - 44, sy + fh, "#111", 1)
    lx, ly = sx + fw + 40, sy + 30
    for dy, (c, s) in enumerate([("#8ecae6", "порты направлений — 400 шт (20×20)"),
                                 ("#ffb703", "резервные порты — 16 шт"),
                                 ("#e63946", "порты «reject» (нечитаемые) — 2 шт"),
                                 ("#90be6d", "индукция (DWS + посадка) — 20 шт"),
                                 ("#dcd6f7", "зарядные доки — 24 шт")]):
        b += rect(lx, ly + dy * 26, 14, 11, c, "#456", 0.8)
        b += txt(lx + 22, ly + dy * 26 + 10, s, 11, anchor="start")
    b += txt(lx, ly + 5 * 26 + 14, "Сетка QR-навигации: шаг 0,6 м", 11,
             anchor="start", color="#555")
    b += txt(lx, ly + 5 * 26 + 32, "Роботов на ярусе: 460", 11,
             anchor="start", color="#555")
    b += txt(lx, ly + 5 * 26 + 50, "Проездов между портами: 2,4×1,8 м", 11,
             anchor="start", color="#555")
    save("layout_tier.svg", W, H, b,
         "Схема 1. План роботизированного яруса (одинаков для ярусов 1–3)")


# =========================================================== 2. разрез
def scheme_section():
    W, H = 980, 640
    b = DEFS
    gx, gy = 90, 560                     # уровень пола
    k = 36                               # px на метр по высоте
    bw = 720                             # ширина корпуса на схеме
    b += line(40, gy, 940, gy, "#111", 2.5)
    b += txt(60, gy + 18, "отм. 0,0 — зона КТЯ", 11, anchor="start")
    tiers = [(3.6, "#8ecae6"), (6.8, "#79b8d8"), (10.0, "#5fa8cc")]
    for i, (z, c) in enumerate(tiers):
        y = gy - z * k
        b += rect(gx, y - 10, bw, 10, c, "#245", 1.2)
        b += txt(gx - 10, y - 12, f"ярус {i+1} · отм. +{z:.1f}".replace(".", ","),
                 11, anchor="end")
        # роботы на ярусе
        for rx in range(6):
            b += rect(gx + 60 + rx * 110, y - 22, 26, 11, "#ffb703", "#845", 1)
    # шахты (3 шт на разрезе)
    for j, px in enumerate([gx + 150, gx + 360, gx + 570]):
        for z, _ in tiers:
            y = gy - z * k
            b += line(px, y, px, gy - 34, "#e63946", 3)
        b += rect(px - 16, gy - 34, 32, 22, "#f4a261", "#8a4f1d", 1.2)
        b += txt(px, gy - 40, "КТЯ", 10)
    b += txt(gx + 360, gy - 5.2 * k,
             "гравитационные шахты со спиральными вставками-замедлителями",
             11, color="#a31621")
    # наклонная лента подъёма
    b += line(60, gy, gx + 40, gy - 10.0 * k - 10, "#2d6a4f", 5)
    b += txt(46, gy - 5 * k, "наклонные ленты подачи на ярусы (12 шт)", 11,
             color="#2d6a4f", rot=-63)
    # отводящая лента внизу
    b += rect(gx + 40, gy - 12, 640, 8, "#adb5bd", "#495057", 1)
    b += arrow(gx + 620, gy - 8, gx + 700, gy - 8, "#495057", 2)
    b += txt(gx + 700, gy + 14, "отводящие ленты (20 шт) → отгрузка", 11,
             anchor="end")
    # габарит здания
    b += line(gx + bw + 60, gy, gx + bw + 60, gy - 12.6 * k, "#111", 1)
    b += txt(gx + bw + 74, gy - 6.3 * k, "12,6 м", 12, bold=True, rot=-90)
    b += txt(490, 615, "Пятно застройки: 62×59,5 м ≈ 3 690 м² "
             "(в 5,4 раза меньше лимита 20 000 м²)", 12, bold=True)
    save("section.svg", W, H, b, "Схема 2. Поперечный разрез: 3 яруса, шахты, зона КТЯ")


# =========================================================== 3. робот
def scheme_robot():
    W, H = 980, 560
    b = DEFS
    # вид сбоку (слева)
    ox, oy = 130, 420
    k = 0.55                             # px на мм
    bw, bh = 720 * k, 250 * k
    b += rect(ox, oy - bh, bw, bh, "#dee2e6", "#343a40", 2, rx=8)
    for wx in (ox + 60 * k, ox + bw - 60 * k):
        b += f'<circle cx="{wx}" cy="{oy}" r="{55*k}" fill="#495057" stroke="#212529" stroke-width="2"/>\n'
    # тилт-трей наклонён
    b += (f'<g transform="rotate(-18 {ox+bw/2} {oy-bh})">'
          + rect(ox + 60 * k, oy - bh - 60 * k, 500 * k, 55 * k,
                 "#ffb703", "#845", 2, rx=4) + '</g>\n')
    b += rect(ox + 300 * k, oy - bh - 10, 120 * k, 10, "#845", "#845", 1)
    b += txt(ox + bw / 2, oy - bh - 78, "лоток 500×430 мм, наклон ±45°, 0,9 с", 11)
    b += txt(ox + bw / 2, oy + 42, "АМР-Т5: 720×540×330 мм · до 5 кг · 3,0 м/с",
             12, bold=True)
    b += txt(ox + bw / 2, oy + 62, "LiFePO4 307 Вт·ч · 85 Вт ход · зарядка 15 мин",
             11, color="#555")
    # габаритные линии
    b += line(ox, oy + 14, ox + bw, oy + 14, "#111", 1)
    b += txt(ox + bw / 2, oy + 27, "720 мм", 10)
    b += line(ox - 14, oy, ox - 14, oy - bh, "#111", 1)
    b += txt(ox - 26, oy - bh / 2, "330 мм", 10, rot=-90)
    # компоненты (справа) — выноски
    cx = 600
    items = [
        ("камера QR-навигации (низ) + IMU", 470),
        ("контроллер + Wi-Fi 6 (802.11ax) 5 ГГц", 440),
        ("датчики препятствий: 4× ToF + бампер", 410),
        ("мотор-колёса 2×150 Вт, дифф. привод", 380),
        ("контакты автозарядки (сзади)", 350),
        ("тилт-механизм: сервопривод 60 Вт", 320),
    ]
    b += txt(cx + 160, 285, "Состав узлов", 13, bold=True)
    for s, y in items:
        b += f'<circle cx="{cx}" cy="{y}" r="3" fill="#c00"/>\n'
        b += txt(cx + 12, y + 4, s, 11, anchor="start")
    # цикл робота
    b += txt(cx + 160, 130, "Рабочий цикл (среднее, модель)", 13, bold=True)
    for i, s in enumerate(["посадка товара — 1,8 с",
                           "гружёный ход — 46,6 м",
                           "сброс в порт — 2,5 с (4,5 с хрупкие)",
                           "порожний ход к ближайшей станции — 18,5 м",
                           "итого цикл ≈ 42,5 с → 84,7 сорт/ч"]):
        b += txt(cx, 152 + i * 20, "• " + s, 11, anchor="start")
    save("robot.svg", W, H, b, "Схема 3. Сортировочный робот АМР-Т5 с наклонным лотком")


# =========================================================== 4. КТЯ-станция
def scheme_box_station():
    W, H = 980, 560
    b = DEFS
    # шахта сверху
    b += rect(430, 50, 60, 150, "#f4a261", "#8a4f1d", 2)
    b += txt(460, 40, "шахта (сливает 3 яруса)", 11)
    b += arrow(460, 205, 460, 250, "#c00", 2)
    # активный короб
    b += rect(400, 250, 120, 100, "#deb887", "#6b4f1d", 2)
    b += txt(460, 305, "КТЯ", 13, bold=True)
    b += txt(460, 322, "активный", 10)
    # датчики
    b += line(380, 250, 380, 350, "#5a4fcf", 2)
    b += txt(368, 300, "лазерный датчик уровня", 10, rot=-90, color="#3a2fb0")
    b += rect(398, 352, 124, 8, "#adb5bd", "#495057", 1)
    b += txt(560, 360, "тензовесы (контроль веса)", 10, anchor="start")
    # уплотнитель
    b += rect(300, 240, 70, 26, "#c9ada7", "#6d4c41", 1.5, rx=4)
    b += txt(335, 257, "вибро", 10)
    b += txt(335, 232, "уплотнение 2 Гц", 10)
    # резервный короб
    b += rect(560, 260, 110, 90, "#e9ecef", "#868e96", 2)
    b += txt(615, 300, "КТЯ", 12)
    b += txt(615, 316, "резервный", 10)
    b += arrow(556, 305, 526, 305, "#2d6a4f", 2)
    b += txt(600, 250, "сдвиг 8 с (тандем)", 10, color="#2d6a4f")
    # толкатель и лента
    b += rect(310, 380, 80, 30, "#5a4fcf", "#3a2fb0", 1.5, rx=4)
    b += txt(350, 400, "толкатель", 10, color="#fff")
    b += arrow(394, 395, 434, 395, "#3a2fb0", 2)
    b += rect(280, 430, 420, 24, "#adb5bd", "#495057", 1.5)
    b += arrow(600, 442, 690, 442, "#212529", 2.5)
    b += txt(490, 470, "отводящая лента (такт толкателя 4 с; 1 лента на 20 станций)", 11)
    # подача пустых
    b += rect(700, 380, 150, 40, "#90be6d", "#2d6a4f", 1.5, rx=4)
    b += txt(775, 405, "формовщик коробов", 10)
    b += arrow(700, 400, 676, 330, "#2d6a4f", 2)
    b += txt(760, 360, "подача пустых КТЯ", 10, color="#2d6a4f")
    # логика закрытия
    b += txt(150, 120, "Критерии закрытия короба (ЛЮБОЙ):", 12, bold=True,
             anchor="start")
    for i, s in enumerate(["объём ≥ 80% (лазерный датчик)",
                           "вес ≥ 18 кг (тензовесы)",
                           "таймаут 20 мин (редкое направление)",
                           "команда WCS (смена волны)"]):
        b += txt(160, 145 + i * 20, "• " + s, 11, anchor="start")
    b += txt(150, 250, "Факт (модель): заполнение 83,4%,", 11, anchor="start",
             color="#2d6a4f")
    b += txt(150, 268, "24,8 товара/короб, 4 034 короба/ч", 11, anchor="start",
             color="#2d6a4f")
    save("box_station.svg", W, H, b,
         "Схема 4. КТЯ-станция: тандемная смена короба без остановки потока")


# =========================================================== 5. управление
def scheme_control():
    W, H = 980, 620
    b = DEFS

    def box(x, y, w, h, c, t1, t2="", tc="#111"):
        s = rect(x, y, w, h, c, "#345", 1.6, rx=8)
        s += txt(x + w / 2, y + 24, t1, 13, bold=True, color=tc)
        if t2:
            s += txt(x + w / 2, y + 44, t2, 10, color=tc)
        return s

    b += box(330, 50, 320, 60, "#e9ecef", "WMS заказчика (внешняя)",
             "REST API: товар → направление; события коробов")
    b += box(330, 150, 320, 60, "#8ecae6", "WCS — управление сортировкой",
             "маршруты, резервные порты, волны, KPI")
    b += box(80, 270, 250, 60, "#90be6d", "FMS — диспетчер флота",
             "MAPF-планирование, светофоры, зарядка")
    b += box(365, 270, 250, 60, "#ffb703", "Контроллеры узлов (ПЛК)",
             "индукция, шахты, толкатели, ленты")
    b += box(650, 270, 250, 60, "#c9ada7", "SCADA + безопасность",
             "СКУД ярусов, аварийные цепи, LOTO")
    b += box(80, 400, 250, 54, "#dcd6f7", "1 380 роботов",
             "Wi-Fi 6, телеметрия 10 Гц")
    b += box(365, 400, 250, 54, "#dcd6f7", "120 станций/лент/шахт",
             "PROFINET / OPC UA")
    b += box(650, 400, 250, 54, "#dcd6f7", "Датчики и СКУД",
             "двери, лидары зон, E-stop")
    b += arrow(490, 110, 490, 148, "#345", 2)
    b += txt(505, 133, "GET /item/{barcode} · POST /box/closed", 10, anchor="start")
    for x1, y1, x2, y2 in [(430, 210, 220, 268), (490, 210, 490, 268),
                           (550, 210, 760, 268), (205, 330, 205, 398),
                           (490, 330, 490, 398), (775, 330, 775, 398)]:
        b += arrow(x1, y1, x2, y2, "#345", 1.6)
    b += txt(490, 500, "Резервирование: WCS/FMS — активный/пассивный кластер; "
             "потеря связи с WMS → локальный кэш направлений на 30 мин", 11)
    b += txt(490, 522, "MAPF (Multi-Agent Path Finding) — многоагентный поиск "
             "путей без столкновений; такт перепланирования 100 мс", 11,
             color="#555")
    b += txt(490, 560, "В комплекте: mock-WMS (wms/mock_wms.py) + сквозной тест "
             "интеграции (wms/demo_integration.py)", 11, color="#2d6a4f")
    save("control.svg", W, H, b,
         "Схема 5. Архитектура управления: WMS → WCS → FMS/ПЛК → оборудование")


if __name__ == "__main__":
    scheme_layout()
    scheme_section()
    scheme_robot()
    scheme_box_station()
    scheme_control()
