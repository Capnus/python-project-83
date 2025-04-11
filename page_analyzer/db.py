import os
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    # Проверяем, что DATABASE_URL загружен
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL не найден в переменных окружения!")
    
    # Подключаемся с SSL (обязательно для Render)
    return psycopg2.connect(database_url, sslmode="require")


def normalize_url(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"
