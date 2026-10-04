#!/usr/bin/env bash
# Provision and deploy Course Finder on Ubuntu 26.04: Gunicorn under systemd,
# behind Nginx, with MySQL on the same machine.
#
#   sudo bash deploy/setup.sh [git-repo-url]
#
# Safe to re-run: every step checks before it changes anything, so the first run
# provisions the server and every later run is a deploy (pull, install, migrate,
# graceful reload). Works on a VPS and inside WSL2 with systemd enabled.
set -euo pipefail

REPO_URL="${1:-https://github.com/Busayor2020/course-finder-api.git}"
APP_USER=coursefinder
APP_DIR=/srv/course-finder
DB_NAME=course_finder_prod
DB_USER=course_finder_prod

step() { printf '\n==> %s\n' "$*"; }
# Run a command as the app user, from the app directory.
as_app() { (cd "$APP_DIR" && sudo -u "$APP_USER" -H "$@"); }

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo bash deploy/setup.sh" >&2
    exit 1
fi
if grep -qi microsoft /proc/version; then IS_WSL=yes; else IS_WSL=no; fi

step "1/9 System packages"
apt-get update -q
apt-get install -y -q python3-venv mysql-server nginx git curl

step "2/9 App user: a system account with no login shell"
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
# Group www-data lets Nginx read the static files; everyone else is locked out.
install -d -o "$APP_USER" -g www-data -m 750 "$APP_DIR"

step "3/9 Code from $REPO_URL"
if [[ -d $APP_DIR/.git ]]; then
    as_app git pull --ff-only
else
    as_app git clone "$REPO_URL" "$APP_DIR"
fi

step "4/9 Python virtualenv and production dependencies"
[[ -d $APP_DIR/.venv ]] || as_app python3 -m venv .venv
as_app .venv/bin/pip install --no-cache-dir -q -r requirements.txt

step "5/9 MySQL database, least-privilege user and .env (first run only)"
if [[ -f $APP_DIR/.env ]]; then
    echo ".env exists; keeping the existing secrets."
else
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(24))")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    # Privileges on this one database only; the migrations need the DDL ones.
    mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES
    ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
SQL
    # On a VPS, leave GUNICORN_WORKERS unset and use the 2 x cores + 1 formula.
    # A laptop has many cores but shares them with everything else, so cap it.
    WORKERS_LINE=""
    [[ $IS_WSL == yes ]] && WORKERS_LINE="GUNICORN_WORKERS=3"
    install -o "$APP_USER" -g "$APP_USER" -m 600 /dev/null "$APP_DIR/.env"
    cat > "$APP_DIR/.env" <<ENV
FLASK_APP=wsgi.py
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=$SECRET_KEY
DATABASE_URL=mysql+pymysql://$DB_USER:$DB_PASSWORD@127.0.0.1:3306/$DB_NAME?charset=utf8mb4
REPORTS_DIR=reports
$WORKERS_LINE
ENV
fi

step "6/9 Database migrations and sample data"
as_app .venv/bin/flask db upgrade
# Ingestion is idempotent, so re-running it on each deploy only re-verifies rows.
as_app .venv/bin/flask ingest data/sample_courses.csv

step "7/9 Gunicorn under systemd"
install -m 644 "$APP_DIR/deploy/course-finder.service" /etc/systemd/system/course-finder.service
systemctl daemon-reload
systemctl enable --quiet course-finder
if systemctl is-active --quiet course-finder; then
    systemctl reload course-finder  # graceful: no dropped requests
else
    systemctl start course-finder
fi

step "8/9 Nginx"
install -m 644 "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/course-finder
ln -sf /etc/nginx/sites-available/course-finder /etc/nginx/sites-enabled/course-finder
rm -f /etc/nginx/sites-enabled/default
nginx -t  # never reload a broken config
systemctl enable --quiet nginx
systemctl reload-or-restart nginx

step "9/9 Firewall"
if [[ $IS_WSL == yes ]]; then
    echo "Skipped on WSL: Windows sits in front and its firewall applies."
else
    ufw allow OpenSSH
    ufw allow 'Nginx Full'
    ufw --force enable
fi

step "Smoke test"
curl -fsS http://127.0.0.1/health && echo
as_app bash -c 'set -a; source .env; .venv/bin/python -c "from wsgi import app; print(\"Flask debug:\", app.debug)"'
echo "Done. Open http://localhost/ (WSL) or http://<server-ip>/ (VPS)."
