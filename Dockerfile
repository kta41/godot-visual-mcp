FROM python:3.11-slim

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY palettes ./palettes
COPY workflows ./workflows
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["uv", "run", "--no-dev", "python", "-m", "server.main"]
