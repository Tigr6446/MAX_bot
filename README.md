# MAX Event Bot

Бот-агрегатор событий для мессенджера MAX. Парсит сообщения из каналов (спорт, волонтёрство, досуг), фильтрует их через эвристику и отправляет пользователю только релевантные события по его интересам.

**Бот в MAX:** [@t277_hakaton_max_bot](https://max.ru/t277_hakaton_max_bot)

# Пользовательский сценарий:
- Запустить бота или прописать в чате с ботом команду /start.
- Пройти регистрацию: ввести регион (например, Республика Татарстан),
город и выбрать интересы из списка.
- Отправить в чат свободный запрос: «Скинь волонтёрские мероприятия» или
«Хочу культурные события».
- Получить список актуальных событий и зарегистрироваться на интересующем
мероприятии
- При необходимости изменить параметры профиля с помомщью команды /settings

# Стек

- Python 3.12
- [maxapi](https://pypi.org/project/maxapi/) — библиотека для работы с MAX Bot API
- FastAPI + Uvicorn — веб-сервер для приёма вебхуков
- PostgreSQL 16 — хранение пользователей и событий
- SQLAlchemy (async) + asyncpg — ORM и драйвер БД
- Docker + Docker Compose — контейнеризация

# Состав и архитектура решения
- `main.py` — точка входа, FastAPI + вебхук MAX.
- `app/handlers/` — обработчики команд и онбординга.
- `app/handlers/channels/` — парсер каналов MAX.
- `app/handlers/user_command_scripts/` — команды пользователя, настройки, регистрация пользователя.
- `app/Analyzer/` — эвристический анализатор текста.
- `app/background/` — фоновые задачи (парсер, библиотекарь).
- `app/database/` — модели и запросы к PostgreSQL.
- `app/config.py` — настройки через `.env`.

# Порты
- 8000 FastAPI/Uvicorn (приём вебхуков MAX)
- 5432 - PostgreSQL

# Запуск через Docker

## Подготовка

cp .env.example .env

## Запуск

docker compose -f dockerfiles/docker-compose.yml up --build -d

## Проверка

docker compose -f dockerfiles/docker-compose.yml logs -f bot

### Должно появится

INFO: Application startup complete.
INFO: Unicorn running on http://0.0.0.0:8000

## Остановка

docker compose -f dockerfiles/docker-compose.yml down

# Необходимые параметры окружения

MAX_BOT-TOKEN 
WEBHOOK_SECRET
DATABASE_URL
PUBLIC_URL
PARSER_CHANNELS

# Python-пакеты

maxapi - Bot API MAX (Dispatcher, Router, Bot)

maxapi-python - клиент для парсинга каналов (модуль pymax)

fastapi + unicorn[standard] - веб-сервер

sqlalchemy[asyncio] + asyncpg - ORM и драйвер PostgreSQL

pydantic-settings - настройки

python-dotenv - загрузка .env

# Системные

python 3.12

PostgreSQL 16