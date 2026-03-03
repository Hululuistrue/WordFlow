# Deployment Guide

This document provides a production deployment path for this repository:

- Backend: FastAPI + in-process async job queue
- Frontend: Next.js
- Reverse proxy: Nginx
- Database: PostgreSQL

## Recommended Topology

Use one Linux VM (Ubuntu 22.04/24.04) for initial production:

- `app.your-domain.com` -> Next.js (`127.0.0.1:3000`)
- `api.your-domain.com` -> FastAPI (`127.0.0.1:8000`)
- PostgreSQL on managed service or same VM

Important: the current backend job queue is process-local. Run exactly one backend process/replica, otherwise queue state will not be shared across replicas.

## 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm nginx ffmpeg
```

Notes:

- `nodejs` is required by current default `YTDLP_JS_RUNTIMES=node`.
- `ffmpeg` is required by ASR/audio processing stack.

## 2. Clone Repository

```bash
git clone https://github.com/Hululuistrue/WordFlow.git
cd WordFlow
```

## 3. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Create runtime directories:

```bash
sudo mkdir -p /srv/wordflow/tmp /srv/wordflow/storage
sudo chown -R "$USER:$USER" /srv/wordflow
```

## 4. Configure Backend Environment

Edit `backend/.env` for production:

```env
APP_ENV=prod
APP_HOST=127.0.0.1
APP_PORT=8000
LOG_LEVEL=INFO

TEMP_DIR=/srv/wordflow/tmp
UPLOAD_STORAGE_DIR=/srv/wordflow/storage

DATABASE_URL=postgresql+psycopg://DB_USER:DB_PASSWORD@DB_HOST:5432/wordflow
DATABASE_ECHO=false
DATABASE_AUTO_CREATE_TABLES=false

TASK_POLL_INTERVAL_SECONDS=2
SUBTITLE_FETCH_TIMEOUT_SECONDS=180
YTDLP_JS_RUNTIMES=node
ALLOW_USER_SUPPLIED_COOKIES=false
```

## 5. Run Database Migration

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

## 6. Run Backend with systemd

Create `/etc/systemd/system/wordflow-backend.service`:

```ini
[Unit]
Description=WordFlow Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/WordFlow/backend
EnvironmentFile=/opt/WordFlow/backend/.env
ExecStart=/opt/WordFlow/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Adjust `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` to your actual path.

Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wordflow-backend
sudo systemctl status wordflow-backend
```

## 7. Frontend Setup and systemd

Install and build:

```bash
cd /opt/WordFlow/frontend
npm ci
NEXT_PUBLIC_API_BASE=https://api.your-domain.com npm run build
```

Create `/etc/systemd/system/wordflow-frontend.service`:

```ini
[Unit]
Description=WordFlow Frontend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/WordFlow/frontend
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wordflow-frontend
sudo systemctl status wordflow-frontend
```

## 8. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/wordflow.conf`:

```nginx
server {
    listen 80;
    server_name app.your-domain.com;

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name api.your-domain.com;

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/wordflow.conf /etc/nginx/sites-enabled/wordflow.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 9. Enable HTTPS

Use certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d app.your-domain.com -d api.your-domain.com
```

## 10. Verify Deployment

Backend health:

```bash
curl -s http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

Then open frontend in browser and test:

1. Upload flow (`upload -> job -> transcript -> export`)
2. YouTube URL flow

## 11. Update Procedure

```bash
cd /opt/WordFlow
git pull origin main

cd backend
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart wordflow-backend

cd ../frontend
npm ci
NEXT_PUBLIC_API_BASE=https://api.your-domain.com npm run build
sudo systemctl restart wordflow-frontend
```

## 12. Operational Notes

- Keep `backend/.env` out of git.
- Use managed PostgreSQL backups or scheduled dumps.
- Keep only one backend process until queue is moved to shared infra (for example Redis/Celery/RQ).
- If YouTube extraction has regional/rate-limit issues, inspect backend logs:

```bash
sudo journalctl -u wordflow-backend -n 200 --no-pager
```
