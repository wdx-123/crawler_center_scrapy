FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY crawler_center /app/crawler_center

EXPOSE 8000

CMD ["uvicorn", "crawler_center.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
