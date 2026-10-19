FROM dhi.io/python:3.14.8-debian13-dev@sha256:c73dad82bf13f79fc2677318eb95c4a76c5920635d1177a2618da621c8953fbd AS construction

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

FROM dhi.io/python:3.14.8-debian13@sha256:b2dee88be07689a608f86c392dd863f20399f8ffcbe99eff6bdb4f04485d9298

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
