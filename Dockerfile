# Estágio 1: Builder
FROM python:3.13 AS builder
WORKDIR /app

# Instala uv
RUN pip install uv

# Copia dependências e instala
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Estágio 2: Final (imagem limpa)
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY main.py ./
ENV PATH=/app/.venv/bin:$PATH
CMD ["python", "main.py"]