NAME = geodispatch

.PHONY: all init prepare update-submodules build up down logs status check test contract-check smoke-check clean fclean re

all: prepare build up

init:
	git submodule update --init --recursive

update-submodules:
	git submodule foreach 'git fetch origin main && git merge --ff-only origin/main'

prepare:
	@if [ ! -f .env ]; then cp .env.example .env; echo ".env created from .env.example"; fi
	@if [ ! -f supervisor/.env ] && [ -f supervisor/.env.example ]; then cp supervisor/.env.example supervisor/.env; echo "supervisor/.env created from supervisor/.env.example"; fi

# ─────────────────────────────────────────────────────────────
# PRODUCTION / FULL-STACK TARGETS (Root docker-compose.yml)
# ─────────────────────────────────────────────────────────────
build: prepare
	docker compose build

up: prepare
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps

contract-check:
	python3 helpers/scripts/validate_contracts.py

smoke-check: prepare
	python3 helpers/scripts/smoke_check.py

check: prepare
	python3 helpers/scripts/check.py

test: prepare
	python3 helpers/scripts/check.py --test

clean:
	docker compose -f supervisor/docker-compose.dev.yml down --volumes --rmi local 2>/dev/null || true
	docker compose down --volumes --rmi local

fclean: clean
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
	@echo "Environment cleaned and Python bytecode purged."

re: fclean all