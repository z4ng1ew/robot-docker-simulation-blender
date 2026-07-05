# -*- coding: utf-8 -*-
"""
app.py — интерактивный дашборд результатов (Streamlit).

Запуск:  streamlit run app.py     (сначала: python sim/run_all.py)
Docker:  docker compose up dashboard  ->  http://localhost:8501
"""

import json
import os

import pandas as pd
import streamlit as st

RES = "results"

st.set_page_config(page_title="АСР-100/400 «Рой»", layout="wide")
st.title("АСР-100/400 «Рой» — результаты верификации")
st.caption("Ozon Tech «Робозон», задача 2 · команда «Ящик Шрёдингера»")

path = os.path.join(RES, "summary_all.json")
if not os.path.exists(path):
    st.warning("Нет результатов. Выполните:  `python sim/run_all.py`")
    st.stop()

with open(path, encoding="utf-8") as f:
    allsum = json.load(f)

scen = st.sidebar.selectbox("Сценарий", list(allsum.keys()))
s = allsum[scen]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Производительность, шт/ч", f"{s['throughput_steady_h']:,.0f}"
          .replace(",", " "))
c2.metric("Задержка p95, с", s["latency_p95_s"])
c3.metric("Точность сортировки, %", s["sort_accuracy_pct"])
c4.metric("Вт·ч на товар", s["energy_wh_per_item"])

c5, c6, c7, c8 = st.columns(4)
c5.metric("Утилизация роботов", s["robot_util"])
c6.metric("Заполнение КТЯ", s["box_fill_avg"])
c7.metric("Коробов закрыто", f"{s['boxes_done']:,}".replace(",", " "))
c8.metric("Резервных портов задействовано", s["reserve_assigned"])

ts_path = os.path.join(RES, scen, "timeseries.csv")
if os.path.exists(ts_path):
    ts = pd.read_csv(ts_path)
    ts["t_ч"] = ts["t"] / 3600
    left, right = st.columns(2)
    with left:
        st.subheader("Производительность, шт/ч")
        st.line_chart(ts.set_index("t_ч")["thr_h"])
        st.subheader("Роботы: занято / едут")
        st.line_chart(ts.set_index("t_ч")[["robots_busy", "moving"]])
    with right:
        st.subheader("Очередь перед индукцией, шт")
        st.line_chart(ts.set_index("t_ч")["q_induct"])
        st.subheader("Товаров внутри системы")
        st.line_chart(ts.set_index("t_ч")["in_system"])

lat_path = os.path.join(RES, scen, "latency_s.csv")
if os.path.exists(lat_path):
    lat = pd.read_csv(lat_path)["latency_s"]
    st.subheader("Гистограмма времени «приёмка → короб», с")
    st.bar_chart(pd.cut(lat, bins=40).value_counts().sort_index()
                 .rename(index=lambda i: round(i.mid)))

with st.expander("Полный summary.json"):
    st.json(s)

val = os.path.join(RES, "validation.md")
if os.path.exists(val):
    st.divider()
    st.markdown(open(val, encoding="utf-8").read())
