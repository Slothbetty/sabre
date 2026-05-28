FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/src
CMD ["python", "sabre.py", "--help"]
