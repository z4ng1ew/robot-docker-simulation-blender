# -*- coding: utf-8 -*-
"""
config.py — единый источник инженерных параметров системы АСР-100/400 «Рой».

Все расчёты (analytic.py) и симуляция (model.py) берут числа ОТСЮДА,
поэтому проектная документация, расчёты и цифровая модель согласованы.
"""

from dataclasses import dataclass, field


@dataclass
class Config:
    # ------------------------------------------------ поток
    arrival_rate_h: float = 100_000.0        # товаров в час на входе (номинал)
    directions: int = 400                    # исходящих направлений
    zipf_s: float = 0.7                      # перекос спроса по направлениям (Ципф)

    # классы товаров: доля, объём (л), масса (кг), доля хрупких внутри класса
    item_classes: tuple = (
        # (имя, доля, объём_л, масса_кг)
        ("S",  0.55, 0.30, 0.15),
        ("M",  0.30, 2.50, 0.80),
        ("L",  0.12, 9.00, 2.20),
        ("XL", 0.03, 28.0, 4.50),
    )
    fragile_share: float = 0.06              # доля хрупких товаров (мягкий сброс)

    # ------------------------------------------------ геометрия яруса
    tiers: int = 3                           # роботизированных ярусов
    port_cols: int = 21                      # колонн портов (20 осн. + резерв/реджект)
    port_rows: int = 20                      # рядов портов
    port_pitch_x: float = 2.4                # шаг портов по X, м
    port_pitch_y: float = 1.8                # шаг портов по Y, м
    perimeter_margin: float = 6.0            # периметральная зона (индукция, магистраль), м
    cell: float = 0.9                        # клетка сетки движения, м

    main_ports_per_tier: int = 400
    reserve_ports_per_tier: int = 16
    reject_ports_per_tier: int = 2

    # ------------------------------------------------ роботы (АМР-Т5)
    robots_per_tier: int = 460
    robot_speed: float = 3.0                 # крейсерская скорость, м/с
    robot_turn_time: float = 1.2             # поворот на 90°, с
    avg_turns_per_leg: float = 2.0           # среднее число поворотов на плечо
    t_load: float = 3.0                      # передача товара на лоток, с
    t_drop: float = 2.5                      # позиционирование + наклон лотка, с
    t_drop_fragile: float = 4.5              # мягкий сброс хрупкого, с
    density_slowdown: float = 0.60           # коэффициент замедления от плотности потока
    min_speed_factor: float = 0.30           # нижний предел скорости при заторе
    lane_capacity_share: float = 0.25        # доля свободных клеток = ёмкость трафика

    # энергетика робота
    p_move_w: float = 85.0                   # средняя мощность в движении, Вт
    p_idle_w: float = 15.0                   # мощность в ожидании, Вт
    battery_wh: float = 307.0                # LiFePO4 25,6 В × 12 А·ч
    work_before_charge_s: float = 3.2 * 3600 # наработка до подзарядки
    charge_time_s: float = 900.0             # подзарядка «подхватом», 15 мин
    charge_efficiency: float = 0.88

    # ------------------------------------------------ индукция (автозагрузка)
    inductions_per_tier: int = 20
    induction_service_mean: float = 1.80     # такт станции, с (DWS + передача)
    induction_service_sd: float = 0.30
    induction_buffer: int = 12               # буфер накопителя перед станцией, шт
    no_read_rate: float = 0.003              # нечитаемый штрихкод -> реджект-порт
    misplace_rate: float = 0.0005            # ошибка сброса не в тот порт
    weight_check_catch: float = 0.70         # весовой контроль КТЯ ловит долю ошибок
    damage_rate_normal: float = 0.0003       # повреждения при обычном сбросе
    damage_rate_fragile_soft: float = 0.0003 # хрупкие при мягком сбросе

    # ------------------------------------------------ порты и шахты
    port_drop_occupancy: float = 2.5         # занятость порта на один сброс, с
    port_queue_redirect: int = 4             # очередь у порта, после которой ищем резерв
    chute_delay: float = 3.0                 # транзит по желобу вниз, с

    # ------------------------------------------------ КТЯ-станции (низ)
    box_volume_l: float = 83.7               # полезный объём КТЯ 600×400×400, л
    box_fill_target: float = 0.80            # порог свапа по объёму
    box_weight_limit: float = 18.0           # порог свапа по массе, кг
    box_timeout_s: float = 1200.0            # закрытие частично заполненного, с
    box_swap_time: float = 8.0               # выставление нового резерва, с
    takeaway_lanes: int = 20                 # отводящих лент полных КТЯ
    takeaway_time_per_box: float = 4.0   # такт толкателя на ленту, с
    station_block_queue: int = 4             # очередь на ленту -> блокировка станции

    # ------------------------------------------------ смена/энергия оборудования
    p_induction_kw: float = 3.0
    p_lift_kw: float = 7.5
    lifts: int = 12
    p_conveyors_kw: float = 120.0
    p_boxline_kw: float = 40.0
    p_it_light_kw: float = 60.0

    # ------------------------------------------------ симуляция
    sim_hours: float = 4.0
    warmup_s: float = 900.0
    seed: int = 21
    sample_period_s: float = 60.0

    # ------------------------------------------------ сценарные переключатели
    peak_factor: float = 1.0                 # множитель входного потока
    peak_from_s: float = 0.0
    peak_to_s: float = 0.0
    robot_fail_share: float = 0.0            # доля роботов, выбывших в t_fail
    ports_fail: int = 0                      # закрытых основных портов в t_fail
    tier_down: int = -1                      # номер яруса, отключаемого в t_fail
    tier_down_duration: float = 1800.0
    inductions_fail: int = 0                 # выключенных индукций в t_fail
    t_fail_s: float = 3600.0

    # производные величины -----------------------------------------------
    @property
    def arrival_rate_s(self) -> float:
        return self.arrival_rate_h / 3600.0

    @property
    def field_w(self) -> float:
        return (self.port_cols - 1) * self.port_pitch_x + 2 * self.perimeter_margin

    @property
    def field_h(self) -> float:
        return (self.port_rows - 1) * self.port_pitch_y + 2 * self.perimeter_margin

    @property
    def free_cells(self) -> int:
        total = int(self.field_w / self.cell) * int(self.field_h / self.cell)
        ports = self.port_cols * self.port_rows
        return total - ports

    @property
    def traffic_capacity(self) -> float:
        """Сколько роботов может одновременно двигаться без коллапса трафика."""
        return self.free_cells * self.lane_capacity_share

    @property
    def avg_item_volume_l(self) -> float:
        return sum(sh * v for _, sh, v, _ in self.item_classes)

    @property
    def avg_item_weight_kg(self) -> float:
        return sum(sh * w for _, sh, _, w in self.item_classes)


SCENARIOS = {
    "S0_base":      dict(),
    "S1_peak15":    dict(peak_factor=1.15, peak_from_s=3600.0, peak_to_s=7200.0),
    "S2_robots5":   dict(robot_fail_share=0.05),
    "S3_ports10":   dict(ports_fail=10),
    "S4_tier_down": dict(tier_down=1, tier_down_duration=1800.0),
    "S5_induct6":   dict(inductions_fail=6),
    "S6_skew":      dict(zipf_s=1.1),
    "S7_stress120": dict(arrival_rate_h=120_000.0, sim_hours=2.0),
}


def make_config(scenario: str = "S0_base", **overrides) -> Config:
    cfg = Config()
    for k, v in SCENARIOS.get(scenario, {}).items():
        setattr(cfg, k, v)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
