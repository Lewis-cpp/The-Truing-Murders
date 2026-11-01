# Runtime image for the API. Build from the repository root:
#   docker build -t truing-api -f backend/Dockerfile backend
# Case assets and prompts are packaged into the wheel (pyproject force-include).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY assets ./assets
RUN uv sync --locked --no-dev

# Never bake configuration or secrets into the image: they come from the environment.
RUN useradd --system --create-home truing && chown -R truing:truing /app
USER truing

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
