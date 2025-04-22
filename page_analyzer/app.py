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


@app.route("/")
def index():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM urls LIMIT 10")
            urls = cursor.fetchall()
        return render_template('index.html', urls=urls)
    finally:
        conn.close()


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


@app.post('/urls/<int:id>/checks')
def check_url(id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=NamedTupleCursor) as cursor:
                cursor.execute("SELECT name FROM urls WHERE id = %s", (id,))
                url = cursor.fetchone()
                
                if not url:
                    flash('Страница не найдена', 'danger')
                    return redirect(url_for('show_urls'))
                
                try:
                    response = requests.get(url.name, timeout=5)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    h1 = soup.h1.get_text().strip() if soup.h1 else None
                    title = soup.title.string.strip() if soup.title else None
                    description = soup.find('meta', attrs={'name': 'description'})
                    description = description['content'].strip() if description else None
                    
                    cursor.execute(
                        """INSERT INTO url_checks 
                        (url_id, status_code, h1, title, description) 
                        VALUES (%s, %s, %s, %s, %s)""",
                        (id, response.status_code, h1, title, description)
                    )
                    conn.commit()
                    flash('Страница успешно проверена', 'success')
                except Exception as e:
                    cursor.execute(
                        """INSERT INTO url_checks 
                        (url_id, status_code) 
                        VALUES (%s, %s)""",
                        (id, 500)
                    )
                    conn.commit()
                    flash('Произошла ошибка при проверке', 'danger')
                    app.logger.error(f"Error checking URL {url.name}: {str(e)}")
                
                return redirect(url_for('show_url', id=id))
    
    except Exception as e:
        flash('Произошла внутренняя ошибка', 'danger')
        app.logger.error(f"Error checking URL: {str(e)}")
        return redirect(url_for('show_url', id=id))


if __name__ == "__main__":
    app.run()
