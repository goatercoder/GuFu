# Stage 1: build the React frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime serving API + built frontend on one port
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GUFU_DB_PATH=/app/backend/data/gufu.sqlite
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=web /web/dist frontend/dist
RUN mkdir -p /app/backend/data
VOLUME ["/app/backend/data"]
EXPOSE 8000
WORKDIR /app/backend
# Render (and other hosts) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn gufu.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
