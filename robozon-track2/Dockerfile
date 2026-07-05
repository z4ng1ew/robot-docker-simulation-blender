FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sim/ sim/
COPY wms/ wms/
COPY docs/ docs/
COPY app.py .

# полный прогон верификации при сборке НЕ выполняем — по запросу:
#   docker compose run sim make verify
CMD ["python", "sim/run.py", "S0_base"]
