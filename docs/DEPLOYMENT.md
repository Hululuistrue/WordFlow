# Deployment Plan for ominiscribe.online

This is a domain-specific deployment guide for:

- Production frontend on Vercel: `app.ominiscribe.online`
- Backup frontend on Cloudflare Workers: `app-cf.ominiscribe.online`
- Backend on VPS: `api.ominiscribe.online`
- DNS managed in Cloudflare zone: `ominiscribe.online`

Important architecture note:

- This backend currently uses an in-process queue (`asyncio.Queue`) for job processing.
- Run one backend process/replica only for now. Do not scale backend horizontally yet.

## 0. Final Hostname Layout

- `api.ominiscribe.online` -> VPS (FastAPI + Nginx)
- `app.ominiscribe.online` -> Vercel project (primary web)
- `app-cf.ominiscribe.online` -> Cloudflare Worker (backup web)
- `ominiscribe.online` -> optional redirect to `app.ominiscribe.online`
- `www.ominiscribe.online` -> optional redirect to `app.ominiscribe.online`

## 1. Cloudflare DNS Baseline

Create and keep these records in Cloudflare DNS:

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| A | `api` | `<YOUR_VPS_PUBLIC_IP>` | Proxied |
| CNAME | `app` | `cname.vercel-dns-0.com` | DNS only |

Optional records:

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| A | `@` | `76.76.21.21` | DNS only |
| CNAME | `www` | `cname.vercel-dns-0.com` | DNS only |

Notes:

- For Vercel domains, always run `vercel domains inspect <domain>` and use the exact records shown there.
- Keep Vercel hostnames as `DNS only` to avoid placing Cloudflare reverse proxy in front of Vercel.
- Cloudflare can still be your DNS provider without proxying Vercel traffic.

## 2. Deploy Backend to VPS (api.ominiscribe.online)

Assume Ubuntu 22.04/24.04 and repository path `/opt/WordFlow`.

### 2.1 Install packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx ffmpeg nodejs npm postgresql postgresql-contrib
```

### 2.2 Create service user and directories

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin wordflow || true
sudo mkdir -p /opt /srv/wordflow/tmp /srv/wordflow/storage
sudo chown -R wordflow:wordflow /srv/wordflow
```

### 2.3 Clone repository

```bash
cd /opt
sudo git clone https://github.com/Hululuistrue/WordFlow.git
sudo chown -R wordflow:wordflow /opt/WordFlow
```

If this repository is private, use SSH deploy key instead:

```bash
sudo -u wordflow mkdir -p /home/wordflow/.ssh
sudo -u wordflow ssh-keygen -t ed25519 -C "vps-wordflow" -f /home/wordflow/.ssh/id_ed25519_github
sudo -u wordflow cat /home/wordflow/.ssh/id_ed25519_github.pub
```

Then add the printed public key in GitHub:

1. Repository `Hululuistrue/WordFlow` -> Settings -> Deploy keys
2. Add key, enable read-only

Clone with SSH URL:

```bash
cd /opt
sudo -u wordflow git clone git@github.com:Hululuistrue/WordFlow.git
```

If you already cloned with HTTPS and want to switch to SSH:

```bash
cd /opt/WordFlow
sudo -u wordflow git remote set-url origin git@github.com:Hululuistrue/WordFlow.git
```

### 2.4 Python environment

```bash
cd /opt/WordFlow/backend
sudo -u wordflow python3 -m venv .venv
sudo -u wordflow /opt/WordFlow/backend/.venv/bin/pip install -r requirements.txt
sudo -u wordflow cp .env.example .env
```

### 2.5 PostgreSQL setup (local)

```bash
sudo -u postgres psql -c "CREATE USER wordflow WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE wordflow OWNER wordflow;"
```

### 2.6 Backend environment file

Edit `/opt/WordFlow/backend/.env`:

```env
APP_ENV=prod
APP_HOST=127.0.0.1
APP_PORT=8000
LOG_LEVEL=INFO

TEMP_DIR=/srv/wordflow/tmp
UPLOAD_STORAGE_DIR=/srv/wordflow/storage

ASR_MODEL_SIZE=base
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8

DATABASE_URL=postgresql+psycopg://wordflow:CHANGE_ME_STRONG_PASSWORD@127.0.0.1:5432/wordflow
DATABASE_ECHO=false
DATABASE_AUTO_CREATE_TABLES=false

TASK_POLL_INTERVAL_SECONDS=2
SUBTITLE_FETCH_TIMEOUT_SECONDS=180
YTDLP_JS_RUNTIMES=node
ALLOW_USER_SUPPLIED_COOKIES=false
```

Set file ownership:

```bash
sudo chown wordflow:wordflow /opt/WordFlow/backend/.env
sudo chmod 640 /opt/WordFlow/backend/.env
```

### 2.7 Database migration

```bash
cd /opt/WordFlow/backend
sudo -u wordflow /opt/WordFlow/backend/.venv/bin/alembic upgrade head
```

### 2.8 systemd service

Create `/etc/systemd/system/wordflow-backend.service`:

```ini
[Unit]
Description=WordFlow FastAPI Backend
After=network.target

[Service]
Type=simple
User=wordflow
Group=wordflow
WorkingDirectory=/opt/WordFlow/backend
EnvironmentFile=/opt/WordFlow/backend/.env
ExecStart=/opt/WordFlow/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wordflow-backend
sudo systemctl status wordflow-backend
```

### 2.9 Nginx reverse proxy for API

Create `/etc/nginx/sites-available/wordflow-api.conf`:

```nginx
server {
    listen 80;
    server_name api.ominiscribe.online;
    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/wordflow-api.conf /etc/nginx/sites-enabled/wordflow-api.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 2.10 HTTPS certificate on VPS origin

Install certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Issue cert:

```bash
sudo certbot --nginx -d api.ominiscribe.online
```

Cloudflare SSL mode:

- Set SSL/TLS mode to `Full (strict)` in Cloudflare after certificate is valid.

## 3. Deploy Frontend to Vercel (Primary)

Project settings:

- Repository: `Hululuistrue/WordFlow`
- Root Directory: `frontend`
- Framework: Next.js (auto-detected)
- Node.js: satisfy `>=20 <23` from project `package.json`

Environment variables (Production, Preview):

```env
NEXT_PUBLIC_API_BASE=https://api.ominiscribe.online
```

Add domains to Vercel project:

```bash
vercel domains add app.ominiscribe.online <vercel-project-name>
vercel domains inspect app.ominiscribe.online
```

If using apex on Vercel:

```bash
vercel domains add ominiscribe.online <vercel-project-name>
vercel domains inspect ominiscribe.online
```

Cloudflare DNS then must match `vercel domains inspect` output exactly.

## 4. Deploy Frontend to Cloudflare Workers (Backup)

This creates an independent backup frontend on `app-cf.ominiscribe.online`.

### 4.1 Prepare project for OpenNext Cloudflare adapter

```bash
cd /opt/WordFlow/frontend
npm install @opennextjs/cloudflare@latest
npm install --save-dev wrangler@latest
npx @opennextjs/cloudflare migrate
```

Set build-time API base:

```bash
echo "NEXT_PUBLIC_API_BASE=https://api.ominiscribe.online" | sudo -u wordflow tee /opt/WordFlow/frontend/.env.production
```

### 4.2 Build and deploy

```bash
cd /opt/WordFlow/frontend
npm run deploy
```

### 4.3 Bind custom domain in Cloudflare Workers

In Cloudflare dashboard:

1. Workers and Pages -> select deployed Worker
2. Settings -> Domains and Routes -> Add -> Custom Domain
3. Add `app-cf.ominiscribe.online`

Cloudflare creates DNS/certificate automatically for this Worker custom domain.
Do not create a manual `app-cf` DNS record before binding the custom domain.

## 5. Optional Redirect Rules

If you want users to always land on primary Vercel app:

- `ominiscribe.online` -> redirect to `https://app.ominiscribe.online`
- `www.ominiscribe.online` -> redirect to `https://app.ominiscribe.online`

You can implement redirects either:

- In Vercel project domain settings
- Or in Cloudflare Bulk Redirects

## 6. Validation Checklist

Backend:

- `curl -s https://api.ominiscribe.online/health` returns `{"status":"ok"}`
- `sudo systemctl status wordflow-backend` is active

Vercel frontend:

- `https://app.ominiscribe.online` loads
- Browser requests call `https://api.ominiscribe.online`

Cloudflare backup frontend:

- `https://app-cf.ominiscribe.online` loads
- API calls still target `https://api.ominiscribe.online`

Functional checks:

1. Upload file -> job queued/running/success
2. Transcript fetch/edit/export works
3. YouTube route works with current backend settings

## 7. Release and Update Workflow

### 7.1 Manual backend update on VPS

Use this when you want to update VPS manually:

```bash
cd /opt/WordFlow
sudo -u wordflow git pull --ff-only origin main
sudo -u wordflow /opt/WordFlow/backend/.venv/bin/pip install -r /opt/WordFlow/backend/requirements.txt
sudo -u wordflow /opt/WordFlow/backend/.venv/bin/alembic -c /opt/WordFlow/backend/alembic.ini upgrade head
sudo systemctl restart wordflow-backend
```

Frontend update (Vercel):

- Push to `main` -> Vercel auto-build/deploy

Frontend update (Cloudflare backup):

```bash
cd /opt/WordFlow/frontend
npm ci
npm run deploy
```

### 7.2 Auto-sync backend after GitHub push (recommended)

Goal:

- Push backend code to `main` on GitHub
- GitHub Actions SSH into VPS
- VPS runs `git pull --ff-only`, migration, and service restart automatically

#### Step A: Prepare VPS deploy user permissions

Create a deploy user:

```bash
sudo useradd --create-home --shell /bin/bash deploy || true
sudo usermod -aG wordflow deploy
```

Allow only limited service commands (least privilege):

Create `/etc/sudoers.d/deploy-wordflow`:

```text
deploy ALL=(root) NOPASSWD: /bin/systemctl restart wordflow-backend, /bin/systemctl is-active wordflow-backend
```

Validate sudoers:

```bash
sudo visudo -cf /etc/sudoers.d/deploy-wordflow
```

If your VPS uses `/usr/bin/systemctl`, update both sudoers and workflow command paths accordingly.

#### Step B: Add GitHub Secrets in repository

Repository -> Settings -> Secrets and variables -> Actions -> New repository secret:

- `VPS_HOST` = your VPS IP or domain
- `VPS_PORT` = `22`
- `VPS_USER` = `deploy`
- `VPS_SSH_KEY` = private key content for GitHub Actions -> VPS login

Note:

- This key is for Actions to access VPS.
- VPS still needs access to GitHub for `git pull` (use deploy key in section 2.3 if repository is private).

#### Step C: Add workflow file

Create `.github/workflows/deploy-backend.yml`:

```yaml
name: Deploy Backend To VPS

on:
  push:
    branches: [main]
    paths:
      - "backend/**"
      - ".github/workflows/deploy-backend.yml"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.VPS_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -p "${{ secrets.VPS_PORT }}" "${{ secrets.VPS_HOST }}" >> ~/.ssh/known_hosts

      - name: Deploy on VPS
        run: |
          ssh -p "${{ secrets.VPS_PORT }}" "${{ secrets.VPS_USER }}@${{ secrets.VPS_HOST }}" '
            set -e
            cd /opt/WordFlow
            git pull --ff-only origin main
            cd backend
            /opt/WordFlow/backend/.venv/bin/pip install -r requirements.txt
            /opt/WordFlow/backend/.venv/bin/alembic -c /opt/WordFlow/backend/alembic.ini upgrade head
            sudo /bin/systemctl restart wordflow-backend
            sudo /bin/systemctl is-active --quiet wordflow-backend
          '
```

#### Step D: First run validation

1. Commit and push workflow file.
2. In GitHub Actions tab, confirm workflow succeeds.
3. Verify API on VPS:

```bash
curl -s https://api.ominiscribe.online/health
```

4. Check backend service logs if needed:

```bash
sudo journalctl -u wordflow-backend -n 200 --no-pager
```

#### Step E: Ongoing usage

- Change backend code -> push to `main` -> VPS auto-sync runs.
- Avoid editing tracked files directly on VPS to keep `git pull --ff-only` reliable.

## 8. Security and Operations

- Keep `/opt/WordFlow/backend/.env` out of git.
- Rotate DB password and API secrets on schedule.
- Monitor logs:

```bash
sudo journalctl -u wordflow-backend -n 200 --no-pager
sudo tail -n 200 /var/log/nginx/access.log
sudo tail -n 200 /var/log/nginx/error.log
```

- Backup PostgreSQL daily (`pg_dump`) and verify restore regularly.
- Keep backend single process until job queue moves to shared infra (Redis/Celery/RQ).

## 9. References (Official Docs)

- Vercel custom domains with external DNS:
  - https://vercel.com/docs/domains/set-up-custom-domain
- Vercel on Cloudflare proxy guidance:
  - https://vercel.com/guides/using-cloudflare-with-vercel
- Vercel monorepo and root directory:
  - https://vercel.com/docs/monorepos
  - https://vercel.com/docs/builds/configure-a-build
- Cloudflare Workers Next.js guide:
  - https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/
- OpenNext Cloudflare existing Next.js setup:
  - https://opennext.js.org/cloudflare/get-started
- Cloudflare Workers custom domains:
  - https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Cloudflare DNS proxy status:
  - https://developers.cloudflare.com/dns/proxy-status/
- Cloudflare SSL mode Full (strict):
  - https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
- GitHub deploy keys:
  - https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- GitHub Actions secrets:
  - https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- GitHub Actions workflow syntax:
  - https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions
