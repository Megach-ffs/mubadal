
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYCODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
   apt-get install -y libreoffice && \
   apt-get clean && \
   rm -rf /var/lib/apt/lists/*


COPY reqirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .



