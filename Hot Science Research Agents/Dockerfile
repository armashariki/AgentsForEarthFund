# syntax=docker/dockerfile:1

FROM node:22-slim AS frontend-builder

WORKDIR /app
COPY web/frontend/package*.json ./web/frontend/
RUN cd web/frontend && npm ci
COPY web/frontend ./web/frontend
RUN cd web/frontend && npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOT_SCIENCE_DATA_DIR=/data/hot_science \
    PORT=8080

WORKDIR /app

RUN mkdir -p /data/hot_science

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-builder /app/web/frontend/dist ./web/frontend/dist

EXPOSE 8080

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
