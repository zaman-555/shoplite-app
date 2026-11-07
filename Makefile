.PHONY: build up down test smoke

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

test:
	docker build --target test -f services/catalog-api/Dockerfile -t shoplite-catalog-api-test .
	docker run --rm shoplite-catalog-api-test
	docker build --target test -f services/order-worker/Dockerfile -t shoplite-order-worker-test .
	docker run --rm shoplite-order-worker-test

smoke:
	./scripts/smoke-test.sh
