# Course Finder API

[![CI](https://github.com/Busayor2020/course-finder-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Busayor2020/course-finder-api/actions/workflows/ci.yml)

A small Flask REST API for searching UK and Canadian university courses: ingest messy course data, clean it, store it in MySQL, and serve it through a versioned JSON API.

> **All course data in this repo is synthetic.** University names may be real, but fees, IELTS scores and intakes are illustrative only.

Work in progress. Full documentation arrives in a later phase.

## Quick start (Linux or WSL)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then fill in SECRET_KEY and DATABASE_URL
flask run
curl http://127.0.0.1:5000/health
```

## Running tests

Tests use an in-memory SQLite database, so they need no MySQL and no `.env`.

```bash
pytest -q              # the whole suite
ruff check .           # lint
ruff format --check .  # formatting
```

CI (`.github/workflows/ci.yml`) runs the same three commands on every push and pull request.
