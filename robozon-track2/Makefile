.PHONY: run verify fast wms demo dashboard schemes clean

run:            ## базовый сценарий (8 ч модельного времени, ~40 с)
	python3 sim/run.py S0_base

verify:         ## все 8 сценариев + валидация + графики (~3 мин)
	python3 sim/run_all.py

fast:           ## быстрая проверка всех сценариев (~1 мин)
	python3 sim/run_all.py --fast

wms:            ## поднять mock-WMS на :8008
	python3 wms/mock_wms.py --port 8008

demo:           ## сквозной тест сетевой интеграции с WMS
	python3 wms/demo_integration.py

dashboard:      ## интерактивный дашборд результатов (нужен streamlit)
	streamlit run app.py

schemes:        ## перегенерировать SVG-схемы
	python3 docs/make_schemes.py

clean:
	rm -rf results/*/ results/plots __pycache__ sim/__pycache__
