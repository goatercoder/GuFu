# Build the frontend, then serve everything from one Python image.
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    BULWARK_DATA_DIR=/data BULWARK_HOST=0.0.0.0 BULWARK_PORT=8800
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY catalog/ ./catalog/
COPY agent/ ./agent/
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --system --uid 10001 bulwark && mkdir -p /data && chown -R bulwark /data /app
USER bulwark
VOLUME ["/data"]
EXPOSE 8800
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8800/api/health').status==200 else 1)"
CMD ["python", "-m", "uvicorn", "bulwark.main:app", "--host", "0.0.0.0", "--port", "8800", \
     "--app-dir", "backend"]
