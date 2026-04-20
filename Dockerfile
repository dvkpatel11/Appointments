FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
COPY canada /app/canada
WORKDIR /app/canada
RUN mkdir -p screenshots
CMD python -m waitress --port=8080 --host=0.0.0.0 app:app