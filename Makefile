.PHONY: check lint types test validate audit format

check: lint types test validate

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term

validate:
	uv run rt validate

audit:
	uv export --locked --no-emit-project --format requirements-txt --quiet -o .audit-requirements.txt
	uv run pip-audit --strict --disable-pip --require-hashes -r .audit-requirements.txt
	rm -f .audit-requirements.txt

format:
	uv run ruff check --fix .
	uv run ruff format .
