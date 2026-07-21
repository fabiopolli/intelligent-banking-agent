FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY frontend /app/frontend
COPY scripts /app/scripts
COPY tests /app/tests
COPY knowledge /app/knowledge
COPY prompts /app/prompts
COPY .docs/tabela_geral_de_tarifas_pf_pdf.pdf /app/.docs/tabela_geral_de_tarifas_pf_pdf.pdf

RUN pip install --no-cache-dir -e .[dev]

EXPOSE 8000 8501 8502

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
