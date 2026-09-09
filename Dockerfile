FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SKILLSIFT_DB=/data/skillsift.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY skillsift ./skillsift
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --no-deps -e .

# The database lives on a volume so application history survives a redeploy.
RUN mkdir -p /data && useradd --create-home app && chown -R app /data /app
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "skillsift.web:create_app()"]
