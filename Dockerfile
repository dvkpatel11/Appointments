# Base image has everything: Python 3.12, playwright 1.49.1, greenlet, pyee, chromium
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app
COPY requirements.txt .  # ignored - base image has all deps
COPY . .

WORKDIR /app/canada
RUN mkdir -p screenshots

ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=false
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "waitress-serve --port=${PORT} --host=0.0.0.0 app:app"]