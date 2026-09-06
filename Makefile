init:
	pip install -r requirements.txt
# ruff is not in requirements.txt - CI installs it pinned, see .github/workflows/test.yml
lint:
	python3 -m ruff check .
# pytest and pytest-cov are NOT covered by requirements.txt: they are not runtime
# dependencies, and mcrit declares them under its `dev` extra. Install them alongside,
# as CI does - see .github/workflows/test.yml
test:
	python3 -m pytest
test-coverage:
	python3 -m pytest --cov=mcritweb --cov-report=html:coverage-html
clean:
	find . | grep -E "(__pycache__|\.pyc|\.pyo$\)" | xargs rm -rf
	rm -rf .coverage
	rm -rf coverage-html
	rm -rf dist/*
