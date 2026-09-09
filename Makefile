.PHONY: install test lint cov serve docker

install:
	pip install -r requirements-dev.txt && pip install -e .

test:
	pytest

cov:
	pytest --cov=skillsift --cov-report=term-missing

lint:
	ruff check skillsift tests

serve:
	python -m skillsift serve --debug

docker:
	docker build -t skillsift . && docker run --rm -p 8000:8000 -v skillsift-data:/data skillsift
