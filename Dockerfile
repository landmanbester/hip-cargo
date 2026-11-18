FROM python:3.11-slim

WORKDIR /app

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /usr/local/bin/uv

# Install the locked dependencies first, so every architecture gets the versions
# CI tested (and this layer is cached until uv.lock changes), then the package
# itself without re-resolving. --locked fails the build if uv.lock is stale.
COPY pyproject.toml uv.lock ./
RUN uv export --locked --no-dev --extra all --no-emit-project --no-header -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY README.md ./
COPY src/ src/
RUN uv pip install --system --no-cache --no-deps .

# Make CLI available
CMD ["hip-cargo", "--help"]
