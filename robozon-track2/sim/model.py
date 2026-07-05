# -*- coding: utf-8 -*-
"""
model.py — имитационная модель (мезоуровень) системы АСР-100/400 «Рой».

Моделируемая цепочка (полный жизненный цикл товара):
  прибытие -> выбор яруса -> очередь индукции -> станция (DWS + загрузка на робота)
  -> поездка робота -> порт (сброс) -> шахта -> КТЯ-станция (заполнение, контроль,
  смена короба, отвод на ленту) -> закрытый короб.

Трафик роботов — макромодель плотности («фундаментальная диаграмма» транспортного
потока): эффективная скорость падает с ростом числа одновременно движущихся
роботов на ярусе. Порты, ленты, станции — ресурсы с очередями FIFO.

Ключевые механики устойчивости, воспроизводимые моделью:
  * динамическое назначение резервных портов «горячим» направлениям
    (у резервного порта — собственная КТЯ-станция внизу);
  * тандемная смена КТЯ (активный/резервный короб) без остановки потока;
  * каскадная блокировка: затор на отводящей ленте -> блок станции ->
    закрытие её портов -> перенаправление роботов;
  * отказы роботов / портов / индукции / целого яруса.
"""

import random
from collections import defaultdict

from engine import Environment, Slot, Buffer, BACKEND
from config import Config

REJECT = -1  # «направление» нечитаемых товаров (зона ручной обработки)


# ---------------------------------------------------------------- сущности

class Item:
    __slots__ = ("t0", "direction", "vol", "wt", "fragile", "tier")

    def __init__(self, t0, direction, vol, wt, fragile):
        self.t0 = t0
        self.direction = direction
        self.vol = vol
        self.wt = wt
        self.fragile = fragile
        self.tier = -1


class Port:
    """Порт сброса на ярусе (люк с шахтой вниз). Привязан к КТЯ-станции."""

    __slots__ = ("slot", "x", "y", "closed", "station")

    def __init__(self, env, x, y):
        self.slot = Slot(env, 1)
        self.x = x
        self.y = y
        self.closed = False
        self.station = None


class BoxStation:
    """КТЯ-станция на отм. 0 (тандем: активный + резервный короб).

    Шахты одноимённых портов всех ярусов сливаются в одну станцию.
    """

    __slots__ = ("env", "cfg", "m", "direction", "vol", "wt", "count",
                 "first_t", "standby_ready", "blocked", "lane", "ports")

    def __init__(self, env, cfg, metrics, lane):
        self.env = env
        self.cfg = cfg
        self.m = metrics
        self.direction = None      # для резервных станций назначается на лету
        self.vol = 0.0
        self.wt = 0.0
        self.count = 0
        self.first_t = None
        self.standby_ready = True
        self.blocked = False
        self.lane = lane
        self.ports = []            # порты (по одному на ярус), падающие сюда

    # ---- приём товара из шахты ----
    def add(self, item):
        if self.count == 0:
            self.first_t = self.env.now
        self.count += 1
        self.vol += item.vol
        self.wt += item.wt
        c = self.cfg
        if (self.vol >= c.box_fill_target * c.box_volume_l
                or self.wt >= c.box_weight_limit):
            self.close_box(partial=False)

    def maybe_timeout_close(self):
        if (self.count > 0 and self.first_t is not None
                and self.env.now - self.first_t >= self.cfg.box_timeout_s):
            self.close_box(partial=True)

    # ---- закрытие короба и логистика ----
    def close_box(self, partial):
        m = self.m
        m["boxes_done"] += 1
        if partial:
            m["boxes_partial"] += 1
        m["box_fill_sum"] += self.vol / self.cfg.box_volume_l
        m["items_boxed"] += self.count
        self.vol = self.wt = 0.0
        self.count = 0
        self.first_t = None
        if self.standby_ready:
            self.standby_ready = False           # поток мгновенно на резерв
            self.env.process(self._restock())
        else:                                     # резерв не успел — затор
            self._set_blocked(True)
            self.env.process(self._restock(unblock=True))
        self.env.process(self._takeaway())

    def _takeaway(self):
        if self.lane.qlen >= self.cfg.station_block_queue:
            self._set_blocked(True)
            self.m["station_blocks"] += 1
            yield self.lane.acquire()
            yield self.env.timeout(self.cfg.takeaway_time_per_box)
            self.lane.release()
            if self.standby_ready:
                self._set_blocked(False)
        else:
            yield self.lane.acquire()
            yield self.env.timeout(self.cfg.takeaway_time_per_box)
            self.lane.release()

    def _restock(self, unblock=False):
        yield self.env.timeout(self.cfg.box_swap_time)
        self.standby_ready = True
        if unblock and self.lane.qlen < self.cfg.station_block_queue:
            self._set_blocked(False)

    def _set_blocked(self, flag):
        if self.blocked == flag:
            return
        self.blocked = flag
        for p in self.ports:
            p.closed = flag
        if flag:
            self.m["blocked_events"] += 1


class Tier:
    """Роботизированный ярус: матрица портов, флот, индукционные станции."""

    def __init__(self, env, cfg, rng, metrics, index):
        self.env = env
        self.cfg = cfg
        self.rng = rng
        self.m = metrics
        self.index = index
        self.active = True

        self.robots = Slot(env, cfg.robots_per_tier)
        self.moving = 0
        self.inflight = 0

        mx, py, px = cfg.perimeter_margin, cfg.port_pitch_y, cfg.port_pitch_x
        self.main_ports = {}
        for d in range(cfg.main_ports_per_tier):
            r, c = divmod(d, 20)
            self.main_ports[d] = Port(env, mx + c * px, mx + r * py)
        self.reserve_ports = [Port(env, mx + 20 * px, mx + r * py)
                              for r in range(cfg.reserve_ports_per_tier)]
        self.reject_ports = [Port(env, mx + 20 * px, mx + (17 + i) * py)
                             for i in range(cfg.reject_ports_per_tier)]

        # индукционные станции: по 5 на каждой из 4 сторон
        W, H = cfg.field_w, cfg.field_h
        self.stations_xy = []
        n_side = cfg.inductions_per_tier // 4
        for i in range(n_side):
            t = (i + 0.5) / n_side
            self.stations_xy += [(t * W, 0.0), (t * W, H),
                                 (0.0, t * H), (W, t * H)]
        self.station_enabled = [True] * cfg.inductions_per_tier
        self.induction_q = Buffer(env)

    # ---------- трафик ----------
    def v_eff(self):
        c = self.cfg
        load = self.moving / max(1.0, c.traffic_capacity)
        return c.robot_speed * max(c.min_speed_factor,
                                   1.0 - c.density_slowdown * load)

    def leg_time(self, x1, y1, x2, y2):
        dist = abs(x1 - x2) + abs(y1 - y2) + 4.0
        return (dist / self.v_eff()
                + self.cfg.avg_turns_per_leg * self.cfg.robot_turn_time)

    def nearest_station(self, x, y):
        return min(self.stations_xy,
                   key=lambda s: abs(s[0] - x) + abs(s[1] - y))


# ---------------------------------------------------------------- мир

class World:
    def __init__(self, cfg: Config, wms=None):
        self.cfg = cfg
        self.wms = wms                 # None => inline-режим (см. wms_client.py)
        self.env = Environment()
        self.rng = random.Random(cfg.seed)
        self.m = defaultdict(float)
        self.latencies = []
        self.series = []

        # распределение спроса по направлениям (Ципф)
        w = [1.0 / (k ** cfg.zipf_s) for k in range(1, cfg.directions + 1)]
        s = sum(w)
        self.dir_cum = []
        acc = 0.0
        for x in w:
            acc += x / s
            self.dir_cum.append(acc)

        self.tiers = [Tier(self.env, cfg, self.rng, self.m, i)
                      for i in range(cfg.tiers)]

        # отводящие ленты и КТЯ-станции
        self.lanes = [Slot(self.env, 1) for _ in range(cfg.takeaway_lanes)]
        self.stations = {}
        for d in range(cfg.directions):
            # балансировка лент: направления чередуются по рядам (WCS-маппинг),
            # чтобы «горячие» направления не скапливались на одной ленте
            lane = self.lanes[d % cfg.takeaway_lanes]
            st = BoxStation(self.env, cfg, self.m, lane)
            st.direction = d
            self.stations[d] = st
            for t in self.tiers:                 # шахты трёх ярусов -> станция
                p = t.main_ports[d]
                p.station = st
                st.ports.append(p)

        # резервные станции (глобальный пул), связаны с reserve_ports[r] ярусов
        self.reserve_stations = []
        for r in range(cfg.reserve_ports_per_tier):
            lane = self.lanes[(r * 7 + 3) % cfg.takeaway_lanes]
            st = BoxStation(self.env, cfg, self.m, lane)
            self.reserve_stations.append(st)
            for t in self.tiers:
                p = t.reserve_ports[r]
                p.station = st
                st.ports.append(p)
        self.next_reserve = 0
        self.extra = defaultdict(list)           # direction -> [reserve idx]

        self.classes_cum = []
        acc = 0.0
        for name, share, vol, wt in cfg.item_classes:
            acc += share
            self.classes_cum.append((acc, vol, wt))

    # ------------------------------------------------ выборки
    def sample_direction(self):
        u = self.rng.random()
        lo, hi = 0, len(self.dir_cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.dir_cum[mid] < u:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def sample_item(self):
        if self.wms is not None:            # сетевой режим: штрихкод -> WMS
            info = self.wms.resolve(self.wms.next_barcode())
            wt = info["weight_g"] / 1000.0
            vol = min((c[2] for c in self.cfg.item_classes),
                      key=lambda v: abs(v - wt * 4))     # класс по весу
            for _, _, v, w in self.cfg.item_classes:
                if abs(w - wt) < 1e-6:
                    vol = v
                    break
            return Item(self.env.now, info["direction"], vol, wt,
                        info["fragile"])
        u = self.rng.random()
        for acc, vol, wt in self.classes_cum:
            if u <= acc:
                break
        return Item(self.env.now, self.sample_direction(), vol, wt,
                    self.rng.random() < self.cfg.fragile_share)

    # ------------------------------------------------ поток на входе
    def arrivals(self):
        c, rng, env = self.cfg, self.rng, self.env
        while True:
            rate = c.arrival_rate_s
            if c.peak_to_s > 0 and c.peak_from_s <= env.now < c.peak_to_s:
                rate *= c.peak_factor
            yield env.timeout(rng.expovariate(rate))
            item = self.sample_item()
            self.m["arrived"] += 1
            tier = min((t for t in self.tiers if t.active),
                       key=lambda t: t.inflight + len(t.induction_q.items))
            item.tier = tier.index
            tier.inflight += 1
            tier.induction_q.put(item)

    # ------------------------------------------------ индукция
    def station_worker(self, tier: Tier, sid: int):
        c, env, rng = self.cfg, self.env, self.rng
        sx, sy = tier.stations_xy[sid]
        while True:
            if not tier.station_enabled[sid] or not tier.active:
                yield env.timeout(5.0)
                continue
            item = yield tier.induction_q.get()
            yield tier.robots.acquire()
            svc = max(1.0, rng.gauss(c.induction_service_mean,
                                     c.induction_service_sd))
            yield env.timeout(svc)
            self.m["induct_busy_s"] += svc
            if rng.random() < c.no_read_rate:
                item.direction = REJECT
                self.m["rejected"] += 1
            env.process(self.robot_trip(tier, item, sx, sy))

    # ------------------------------------------------ выбор порта
    def pick_port(self, tier: Tier, direction: int):
        if direction == REJECT:
            return min(tier.reject_ports, key=lambda p: p.slot.qlen)
        cands = [tier.main_ports[direction]]
        for r in self.extra.get(direction, []):
            cands.append(tier.reserve_ports[r])
        open_c = [p for p in cands if not p.closed]
        if not open_c:
            # направление полностью закрыто (блок станции/отказ шахты):
            # немедленное переназначение на резервный порт+станцию
            if self.next_reserve < self.cfg.reserve_ports_per_tier:
                r = self.next_reserve
                self.next_reserve += 1
                self.extra[direction].append(r)
                self.reserve_stations[r].direction = direction
                self.m["reserve_assigned"] += 1
                self.m["reserve_on_block"] += 1
                return tier.reserve_ports[r]
            return None
        best = min(open_c, key=lambda p: p.slot.busy + p.slot.qlen)
        if (best.slot.qlen >= self.cfg.port_queue_redirect
                and self.next_reserve < self.cfg.reserve_ports_per_tier):
            r = self.next_reserve
            self.next_reserve += 1
            self.extra[direction].append(r)
            self.reserve_stations[r].direction = direction
            self.m["reserve_assigned"] += 1
            return tier.reserve_ports[r]
        return best

    # ------------------------------------------------ поездка робота
    def robot_trip(self, tier: Tier, item: Item, sx, sy):
        c, env, rng = self.cfg, self.env, self.rng
        yield env.timeout(c.t_load)

        target_dir = item.direction
        if target_dir != REJECT and rng.random() < c.misplace_rate:
            target_dir = rng.randrange(c.directions)      # физически не туда
            self.m["misplaced"] += 1
            if rng.random() < c.weight_check_catch:
                self.m["misplace_caught"] += 1

        port = self.pick_port(tier, target_dir)
        waited = 0
        while port is None:            # направление закрыто -> кружение в буфере
            self.m["port_wait_closed"] += 1
            yield env.timeout(10.0)
            waited += 1
            port = self.pick_port(tier, target_dir if waited <= 60 else REJECT)

        t1 = tier.leg_time(sx, sy, port.x, port.y)
        tier.moving += 1
        yield env.timeout(t1)
        tier.moving -= 1
        self.m["move_s"] += t1

        yield port.slot.acquire()
        tdrop = c.t_drop_fragile if item.fragile else c.t_drop
        yield env.timeout(tdrop)
        port.slot.release()
        self.m["move_s"] += tdrop

        if rng.random() < (c.damage_rate_fragile_soft if item.fragile
                           else c.damage_rate_normal):
            self.m["damaged"] += 1

        env.process(self.chute_then_box(item, port, tier))

        bx, by = tier.nearest_station(port.x, port.y)     # порожний ход
        t2 = tier.leg_time(port.x, port.y, bx, by)
        tier.moving += 1
        yield env.timeout(t2)
        tier.moving -= 1
        self.m["move_s"] += t2

        cycle = t1 + t2 + tdrop + c.t_load
        if rng.random() < cycle / c.work_before_charge_s:  # зарядка «подхватом»
            self.m["charges"] += 1
            yield env.timeout(c.charge_time_s)
        tier.robots.release()

    # ------------------------------------------------ шахта и короб
    def chute_then_box(self, item: Item, port: Port, tier: Tier):
        yield self.env.timeout(self.cfg.chute_delay)
        tier.inflight -= 1
        self.m["done"] += 1
        st = port.station
        if st is None:                                    # реджект-порт
            self.m["reject_boxed"] += 1
            return
        st.add(item)
        if self.env.now >= self.cfg.warmup_s:
            self.latencies.append(self.env.now - item.t0)
        if st.direction != item.direction:
            self.m["missort_in_box"] += 1

    # ------------------------------------------------ сервис и отказы
    def box_timeout_patrol(self):
        while True:
            yield self.env.timeout(60.0)
            for st in self.stations.values():
                st.maybe_timeout_close()
            for st in self.reserve_stations:
                st.maybe_timeout_close()

    def sampler(self):
        c, env = self.cfg, self.env
        last_done = 0.0
        while True:
            yield env.timeout(c.sample_period_s)
            done = self.m["done"]
            row = dict(
                t=round(env.now, 0),
                thr_h=round((done - last_done) * 3600.0 / c.sample_period_s, 0),
                in_system=sum(t.inflight for t in self.tiers),
                q_induct=sum(len(t.induction_q.items) for t in self.tiers),
                robots_busy=sum(t.robots.busy for t in self.tiers),
                moving=sum(t.moving for t in self.tiers),
                boxes=int(self.m["boxes_done"]),
                blocked=sum(1 for s in self.stations.values() if s.blocked),
            )
            self.m["robot_busy_int"] += row["robots_busy"] * c.sample_period_s
            self.series.append(row)
            last_done = done

    def fault_injector(self):
        c, env, rng = self.cfg, self.env, self.rng
        if not any([c.robot_fail_share, c.ports_fail, c.tier_down >= 0,
                    c.inductions_fail]):
            return
        yield env.timeout(c.t_fail_s)
        if c.robot_fail_share:
            for t in self.tiers:
                k = int(t.robots.capacity * c.robot_fail_share)
                t.robots.set_capacity(t.robots.capacity - k)
            self.m["evt_robot_fail"] = env.now
        if c.ports_fail:
            for d in rng.sample(range(c.directions), c.ports_fail):
                self.tiers[0].main_ports[d].closed = True
            self.m["evt_ports_fail"] = env.now
        if c.inductions_fail:
            for i in range(c.inductions_fail):
                self.tiers[0].station_enabled[i] = False
            self.m["evt_induct_fail"] = env.now
        if c.tier_down >= 0:
            t = self.tiers[c.tier_down]
            t.active = False
            saved = t.robots.capacity
            t.robots.set_capacity(0)
            self.m["evt_tier_down"] = env.now
            yield env.timeout(c.tier_down_duration)
            t.active = True
            t.robots.set_capacity(saved)
            self.m["evt_tier_up"] = env.now

    # ------------------------------------------------ запуск и итоги
    def run(self):
        env, c = self.env, self.cfg
        env.process(self.arrivals())
        for t in self.tiers:
            for sid in range(c.inductions_per_tier):
                env.process(self.station_worker(t, sid))
        env.process(self.box_timeout_patrol())
        env.process(self.sampler())
        env.process(self.fault_injector())
        env.run(until=c.sim_hours * 3600.0)
        return self.summary()

    def summary(self):
        c, m = self.cfg, self.m
        T = c.sim_hours * 3600.0
        lat = sorted(self.latencies)

        def pct(p):
            return lat[min(len(lat) - 1, int(p * len(lat)))] if lat else 0.0

        steady_T = T - c.warmup_s
        thr = (len(lat) + m["reject_boxed"] * steady_T / T) * 3600.0 / steady_T

        robot_cap = sum(t.robots.capacity for t in self.tiers) or 1
        busy_int = m["robot_busy_int"]
        e_robots_kwh = ((m["move_s"] / 3600.0) * c.p_move_w
                        + max(0.0, robot_cap * T - busy_int) / 3600.0
                        * c.p_idle_w) / 1000.0 / c.charge_efficiency
        e_fixed_kwh = (c.inductions_per_tier * c.tiers * c.p_induction_kw
                       + c.lifts * c.p_lift_kw + c.p_conveyors_kw
                       + c.p_boxline_kw + c.p_it_light_kw) * c.sim_hours
        done = max(1.0, m["done"])
        undetected = m["misplaced"] - m["misplace_caught"]

        return dict(
            backend=BACKEND,
            scenario_hours=c.sim_hours,
            arrived=int(m["arrived"]),
            done=int(m["done"]),
            throughput_steady_h=round(thr, 0),
            latency_p50_s=round(pct(0.50), 1),
            latency_p95_s=round(pct(0.95), 1),
            latency_p99_s=round(pct(0.99), 1),
            in_system_end=int(sum(t.inflight for t in self.tiers)),
            q_induct_end=int(sum(len(t.induction_q.items) for t in self.tiers)),
            robot_util=round(busy_int / (robot_cap * T), 3),
            induct_util=round(m["induct_busy_s"]
                              / (c.inductions_per_tier * c.tiers * T), 3),
            boxes_done=int(m["boxes_done"]),
            boxes_partial=int(m["boxes_partial"]),
            box_fill_avg=round(m["box_fill_sum"] / max(1, m["boxes_done"]), 3),
            rejected_pct=round(100 * m["rejected"] / done, 3),
            misplaced_pct=round(100 * m["misplaced"] / done, 4),
            missort_undetected_pct=round(100 * undetected / done, 4),
            damaged_pct=round(100 * m["damaged"] / done, 4),
            sort_accuracy_pct=round(
                100 * (1 - undetected / done - m["damaged"] / done), 3),
            reserve_assigned=int(m["reserve_assigned"]),
            station_blocks=int(m["station_blocks"]),
            blocked_events=int(m["blocked_events"]),
            port_wait_closed=int(m["port_wait_closed"]),
            charges=int(m["charges"]),
            energy_kwh=round(e_robots_kwh + e_fixed_kwh, 0),
            energy_wh_per_item=round(
                1000.0 * (e_robots_kwh + e_fixed_kwh) / done, 2),
        )
