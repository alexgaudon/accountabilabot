.PHONY: install dev build test lint clean

install:
	uv sync

dev:
	uv run python -m discordbot

run:
	docker run --env-file .env discordbot:latest

build:
	docker build . -t discordbot:latest

test:
	@echo "No tests defined"

lint:
	uv run ruff check

clean:
	rm -rf .venv