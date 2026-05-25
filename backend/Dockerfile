FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Install API dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install worker/agent dependencies (livekit-agents + plugins)
COPY worker/requirements.txt worker/requirements.txt
RUN pip install --no-cache-dir -r worker/requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
