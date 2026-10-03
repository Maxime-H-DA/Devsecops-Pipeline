FROM python:3.14-slim

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONUTF8=1

WORKDIR /app
COPY rpg-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip uninstall -y pip

COPY rpg-api/app.py .
COPY rpg-api/templates/ templates/
COPY rpg-api/static/ static/
COPY rpg-source/monsters.csv .

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["python", "app.py"]
