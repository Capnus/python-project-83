from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime
import validators
import os
from dotenv import load_dotenv
from .db import get_connection, normalize_url
import psycopg2
from psycopg2.extras import NamedTupleCursor

load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


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
                    "INSERT INTO urls (name) VALUES (%s) RETURNING id",
                    (normalized_url,)
                )
                url_id = cursor.fetchone().id
                flash('Страница успешно добавлена', 'success')
                return redirect(url_for('show_url', id=url_id))
            except psycopg2.IntegrityError:
                conn.rollback()
                cursor.execute(
                    "SELECT id FROM urls WHERE name = %s",
                    (normalized_url,)
                )
                url_id = cursor.fetchone().id
                flash('Страница уже существует', 'info')
                return redirect(url_for('show_url', id=url_id))


@app.route('/urls')
def show_urls():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
            cursor.execute("""
                SELECT 
                    urls.id, 
                    urls.name, 
                    urls.created_at,
                    url_checks.created_at as last_check,
                    url_checks.status_code as last_status_code
                FROM urls
                LEFT JOIN url_checks ON urls.id = url_checks.url_id
                AND url_checks.id = (
                    SELECT MAX(id) 
                    FROM url_checks 
                    WHERE url_checks.url_id = urls.id
                )
                ORDER BY urls.created_at DESC
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
                "SELECT * FROM url_checks WHERE url_id = %s ORDER BY created_at DESC",
                (id,)
            )
            checks = cursor.fetchall()
    
    return render_template('urls/show.html', url=url, checks=checks)


@app.post('/urls/<int:id>/checks')
def check_url(id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
            cursor.execute(
                "INSERT INTO url_checks (url_id) VALUES (%s) RETURNING id",
                (id,)
            )
            check_id = cursor.fetchone().id
            
            cursor.execute(
                "UPDATE urls SET created_at = NOW() WHERE id = %s",
                (id,)
            )
    
    flash('Страница успешно проверена', 'success')
    return redirect(url_for('show_url', id=id))


@app.errorhandler(404)
def page_not_found(error):
    try:
        return render_template('errors/404.html'), 404
    except:
        return "Страница не найдена", 404

@app.errorhandler(500)
def server_error(error):
    try:
        return render_template('errors/500.html'), 500
    except:
        return "Внутренняя ошибка сервера", 500

def init_db():
    with app.app_context():
        with get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute("SELECT 1 FROM urls LIMIT 1")
                except psycopg2.Error:
                    with open('database.sql') as f:
                        cursor.execute(f.read())
                    conn.commit()
                    print("Database tables created successfully")

init_db()
