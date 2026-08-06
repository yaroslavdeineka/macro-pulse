# One-command reproducibility: docker compose up monitor
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# default: build the report from cache; override with --refresh
CMD ["python", "run_monitor.py"]
