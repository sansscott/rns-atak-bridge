FROM python:3.11-alpine

# lxml requires libxml2/libxslt build deps on Alpine
RUN apk add --no-cache libxml2-dev libxslt-dev gcc musl-dev

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Store RNS identity in a persistent volume so it survives container restarts
VOLUME ["/rns-identity"]

ENV RNS_CONFIG_DIR=/rns-identity

ENTRYPOINT ["python", "bridge.py", "--config", "/config/config.yaml"]
