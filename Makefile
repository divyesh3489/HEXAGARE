.PHONY: up down logs migrate test lint seed backend-shell frontend-shell

up:              ## Build and start all services
	docker compose up --build

down:            ## Stop all services
	docker compose down

logs:            ## Tail logs for all services
	docker compose logs -f

migrate:         ## Apply database migrations
	docker compose run --rm backend python manage.py migrate

test:            ## Run the backend test suite
	docker compose run --rm -e DJANGO_ENV=test backend python manage.py test

lint:            ## Lint the backend (ruff); frontend lint added in Phase 1
	docker compose run --rm backend ruff check --no-cache .

seed:            ## Load demo products / users
	docker compose exec backend python manage.py seed_demo_data

backend-shell:   ## Open a shell in the backend container
	docker compose run --rm backend sh

frontend-shell:  ## Open a shell in the frontend container (Phase 1)
	docker compose run --rm frontend sh
