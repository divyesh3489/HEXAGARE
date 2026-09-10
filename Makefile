.PHONY: up down logs migrate test lint lint-backend lint-frontend build-frontend seed backend-shell frontend-shell

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

lint: lint-backend lint-frontend  ## Lint backend (ruff) and frontend (eslint)

lint-backend:    ## Lint the backend with ruff
	docker compose run --rm backend ruff check --no-cache .

lint-frontend:   ## Lint the frontend with eslint
	docker compose run --rm frontend npm run lint

build-frontend:  ## Type-check and production-build the frontend
	docker compose run --rm frontend npm run build

seed:            ## Load demo products / users
	docker compose exec backend python manage.py seed_demo_data

backend-shell:   ## Open a shell in the backend container
	docker compose run --rm backend sh

frontend-shell:  ## Open a shell in the frontend container
	docker compose run --rm frontend sh
