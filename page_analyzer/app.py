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
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    response.encoding = 'utf-8'
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    h1 = soup.h1.get_text().strip() if soup.h1 else ''
                    title = soup.title.string.strip() if soup.title else ''
                    
                    description_tag = soup.find('meta', attrs={'name': 'description'})
                    description = description_tag['content'].strip() if description_tag else ''
                    
                    cursor.execute(
                        """INSERT INTO url_checks 
                        (url_id, status_code, h1, title, description) 
                        VALUES (%s, %s, %s, %s, %s)""",
                        (id, response.status_code, h1, title, description)
                    )
                    conn.commit()
                    
                    flash('Страница успешно проверена', 'success')
                    
                except RequestException as e:
                    conn.rollback()
                    flash(f'Произошла ошибка при проверке: {str(e)}', 'danger')
                    app.logger.error(f"Request failed for URL {url}: {str(e)}")
                
                return redirect(url_for('show_url', id=id))
    
    except Exception as e:
        flash('Произошла внутренняя ошибка', 'danger')
        app.logger.error(f"Error checking URL: {str(e)}")
        return redirect(url_for('show_urls'))


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
                    urls.id, 
                    urls.name, 
                    urls.created_at,
                    MAX(url_checks.created_at) as last_check,
                    (
                        SELECT status_code 
                        FROM url_checks 
                        WHERE url_id = urls.id 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    ) as last_status_code
                FROM urls
                LEFT JOIN url_checks ON urls.id = url_checks.url_id
                GROUP BY urls.id
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
