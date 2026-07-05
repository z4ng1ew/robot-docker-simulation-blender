# -*- coding: utf-8 -*-
"""
demo_integration.py — сквозная демонстрация сетевого взаимодействия.

Что делает:
  1) поднимает mock-WMS в отдельном процессе (порт 8008);
  2) запускает короткую симуляцию (72 c модельного времени), где направление
     КАЖДОГО товара запрашивается по HTTP: GET /api/v1/item/<barcode>;
  3) отправляет событие закрытия короба: POST /api/v1/box/closed;
  4) сверяет счётчики WMS с числом товаров в симуляции.

Запуск:  python wms/demo_integration.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "sim"))

PORT = 8008
BASE = f"http://127.0.0.1:{PORT}"


def wait_health(timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=1) as r:
                if json.loads(r.read())["status"] == "ok":
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    srv = subprocess.Popen([sys.executable,
                            os.path.join(HERE, "mock_wms.py"),
                            "--port", str(PORT)])
    try:
        assert wait_health(), "mock-WMS не поднялся"
        print(f"[demo] mock-WMS доступен: {BASE}/health -> ok")

        from run import run_scenario
        from wms_client import WmsHttpClient

        s = run_scenario("S0_base", out_root=os.path.join(ROOT, "results"),
                         wms_url=BASE, sim_hours=0.02, warmup_s=10.0)
        print(f"[demo] симуляция: товаров обработано={s['done']}, "
              f"HTTP-запросов к WMS={s['wms_http_requests']}")

        cli = WmsHttpClient(BASE)
        cli.box_closed(direction=17, items=24, weight_kg=16.8)
        with urllib.request.urlopen(BASE + "/api/v1/stats", timeout=2) as r:
            stats = json.loads(r.read())
        print(f"[demo] счётчики WMS: {stats}")

        ok = (stats["item_requests"] >= s["done"]
              and stats["box_events"] >= 1)
        print("[demo] ИНТЕГРАЦИЯ:", "OK ✅" if ok else "FAIL ❌")
        sys.exit(0 if ok else 1)
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
