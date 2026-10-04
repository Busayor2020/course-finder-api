# Course Finder API

[![CI](https://github.com/Busayor2020/course-finder-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Busayor2020/course-finder-api/actions/workflows/ci.yml)

A small Flask REST API for searching UK and Canadian university courses: ingest messy course data, clean it, store it in MySQL, and serve it through a versioned JSON API.

> **All course data in this repo is synthetic.** University names may be real, but fees, IELTS scores and intakes are illustrative only.

Full documentation arrives in a later phase; the deployment guide is below.

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

## Deployment

Production runs the way most Python services on a Linux box do:

```
browser ──▶ Nginx :80/:443 ──unix socket──▶ Gunicorn (systemd) ──▶ Flask app ──▶ MySQL
            static files, gzip,             2 x cores + 1 workers,
            rate limit on /api/             restart on failure
```

| File | What it does |
|---|---|
| `deploy/gunicorn.conf.py` | Gunicorn: unix socket, worker count, timeouts, worker recycling, logs to the journal |
| `deploy/course-finder.service` | systemd unit: runs Gunicorn as the unprivileged `coursefinder` user, loads `.env`, restarts on failure, graceful reload, sandboxing |
| `deploy/nginx.conf` | Nginx site: reverse proxy to the socket, serves `/static/` itself, gzip, security headers, rate limiting on `/api/` |
| `deploy/setup.sh` | Runs every step below. Safe to re-run: the first run provisions, later runs deploy |

### 1. Prepare the server (VPS only)

On a fresh Ubuntu 26.04 VPS, as root, create a sudo user and switch to SSH keys:

```bash
adduser victor && usermod -aG sudo victor
# On your own machine: ssh-copy-id victor@SERVER_IP, and check you can log in.
# Then on the server, turn off password and root logins:
printf 'PasswordAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/90-hardening.conf
sudo systemctl reload ssh
```

### 2. Provision and deploy

```bash
git clone https://github.com/Busayor2020/course-finder-api.git
cd course-finder-api
sudo bash deploy/setup.sh
```

What `deploy/setup.sh` does, in order (each command is in the script):

1. **Packages:** `apt-get install python3-venv mysql-server nginx git curl`. On 26.04 these give Python 3.14 and MySQL 8.4 LTS, matching development.
2. **App user:** `useradd --system --shell /usr/sbin/nologin coursefinder`, and `/srv/course-finder` owned by `coursefinder:www-data`, mode 750.
3. **Code:** `git clone` into `/srv/course-finder` on the first run, `git pull --ff-only` after that.
4. **Python:** a venv at `/srv/course-finder/.venv` with `requirements.txt` only (no dev tools in production).
5. **Database (first run only):** creates `course_finder_prod` and a MySQL user with privileges on that database only, authenticating with MySQL 8.4's default `caching_sha2_password`. Writes `.env` (mode 600) with a random `SECRET_KEY`, the database URL and `FLASK_DEBUG=0`. Existing secrets are never overwritten.
6. **Schema and data:** `flask db upgrade`, then `flask ingest data/sample_courses.csv`.
7. **Gunicorn:** installs the systemd unit, then `systemctl enable` and `start` (or `reload` if it is already running, so a deploy drops no requests).
8. **Nginx:** installs the site, removes the default site, runs `nginx -t`, then reloads.
9. **Firewall:** `ufw allow OpenSSH`, `ufw allow 'Nginx Full'`, `ufw enable`. Skipped on WSL.

It finishes with a smoke test: `/health` through Nginx, and a check that Flask debug is off.

### 3. HTTPS (VPS with a domain)

Point a DNS A record at the server, set `server_name` in `/etc/nginx/sites-available/course-finder`, then:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d course-finder.example.com   # adds the 443 server block and renews automatically
```

### Operating it

```bash
systemctl status course-finder                         # running? since when?
journalctl -u course-finder -f                         # Gunicorn access and error logs
sudo tail -f /var/log/nginx/course-finder.access.log   # Nginx access log
sudo systemctl reload course-finder                    # graceful reload after a deploy
sudo -u coursefinder /srv/course-finder/.venv/bin/gunicornc \
    -s /run/course-finder/gunicorn.ctl -c "show workers"  # live worker list
```

To deploy a new version, push to `main` and re-run `sudo bash deploy/setup.sh`.

### Rehearsing on WSL2

The same script runs inside WSL2 on Ubuntu 26.04 with systemd enabled (`[boot] systemd=true` in `/etc/wsl.conf`). It caps Gunicorn at 3 workers on WSL, and skips the firewall because Windows sits in front. Open http://localhost/ in a Windows browser: WSL forwards `localhost` to Nginx inside the VM.
