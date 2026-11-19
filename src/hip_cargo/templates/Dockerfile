# uv is a named stage, not `COPY --from=<image>`, because Dependabot only reads
# FROM lines; .github/dependabot.yml bumps it. Keep it no older than the uv that
# writes uv.lock, since `uv export --locked` below re-checks the lock with it.
FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.11-slim

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/

# Install the locked dependencies first, so every architecture gets the versions
# CI tested (and this layer is cached until uv.lock changes), then the package
# itself without re-resolving. --locked fails the build if uv.lock is stale.
# Any `git+` line in `uv export --no-dev --extra full` needs git in the image
# (apt-get install git), and that includes a git pin in a dev or test group for a
# package the extra also lists: uv keeps one source per package. A GitHub archive
# URL (https://github.com/<owner>/<repo>/archive/<sha>.tar.gz) needs no git.
COPY pyproject.toml uv.lock ./
RUN uv export --locked --no-dev --extra full --no-emit-project --no-header -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# LICENSE is required by pyproject's license-files glob.
COPY README.md LICENSE ./
COPY src/ src/
RUN uv pip install --system --no-cache --no-deps .

# Make CLI available
CMD ["<CLI_COMMAND>", "--help"]
