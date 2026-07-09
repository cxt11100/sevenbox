FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chipbox.html chipbox-app.js phone-test.html ./
COPY multiplayer ./multiplayer
ENV PORT=8765
EXPOSE 8765
CMD ["python", "multiplayer/server.py", "--host", "0.0.0.0", "--port", "8765"]
