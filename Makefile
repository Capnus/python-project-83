PORT ?= 8000

install:
	uv sync

dev:
	uv run flask --debug --app page_analyzer:app run

start:
	uv run gunicorn -w 5 -b 0.0.0.0:$(PORT) page_analyzer:app

build:
	./build.sh

render-start:
	gunicorn -w 5 -b 0.0.0.0:$(PORT) page_analyzer:app

check: 
	test lint

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

test:
	uv run pytest

test-coverage:
	uv run pytest --cov-report xml --cov ./tests