import os
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL не задан в .env!")
    
    try:
        return psycopg2.connect(database_url, sslmode="disable")
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"Ошибка подключения к БД: {e}")


def normalize_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"