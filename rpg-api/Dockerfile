FROM dhi.io/python:3.15.2-debian13-dev@sha256:f8af7491df42d4d0b0a3d52e69992df7e3837c09483ec49a513a7e4375ce4d32 AS construction

WORKDIR /app
COPY rpg-api/requirements.txt .
RUN python3 -m venv venv \
    && venv/bin/pip install --no-cache-dir --require-hashes -r requirements.txt \
    && venv/bin/pip uninstall -y pip \
    && rm requirements.txt

COPY rpg-api/app.py rpg-api/gunicorn.conf.py ./
COPY rpg-api/templates/ templates/
COPY rpg-api/static/ static/
COPY rpg-source/monsters.csv .

FROM dhi.io/python:3.15.2-debian13@sha256:37a0fd449194addf16e7076b68fea74793447c0b1be0844eb57a1734e3f2ab69

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
