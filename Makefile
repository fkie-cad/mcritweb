init:
	pip install -r requirements.txt
# ruff is not in requirements.txt - CI installs it pinned, see .github/workflows/test.yml
lint:
	python3 -m ruff check .
# pytest and pytest-cov arrive with mcrit, so requirements.txt covers both
test:
	python3 -m pytest
test-coverage:
	python3 -m pytest --cov=mcritweb --cov-report=html:coverage-html
clean:
	find . | grep -E "(__pycache__|\.pyc|\.pyo$\)" | xargs rm -rf
	rm -rf .coverage
	rm -rf coverage-html
	rm -rf dist/*
