.PHONY: test test-py test-js install

test: test-py test-js

test-py:
	uv run pytest -v

test-js:
	npm --prefix frontend test

install:
	uv sync --all-groups
	npm --prefix frontend ci
