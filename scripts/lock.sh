#!/bin/sh
# Regenerate requirements.lock and requirements-dev.lock from pyproject.toml.
# Runs inside the same Python image as production so the pins match Linux / CPython 3.12.
# Usage (from the repository root): sh scripts/lock.sh
set -eu

PY_IMAGE="python:3.12.14-slim-trixie"
PIP_TOOLS="pip-tools==7.6.1"
HEADER="# Exact pins for Linux, CPython 3.12. Do not edit by hand; regenerate with scripts/lock.sh."

docker run --rm -v "$(pwd):/src" -w /src "$PY_IMAGE" sh -c "
  set -eu
  pip install --quiet --disable-pip-version-check '$PIP_TOOLS'
  pip-compile --quiet --strip-extras --no-header --no-annotate -o /tmp/runtime.txt pyproject.toml
  pip-compile --quiet --strip-extras --no-header --no-annotate --extra dev -o /tmp/dev.txt pyproject.toml
  { echo '$HEADER'; echo '# Runtime dependencies (installed in the Docker image).'; cat /tmp/runtime.txt; } > requirements.lock
  { echo '$HEADER'; echo '# Runtime + dev dependencies (tests and lint, used in CI).'; cat /tmp/dev.txt; } > requirements-dev.lock
"
