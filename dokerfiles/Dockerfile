FROM python:3.12-slim

# Устанавливаем системные зависимости для asyncpg и сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev wget ca-certificates \
    && wget https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
       -O /usr/local/share/ca-certificates/russian_trusted_root_ca.crt \
    && wget https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt \
       -O /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала копируем requirements для кэширования слоев
COPY ..requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

# Копируем код
COPY . .

# Railway сам задаст PORT, но EXPOSE полезен для локального теста
EXPOSE 8000

# Запускаем uvicorn (FastAPI-приложение)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT:-8000}/webhook || exit 1