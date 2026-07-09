FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App files (keep in sync with GitHub upload set)
COPY chipbox.html chipbox-app.js phone-test.html silent.wav sb-sync-worker.js ./
COPY multiplayer ./multiplayer
COPY requirements.txt render.yaml Procfile ./

# Render injects PORT at runtime — do NOT hardcode the listen port
ENV PORT=10000
EXPOSE 10000

# Shell form so $PORT expands
CMD ["sh", "-c", "python multiplayer/server.py --host 0.0.0.0 --port ${PORT:-10000}"]
