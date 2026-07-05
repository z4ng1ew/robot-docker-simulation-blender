# -*- coding: utf-8 -*-
"""
run_all.py — полный прогон верификации: все сценарии + сводка + валидация + графики.

Результат:
    results/<scenario>/summary.json, timeseries.csv, latency_s.csv
    results/summary_all.json / summary_all.md   — сводная таблица сценариев
    results/validation.md                        — аналитика vs симуляция
    results/plots/*.png                          — графики (если есть matplotlib)

Запуск:  python sim/run_all.py           (~2–4 мин)
         python sim/run_all.py --fast    (сокращённые горизонты, ~1 мин)
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SCENARIOS, make_config       # noqa: E402
from analytic import analytic, compare_with_sim  # noqa: E402
from run import run_scenario                     # noqa: E402

SCEN_TITLES = {
    "S0_base":      "Базовый режим, 100 тыс/ч, 8 ч",
    "S1_peak15":    "Пик +15% в течение 1 ч",
    "S2_robots5":   "Отказ 5% роботов на всех ярусах",
    "S3_ports10":   "Отказ 10 портов яруса 1",
    "S4_tier_down": "Полный останов яруса 2 на 30 мин",
    "S5_induct6":   "Отказ 6 индукционных станций яруса 1",
    "S6_skew":      "Сильный перекос спроса (Ципф s=1,1)",
    "S7_stress120": "Стресс: вход 120 тыс/ч (поиск предела)",
}

COLS = [
    ("throughput_steady_h", "Произв., шт/ч"),
    ("latency_p50_s", "p50, с"),
    ("latency_p95_s", "p95, с"),
    ("latency_p99_s", "p99, с"),
    ("robot_util", "Роботы, util"),
    ("induct_util", "Индукция, util"),
    ("boxes_done", "КТЯ закрыто"),
    ("box_fill_avg", "Заполнение КТЯ"),
    ("sort_accuracy_pct", "Точность, %"),
    ("reserve_assigned", "Резерв. портов"),
    ("station_blocks", "Блокировок"),
    ("energy_wh_per_item", "Вт·ч/товар"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true",
                    help="сокращённые горизонты для быстрой проверки")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)

    plan = {
        "S0_base": 8.0, "S1_peak15": 4.0, "S2_robots5": 4.0,
        "S3_ports10": 4.0, "S4_tier_down": 4.0, "S5_induct6": 4.0,
        "S6_skew": 4.0, "S7_stress120": 2.0,
    }
    if a.fast:
        plan = {k: min(v, 1.5) for k, v in plan.items()}

    all_sum = {}
    for name in SCENARIOS:
        print(f"[run_all] {name} ({SCEN_TITLES[name]}) ...", flush=True)
        s = run_scenario(name, a.out, sim_hours=plan[name])
        all_sum[name] = s
        print(f"    произв.={s['throughput_steady_h']:.0f}/ч  "
              f"p95={s['latency_p95_s']}с  точность={s['sort_accuracy_pct']}%  "
              f"[{s['wall_s']}с]")

    with open(os.path.join(a.out, "summary_all.json"), "w",
              encoding="utf-8") as f:
        json.dump(all_sum, f, ensure_ascii=False, indent=2)

    # ---------------- markdown-сводка ----------------
    lines = ["# Сводка сценариев верификации\n",
             "| Сценарий | Описание | " + " | ".join(t for _, t in COLS) + " |",
             "|" + "---|" * (len(COLS) + 2)]
    for name, s in all_sum.items():
        row = [name, SCEN_TITLES[name]] + [str(s[k]) for k, _ in COLS]
        lines.append("| " + " | ".join(row) + " |")
    with open(os.path.join(a.out, "summary_all.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # ---------------- валидация ----------------
    an = analytic(make_config("S0_base"))
    with open(os.path.join(a.out, "analytic.json"), "w",
              encoding="utf-8") as f:
        json.dump(an, f, ensure_ascii=False, indent=2)
    rows = compare_with_sim(all_sum["S0_base"], an)
    v = ["# Валидация цифровой модели",
         "",
         "Два независимых метода: аналитический расчёт (теория массового",
         "обслуживания, баланс потоков) и имитационная модель (DES).",
         "Совпадение подтверждает корректность обоих.",
         "",
         "| Метрика | Аналитика | Симуляция | Ед. | Отклонение, % |",
         "|---|---|---|---|---|"]
    for r in rows:
        v.append(f"| {r['metric']} | {r['analytic']} | {r['sim']} | "
                 f"{r['unit']} | {r['deviation_pct']} |")
    ok = all(r["deviation_pct"] <= 7.0 for r in rows)
    v.append("")
    v.append("**Вывод:** отклонения "
             + ("в пределах 7% — модель валидирована. ✅" if ok
                else "превышают порог — см. анализ в отчёте."))
    with open(os.path.join(a.out, "validation.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(v) + "\n")
    print("[run_all] валидация:", "OK" if ok else "ОТКЛОНЕНИЯ")

    # ---------------- графики ----------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[run_all] matplotlib не найден — графики пропущены")
        return

    pdir = os.path.join(a.out, "plots")
    os.makedirs(pdir, exist_ok=True)

    def load_ts(name):
        path = os.path.join(a.out, name, "timeseries.csv")
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # 1) производительность во времени: база / пик / останов яруса
    plt.figure(figsize=(10, 5))
    for name, style in [("S0_base", "-"), ("S1_peak15", "--"),
                        ("S4_tier_down", "-.")]:
        ts = load_ts(name)
        t = [float(r["t"]) / 3600 for r in ts]
        y = [float(r["thr_h"]) / 1000 for r in ts]
        plt.plot(t, y, style, label=SCEN_TITLES[name])
    plt.axhline(100, color="gray", lw=0.8, ls=":")
    plt.xlabel("Время, ч")
    plt.ylabel("Производительность, тыс. шт/ч")
    plt.title("Пропускная способность: номинал, пик +15%, останов яруса")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(pdir, "throughput.png"), dpi=140)
    plt.close()

    # 2) распределение времени прохождения товара (S0)
    with open(os.path.join(a.out, "S0_base", "latency_s.csv"),
              encoding="utf-8") as f:
        lat = [float(x) for x in f.read().split()[1:]]
    lat.sort()
    plt.figure(figsize=(10, 4.5))
    xs = lat
    ys = [i / len(lat) * 100 for i in range(len(lat))]
    plt.plot(xs, ys)
    for p, lab in [(0.5, "p50"), (0.95, "p95"), (0.99, "p99")]:
        val = lat[int(p * len(lat)) - 1]
        plt.axvline(val, ls="--", lw=0.8, color="tab:red")
        plt.text(val + 1, p * 100 - 6, f"{lab}={val:.0f}с", color="tab:red")
    plt.xlabel("Время «приёмка → короб», с")
    plt.ylabel("Доля товаров, %")
    plt.title("Время прохождения товара через систему (базовый режим)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(pdir, "latency_cdf.png"), dpi=140)
    plt.close()

    # 3) очередь индукции: пик и деградация яруса
    plt.figure(figsize=(10, 4.5))
    for name in ["S1_peak15", "S4_tier_down", "S7_stress120"]:
        ts = load_ts(name)
        t = [float(r["t"]) / 3600 for r in ts]
        q = [float(r["q_induct"]) for r in ts]
        plt.plot(t, q, label=SCEN_TITLES[name])
    plt.xlabel("Время, ч")
    plt.ylabel("Очередь перед индукцией, шт")
    plt.title("Поведение очередей в нештатных режимах")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(pdir, "queues.png"), dpi=140)
    plt.close()

    # 4) сравнение сценариев по производительности и p95
    plt.figure(figsize=(11, 5))
    names = list(all_sum.keys())
    thr = [all_sum[n]["throughput_steady_h"] / 1000 for n in names]
    ax1 = plt.gca()
    ax1.bar(range(len(names)), thr, color="tab:blue", alpha=0.75)
    ax1.set_xticks(range(len(names)))
    ax1.set_xticklabels(names, rotation=25, ha="right")
    ax1.axhline(100, color="gray", ls=":", lw=1)
    ax1.set_ylabel("Производительность, тыс. шт/ч")
    ax2 = ax1.twinx()
    p95 = [all_sum[n]["latency_p95_s"] for n in names]
    ax2.plot(range(len(names)), p95, "o-", color="tab:red")
    ax2.set_ylabel("p95 задержки, с", color="tab:red")
    plt.title("Итог по сценариям: пропускная способность и p95")
    plt.tight_layout()
    plt.savefig(os.path.join(pdir, "scenarios.png"), dpi=140)
    plt.close()

    print("[run_all] графики сохранены в", pdir)


if __name__ == "__main__":
    main()
