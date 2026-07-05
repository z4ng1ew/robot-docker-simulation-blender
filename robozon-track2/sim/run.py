# -*- coding: utf-8 -*-
"""
run.py — запуск одного сценария.

Примеры:
    python sim/run.py                      # базовый сценарий S0_base
    python sim/run.py S4_tier_down
    python sim/run.py S0_base --hours 8 --seed 7
"""

import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import make_config, SCENARIOS          # noqa: E402
from model import World                             # noqa: E402


def run_scenario(name: str, out_root: str = "results", wms_url: str = None,
                 **overrides):
    cfg = make_config(name, **overrides)
    wms = None
    if wms_url:
        from wms_client import WmsHttpClient
        wms = WmsHttpClient(wms_url)
    t_wall = time.time()
    world = World(cfg, wms=wms)
    summary = world.run()
    summary["scenario"] = name
    summary["wall_s"] = round(time.time() - t_wall, 1)
    if wms:
        summary["wms_http_requests"] = wms.requests

    out = os.path.join(out_root, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    if world.series:
        with open(os.path.join(out, "timeseries.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(world.series[0].keys()))
            w.writeheader()
            w.writerows(world.series)
    with open(os.path.join(out, "latency_s.csv"), "w", encoding="utf-8") as f:
        f.write("latency_s\n")
        step = max(1, len(world.latencies) // 20000)   # прореживание для файла
        for v in world.latencies[::step]:
            f.write(f"{v:.1f}\n")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="?", default="S0_base",
                    choices=sorted(SCENARIOS.keys()))
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="results")
    ap.add_argument("--wms-url", default=None,
                    help="адрес mock-WMS (например http://localhost:8008); "
                         "включает разрешение направлений по сети")
    a = ap.parse_args()

    ov = {}
    if a.hours:
        ov["sim_hours"] = a.hours
    if a.seed is not None:
        ov["seed"] = a.seed

    s = run_scenario(a.scenario, a.out, wms_url=a.wms_url, **ov)
    print(json.dumps(s, ensure_ascii=False, indent=2))
