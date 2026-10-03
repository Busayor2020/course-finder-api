# Course Finder API

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
