.PHONY: up down logs seed test verify proto migrate lint fmt demo

up:
	docker compose up -d --build mysql redis kafka
	docker compose up --build migrate
	docker compose up -d --build data-service worklist-api engine scheduler ui

down:
	docker compose down -v

logs:
	docker compose logs -f

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm sync

test:
	docker compose run --rm --no-deps -e ROLE=worklist-api worklist-api pytest -q

verify:
	docker compose run --rm --no-deps -e ROLE=worklist-api worklist-api python tests/oracle.py

proto:
	python -m grpc_tools.protoc -I proto \
		--python_out=libs/common/grpc_gen \
		--grpc_python_out=libs/common/grpc_gen \
		--pyi_out=libs/common/grpc_gen \
		proto/dataservice.proto

lint:
	ruff check .

fmt:
	ruff format .

demo: up seed
	@echo "Swagger UI:  http://localhost:8000/docs"
	@echo "Dashboard:   http://localhost:3000"
