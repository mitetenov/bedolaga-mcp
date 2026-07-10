FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bedolaga_server.py http_server.py ./

EXPOSE 3100

# Run the HTTP server by default. Override with --entrypoint for stdio mode.
CMD ["python3", "http_server.py"]
