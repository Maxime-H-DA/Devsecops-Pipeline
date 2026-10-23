FROM dhi.io/python:3.14.8-debian13-dev@sha256:0fc1a06a500fd1a1a884d7bb53c8da242527878e39eefcf106ed8050e94693ad AS construction

WORKDIR /app
COPY rpg-api/requirements.txt .
RUN python3 -m venv venv \
    && venv/bin/pip install --no-cache-dir -r requirements.txt \
    && venv/bin/pip uninstall -y pip \
    && rm requirements.txt

COPY rpg-api/app.py rpg-api/gunicorn.conf.py ./
COPY rpg-api/templates/ templates/
COPY rpg-api/static/ static/
COPY rpg-source/monsters.csv .

FROM dhi.io/python:3.14.8-debian13@sha256:36c38f4be040b095f67fbb0982d18875518f1b58d23b9ad3cc8bc903a7f7524e

USER 0:0
RUN ["python3", "-m", "pip", "uninstall", "-y", "pip"]

COPY --from=construction --chown=10001:10001 /app /app

ENV PYTHONUTF8=1
ENV PATH="/app/venv/bin:${PATH}"

WORKDIR /app

ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

USER 10001:10001

EXPOSE 5000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
