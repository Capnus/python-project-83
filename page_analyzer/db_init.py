from db import get_connection

SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS urls (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS url_checks (
    id BIGSERIAL PRIMARY KEY,
    url_id BIGINT REFERENCES urls(id),
    status_code INT,
    h1 VARCHAR(255),
    title VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
"""


def init_db():
    """Создает таблицы при первом запуске."""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(SQL_CREATE_TABLES)
        conn.commit()
        print("Таблицы созданы")
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    init_db()