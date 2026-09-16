FROM python:3.12-slim

WORKDIR /app

COPY qbit_auto_reannounce.py /app/qbit_auto_reannounce.py

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

ENV QBIT_STATE=/data/qbit_reannounce_state.json

CMD ["python", "/app/qbit_auto_reannounce.py"]
