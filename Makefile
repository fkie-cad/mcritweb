init:
	pip install -e ".[dev]"
lint:
	python3 -m ruff check .
test:
	python3 -m pytest
test-coverage:
	python3 -m pytest --cov=mcritweb --cov-report=html:coverage-html
clean:
	find . | grep -E "(__pycache__|\.pyc|\.pyo$\)" | xargs rm -rf
	rm -rf .coverage
	rm -rf coverage-html
	rm -rf dist/*
