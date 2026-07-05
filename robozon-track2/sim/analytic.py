# -*- coding: utf-8 -*-
"""
analytic.py — независимый аналитический расчёт системы АСР-100/400 «Рой».

Назначение: (1) обосновать выбор параметров (флот, число станций, ярусов);
(2) служить эталоном для валидации цифровой модели (validation).

Использует те же константы из config.py, что и симуляция, но считает
систему формулами теории массового обслуживания и баланса потоков,
БЕЗ имитационного движка. Совпадение результатов двух независимых
методов (<5–7%) подтверждает корректность цифровой модели.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Config  # noqa: E402


def erlang_c(c: int, a: float) -> float:
    """Вероятность ожидания в M/M/c (формула Эрланга C). a = λ/μ (эрланги)."""
    if a >= c:
        return 1.0
    s = sum(a ** k / math.factorial(k) for k in range(c))
    top = a ** c / math.factorial(c) * c / (c - a)
    return top / (s + top)


def analytic(cfg: Config | None = None) -> dict:
    c = cfg or Config()
    lam = c.arrival_rate_s                       # 1/с, весь СЦ

    # --- геометрия/поле ---
    W, H = c.field_w, c.field_h
    area_tier = W * H
    footprint = (W + 8.0) * (H + 8.0)            # плита + лестницы/техзоны

    # --- средние длины плеч по РЕАЛЬНЫМ координатам компоновки ---
    # станции: по 5 на каждой из 4 сторон; порты: матрица 21×20
    stations = []
    n_side = c.inductions_per_tier // 4
    for i in range(n_side):
        t = (i + 0.5) / n_side
        stations += [(t * W, 0.0), (t * W, H), (0.0, t * H), (W, t * H)]
    mx, px, py = c.perimeter_margin, c.port_pitch_x, c.port_pitch_y
    ports = [(mx + col * px, mx + row * py)
             for col in range(c.port_cols) for row in range(c.port_rows)]

    def manh(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # гружёный ход: станция -> порт (усреднение по всем парам)
    leg_loaded = sum(manh(s, p) for s in stations for p in ports) \
        / (len(stations) * len(ports)) + 4.0
    # порожний ход: порт -> ближайшая станция (диспетчер шлёт к ближайшей)
    leg_empty = sum(min(manh(p, s) for s in stations) for p in ports) \
        / len(ports) + 4.0

    # --- цикл робота при проектной плотности (итерация до сходимости) ---
    lam_tier = lam / c.tiers
    n_rob = c.robots_per_tier
    v = c.robot_speed
    for _ in range(30):
        t_move = (leg_loaded + leg_empty) / v \
            + 2 * c.avg_turns_per_leg * c.robot_turn_time
        t_cycle = c.t_load + t_move + c.t_drop
        moving = min(n_rob, lam_tier * t_move)         # Литтл: едущих = λ·t_move
        load = moving / c.traffic_capacity
        v = c.robot_speed * max(c.min_speed_factor,
                                1.0 - c.density_slowdown * load)
    charge_overhead = 1.0 + c.charge_time_s / c.work_before_charge_s
    t_cycle_eff = t_cycle * charge_overhead
    avg_leg = (leg_loaded + leg_empty) / 2.0
    sorts_per_robot_h = 3600.0 / t_cycle_eff
    fleet_needed_tier = lam_tier * t_cycle_eff
    fleet_util = fleet_needed_tier / n_rob
    capacity_tier_h = n_rob * sorts_per_robot_h
    capacity_sys_h = capacity_tier_h * c.tiers

    # --- индукция: M/M/c на ярус ---
    mu = 1.0 / c.induction_service_mean
    n_st = c.inductions_per_tier
    a = lam_tier / mu
    util_ind = a / n_st
    pw = erlang_c(n_st, a)
    wq = pw / (n_st * mu - lam_tier) if n_st * mu > lam_tier else float("inf")

    # --- порты: пиковое направление (Ципф) и потребность в резервах ---
    zw = [1.0 / (k ** c.zipf_s) for k in range(1, c.directions + 1)]
    zs = sum(zw)
    top_share = zw[0] / zs
    top_rate_s = lam * top_share
    port_cap_s = 1.0 / c.port_drop_occupancy          # сбросов/с на порт
    base_ports = c.tiers                               # порт на каждом ярусе
    top_util_base = top_rate_s / (port_cap_s * base_ports)
    # сколько направлений требуют резервный порт (нагрузка > 80% базовых)
    need_reserve = sum(1 for wk in zw
                       if lam * wk / zs > 0.8 * port_cap_s * base_ports)
    # резервов нужно (по слотам): добить каждое такое направление до <=80%
    extra_slots = 0
    for wk in zw:
        r = lam * wk / zs / (0.8 * port_cap_s)
        if r > base_ports:
            extra_slots += math.ceil(r - base_ports)
    top_port_util = top_rate_s / (port_cap_s * (base_ports
                                  + (math.ceil(extra_slots / max(1, need_reserve))
                                     * c.tiers if need_reserve else 0)))

    # --- КТЯ-логистика ---
    # короб закрывается при ПЕРЕСЕЧЕНИИ порога -> средний перелёт ~0.5 товара;
    # параллельное ограничение по весу (18 кг)
    items_by_vol = c.box_volume_l * c.box_fill_target / c.avg_item_volume_l + 0.5
    items_by_wt = c.box_weight_limit / c.avg_item_weight_kg
    items_per_box = min(items_by_vol, items_by_wt)
    boxes_h = c.arrival_rate_h / items_per_box
    lane_cap_h = 3600.0 / c.takeaway_time_per_box * c.takeaway_lanes
    lane_util = boxes_h / lane_cap_h
    erectors = math.ceil(boxes_h / 60.0 / 15.0)        # формовщик 15 кор/мин

    # --- энергетика (средняя за час при номинале) ---
    robots_total = n_rob * c.tiers
    move_share = fleet_util                            # доля времени в цикле
    p_robots_kw = robots_total * (move_share * c.p_move_w
                                  + (1 - move_share) * c.p_idle_w) / 1000.0
    p_robots_kw /= c.charge_efficiency
    p_fixed_kw = (c.inductions_per_tier * c.tiers * c.p_induction_kw
                  + c.lifts * c.p_lift_kw + c.p_conveyors_kw
                  + c.p_boxline_kw + c.p_it_light_kw)
    p_total_kw = p_robots_kw + p_fixed_kw
    wh_per_item = 1000.0 * p_total_kw / c.arrival_rate_h

    return dict(
        field_w_m=round(W, 1), field_h_m=round(H, 1),
        area_tier_m2=round(area_tier, 0),
        footprint_m2=round(footprint, 0),
        avg_leg_m=round(avg_leg, 1),
        leg_loaded_m=round(leg_loaded, 1),
        leg_empty_m=round(leg_empty, 1),
        v_eff_ms=round(v, 2),
        t_cycle_s=round(t_cycle_eff, 1),
        sorts_per_robot_h=round(sorts_per_robot_h, 1),
        fleet_per_tier=n_rob,
        fleet_needed_per_tier=round(fleet_needed_tier, 0),
        fleet_util=round(fleet_util, 3),
        capacity_tier_h=round(capacity_tier_h, 0),
        capacity_system_h=round(capacity_sys_h, 0),
        induction_util=round(util_ind, 3),
        induction_wait_s=round(wq, 2),
        top_direction_share_pct=round(100 * top_share, 2),
        top_port_util_base=round(top_util_base, 3),
        top_port_util_with_reserve=round(top_port_util, 3),
        directions_needing_reserve=need_reserve,
        reserve_slots_needed=extra_slots,
        items_per_box=round(items_per_box, 1),
        boxes_per_h=round(boxes_h, 0),
        takeaway_util=round(lane_util, 3),
        case_erectors=erectors,
        p_total_kw=round(p_total_kw, 0),
        wh_per_item=round(wh_per_item, 2),
    )


def compare_with_sim(sim_summary: dict, an: dict) -> list[dict]:
    """Таблица валидации: аналитика vs симуляция."""
    rows = []

    def add(name, a_val, s_val, unit=""):
        dev = abs(a_val - s_val) / a_val * 100 if a_val else 0.0
        rows.append(dict(metric=name, analytic=round(a_val, 2),
                         sim=round(s_val, 2), unit=unit,
                         deviation_pct=round(dev, 1)))

    thr_cap = min(an["capacity_system_h"],
                  Config().arrival_rate_h)  # система недогружена -> λ
    add("Производительность", thr_cap, sim_summary["throughput_steady_h"], "шт/ч")
    add("Утилизация роботов", an["fleet_util"], sim_summary["robot_util"])
    add("Утилизация индукции", an["induction_util"], sim_summary["induct_util"])
    add("Коробов в час", an["boxes_per_h"],
        sim_summary["boxes_done"] * 1.0 / sim_summary["scenario_hours"], "КТЯ/ч")
    add("Энергия на товар", an["wh_per_item"],
        sim_summary["energy_wh_per_item"], "Вт·ч")
    return rows


if __name__ == "__main__":
    an = analytic()
    print(json.dumps(an, ensure_ascii=False, indent=2))
    os.makedirs("results", exist_ok=True)
    with open("results/analytic.json", "w", encoding="utf-8") as f:
        json.dump(an, f, ensure_ascii=False, indent=2)
