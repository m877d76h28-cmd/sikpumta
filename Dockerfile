FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    COOKIE_SECURE=1 \
    DATABASE_PATH=/var/data/sikpumta.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /var/data
EXPOSE 5000
CMD ["sh", "-c", "gunicorn app:app --workers 2 --bind 0.0.0.0:${PORT} --timeout 120"]
