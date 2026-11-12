# Build from the repository root:  docker build -f projects/04-contact-cleaning-app/Dockerfile .
# The app reuses project 02's `pipeline` package, so both projects are copied with their relative layout.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/projects/04-contact-cleaning-app

COPY projects/04-contact-cleaning-app/requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY projects/02-contact-list-merge/pipeline /app/projects/02-contact-list-merge/pipeline
COPY projects/02-contact-list-merge/sample-data /app/projects/02-contact-list-merge/sample-data
COPY projects/04-contact-cleaning-app/contactapp ./contactapp

# Nothing is written to disk: uploads live in memory and are discarded after 30 minutes of inactivity.
RUN useradd --create-home --uid 10001 app
USER app

# Railway sets PORT. Public mode: no login, and the app refuses to start with a HubSpot token.
CMD ["sh", "-c", "python -m contactapp --host 0.0.0.0 --port ${PORT:-8770} --no-browser"]
