import os

import psycopg2
import requests
import validators
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from psycopg2.extras import NamedTupleCursor
from requests.exceptions import RequestException

from .db import get_connection, normalize_url

load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS urls (
                        id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                        name varchar(255) UNIQUE NOT NULL,
                        created_at timestamp DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS url_checks (
                        id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                        url_id bigint REFERENCES urls (id) ON DELETE CASCADE,
                        status_code int,
                        h1 varchar(255),
                        title varchar(255),
                        description text,
                        created_at timestamp DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                print(f"Database initialization error: {e}")


init_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.post('/urls')
def add_url():
    url = request.form.get('url')
    
    if not url:
        flash('URL обязателен', 'danger')
        return render_template('index.html'), 422
    
    if not validators.url(url) or len(url) > 255:
        flash('Некорректный URL', 'danger')
        return render_template('index.html'), 422
    
    normalized_url = normalize_url(url)
    
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
            try:
                cursor.execute(
                    "SELECT id FROM urls WHERE name = %s",
                    (normalized_url,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    flash('Страница уже существует', 'info')
                    return redirect(url_for('show_url', id=existing.id))
                
                cursor.execute(
                    "INSERT INTO urls (name) VALUES (%s) RETURNING id",
                    (normalized_url,)
                )
                url_id = cursor.fetchone().id
                conn.commit()
                flash('Страница успешно добавлена', 'success')
                return redirect(url_for('show_url', id=url_id))
                
            except Exception as e:
                conn.rollback()
                flash('Произошла ошибка при добавлении URL', 'danger')
                app.logger.error(f"Error adding URL: {str(e)}")
                return render_template('index.html'), 500


@app.errorhandler(404)
def page_not_found(error):
    try:
        return render_template('errors/404.html'), 404
    except Exception:
        return "Страница не найдена", 404


@app.errorhandler(500)
def server_error(error):
    try:
        return render_template('errors/500.html'), 500
    except Exception:
        return "Внутренняя ошибка сервера", 500


@app.route('/urls')
def show_urls():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
            cursor.execute("""
                SELECT 
                    u.id, 
                    u.name, 
                    u.created_at,
                    uc.status_code as last_status_code,
                    uc.created_at as last_check
                FROM urls u
                LEFT JOIN (
                    SELECT DISTINCT ON (url_id) *
                    FROM url_checks
                    ORDER BY url_id, created_at DESC
                ) uc ON u.id = uc.url_id
                ORDER BY u.created_at DESC
            """)
            urls = cursor.fetchall()
    return render_template('urls/index.html', urls=urls)


@app.route('/urls/<int:id>')
def show_url(id):  
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
            cursor.execute("SELECT * FROM urls WHERE id = %s", (id,))
            url = cursor.fetchone()
            
            cursor.execute(
                """
                SELECT * 
                FROM url_checks 
                WHERE url_id = %s 
                ORDER BY created_at DESC
                """,
            (id,)
            )
            checks = cursor.fetchall()
    
    return render_template('urls/show.html', url=url, checks=checks)
