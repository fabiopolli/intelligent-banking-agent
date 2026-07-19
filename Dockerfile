FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY frontend /app/frontend
COPY tests /app/tests

RUN pip install --no-cache-dir -e .[dev]

EXPOSE 8000 8501 8502

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
