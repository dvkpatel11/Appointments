FROM mcr.microsoft.com/playwright/python:v1.58.0-noble
COPY canada /app/canada
WORKDIR /app/canada
RUN mkdir -p screenshots
RUN python -m playwright install --with-deps chromium
CMD python -m waitress --port=8080 --host=0.0.0.0 app:app