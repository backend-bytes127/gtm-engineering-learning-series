FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 DATA_DIR=/data
WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY sequencer ./sequencer
COPY config ./config
COPY sample-data ./sample-data

# The app writes only to /data (a persistent volume). The entrypoint starts as root only to fix the volume's
# ownership, then drops to an unprivileged user before the app starts.
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Railway sets PORT. APP_PASSWORD and SESSION_SECRET are required (the server refuses to start without them).
CMD ["/entrypoint.sh"]
