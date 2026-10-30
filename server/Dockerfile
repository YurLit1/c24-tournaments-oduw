# One image for app-a, app-b and the gateways (and your publisher and handler, when you write
# them): the command in compose.yaml selects the process. Python 3.14, dependencies from uv.lock.
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv

# dependencies first: this layer is rebuilt only when pyproject.toml or uv.lock change
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

COPY app ./app
RUN mkdir -p /faults

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
