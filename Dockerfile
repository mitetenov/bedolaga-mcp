FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bedolaga_server.py .

ENTRYPOINT ["python3", "bedolaga_server.py"]
