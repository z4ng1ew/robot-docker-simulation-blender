# -*- coding: utf-8 -*-
"""
mock_wms.py — имитация внешней WMS (Warehouse Management System).

Роль в системе: сортировщик считывает штрихкод и по сети спрашивает WMS,
куда ехать товару. Здесь — детерминированная заглушка: ответ вычисляется
из штрихкода (хеш), поэтому воспроизводим и не требует базы данных.

Только стандартная библиотека Python — никаких зависимостей.

API (JSON):
  GET  /health                        -> {"status": "ok"}
  GET  /api/v1/item/<barcode>         -> направление, вес, габариты, хрупкость
  POST /api/v1/box/closed             -> подтверждение приёма события
  GET  /api/v1/stats                  -> счётчики запросов

Запуск:  python wms/mock_wms.py --port 8008
"""

import argparse
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIRECTIONS = 400
ZIPF_S = 0.7

# кумулятивное распределение Ципфа — как в симуляции
_w = [1.0 / (k ** ZIPF_S) for k in range(1, DIRECTIONS + 1)]
_s = sum(_w)
_CUM = []
_acc = 0.0
for _x in _w:
    _acc += _x / _s
    _CUM.append(_acc)

STATS = {"item_requests": 0, "box_events": 0, "started": time.time()}


def _u01(barcode: str, salt: str) -> float:
    """Детерминированное число [0,1) из штрихкода."""
    h = hashlib.sha256((salt + barcode).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def resolve_item(barcode: str) -> dict:
    u = _u01(barcode, "dir")
    lo, hi = 0, DIRECTIONS - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if _CUM[mid] < u:
            lo = mid + 1
        else:
            hi = mid
    v = _u01(barcode, "cls")
    if v < 0.55:
        dims, wt = (180, 120, 60), 300
    elif v < 0.85:
        dims, wt = (250, 200, 120), 900
    elif v < 0.97:
        dims, wt = (350, 280, 200), 2200
    else:
        dims, wt = (400, 320, 280), 4200
    return {
        "barcode": barcode,
        "direction": lo,
        "weight_g": wt,
        "dims_mm": list(dims),
        "fragile": _u01(barcode, "frg") < 0.06,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):            # тишина в консоли
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path.startswith("/api/v1/item/"):
            STATS["item_requests"] += 1
            self._json(200, resolve_item(self.path.rsplit("/", 1)[-1]))
        elif self.path == "/api/v1/stats":
            self._json(200, dict(STATS, uptime_s=round(
                time.time() - STATS["started"], 1)))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/v1/box/closed":
            n = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(n)
            STATS["box_events"] += 1
            self._json(200, {"accepted": True})
        else:
            self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8008)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"[mock-wms] слушаю порт {a.port} "
          f"(GET /api/v1/item/<barcode>, POST /api/v1/box/closed)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
