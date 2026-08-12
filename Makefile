.PHONY: test test-py test-js install lint update-locks update-locks-py update-locks-js

test: test-py test-js

test-py:
	uv run pytest -v

test-js:
	npm --prefix frontend test

install:
	uv sync --all-groups
	npm --prefix frontend ci

lint:
	uv run ruff check --fix .
	uv run ruff format .

update-locks: update-locks-py update-locks-js

update-locks-py:
	uv lock --upgrade
	uv sync --all-groups

update-locks-js:
	npm --prefix frontend update
