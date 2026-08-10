FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    TMPDIR=/tmp

RUN groupadd --gid 65532 datasynq \
    && useradd --uid 65532 --gid datasynq --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin datasynq

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY --chown=65532:65532 app ./app

USER 65532:65532

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--timeout-graceful-shutdown", "25"]
