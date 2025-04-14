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


@app.post('/urls/<int:id>/checks')
def check_url(id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
                cursor.execute("SELECT name FROM urls WHERE id = %s", (id,))
                url_record = cursor.fetchone()
                if not url_record:
                    flash('Сайт не найден', 'danger')
                    return redirect(url_for('show_urls'))
                
                url = url_record.name

        try:
            response = requests.get(
                url,
                timeout=10, 
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            h1 = soup.find('h1')
            h1 = h1.text.strip().encode('utf-8').decode('utf-8') if h1 else None
            
            title = soup.find('title')
            title = (
                title.text.strip().encode('utf-8').decode('utf-8') 
                if title 
                else None
            )

            description = soup.find('meta', attrs={'name': 'description'})
            description = (
                description['content'].strip().encode('utf-8').decode('utf-8') 
                if description 
                else None
            )
            
            with get_connection() as conn:
                with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
                    cursor.execute(
                        """INSERT INTO url_checks 
                        (url_id, status_code, h1, title, description) 
                        VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (id, response.status_code, h1, title, description)
                    )
                    
                    cursor.execute(
                        "UPDATE urls SET created_at = NOW() WHERE id = %s",
                        (id,)
                    )
            
            flash('Страница успешно проверена', 'success')
        
        except RequestException as e:
            flash('Произошла ошибка при проверке', 'danger')
            app.logger.error(f"Request failed for URL {url}: {str(e)}")
            return redirect(url_for('show_url', id=id))
    
    except Exception as e:
        flash('Произошла внутренняя ошибка', 'danger')
        app.logger.error(f"Error checking URL: {str(e)}")
    
    return redirect(url_for('show_url', id=id))


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


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r') as f:
                    cursor.execute(f.read())
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                print(f"Database initialization error: {e}")


init_db()


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
