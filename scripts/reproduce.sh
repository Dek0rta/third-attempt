#!/usr/bin/env bash
# Download the OpenPowerlifting snapshot and rebuild every result, figure, the model and the paper.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! ls data/raw/openpowerlifting-*/openpowerlifting-*.csv >/dev/null 2>&1; then
  mkdir -p data/raw
  curl -L -o data/raw/opl.zip https://openpowerlifting.gitlab.io/opl-csv/files/openpowerlifting-latest.zip
  unzip -q -o data/raw/opl.zip -d data/raw
fi

uv run python analysis/01_prepare.py
uv run python analysis/02_descriptive.py
uv run python analysis/03_model.py
uv run python analysis/04_decisions.py
uv run python tests/make_fixture.py
node --test tests/predict.test.mjs
uv run python paper/build.py
