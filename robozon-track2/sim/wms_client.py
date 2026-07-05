# -*- coding: utf-8 -*-
"""
wms_client.py — интеграционный слой «сортировщик <-> WMS».

Два режима:
  inline — распределение направлений считается внутри симуляции (быстро,
           используется в длинных прогонах);
  http   — на каждый товар генерируется штрихкод и выполняется реальный
           сетевой запрос GET /api/v1/item/<barcode> к mock-WMS
           (демонстрация требуемого сетевого взаимодействия).

Оба режима дают одно и то же распределение (Ципф s=0.7), поэтому
короткий http-прогон статистически сопоставим с inline.
"""

import json
import urllib.request


class WmsHttpClient:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.requests = 0
        self._seq = 0

    def next_barcode(self) -> str:
        self._seq += 1
        return f"OZN{self._seq:010d}"

    def resolve(self, barcode: str) -> dict:
        url = f"{self.base}/api/v1/item/{barcode}"
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            self.requests += 1
            return json.loads(r.read().decode())

    def box_closed(self, direction: int, items: int, weight_kg: float):
        data = json.dumps({"direction": direction, "items": items,
                           "weight_kg": round(weight_kg, 2)}).encode()
        req = urllib.request.Request(
            f"{self.base}/api/v1/box/closed", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout):
            pass
