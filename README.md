# Transcript Pro (V2)

Public-facing hybrid product skeleton:
- YouTube OAuth route (authorized videos)
- Upload + ASR route (worker integration pending)
- Unified V2 API + typed frontend SDK

## Structure
- `backend/`: FastAPI backend
- `frontend/`: Next.js frontend
- `docs/openapi-v2-draft.yaml`: API contract draft
- `docs/V2-PRD-public-hybrid.md`: V2 PRD
- `docs/V2-Architecture-DB-API.md`: architecture and schema draft

## Run Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
For upload transcription, install ASR dependencies from `requirements.txt` (includes `faster-whisper`).

## Database Migration (Alembic)
```bash
cd backend
alembic upgrade head
```

Default local DB in `.env`:
```bash
DATABASE_URL=sqlite:///./app.db
```

## Run Frontend
```bash
cd frontend
npm.cmd install
npm.cmd run dev
```

If needed:
```bash
set NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Test
```bash
cd backend
python -m pytest -q
```

## V2 Entrypoints
- Backend router: `backend/app/api/v2/router.py`
- Backend schemas: `backend/app/api/v2/schemas.py`
- Frontend SDK: `frontend/lib/api/v2/`

## How To Use (Current UI)
1. Open frontend and click `Run Upload -> Job -> Transcript -> Export` to test upload flow.
2. Paste a YouTube URL and click `Run YouTube URL -> Job` to test YouTube job flow.
3. Use `Init YouTube OAuth` to fetch OAuth connect URL (integration stub).

## Notes
- V2 backend now uses SQLAlchemy persistence (SQLite local / PostgreSQL-ready).
- `POST /v2/jobs` now enqueues async processing (`queued -> running -> success/failed`).
- `youtube_oauth` jobs now attempt real subtitle fetching via `yt-dlp`.
- `upload` jobs now run ASR transcription through `faster-whisper` (requires model download on first run).
- User-supplied `cookies.txt` is disabled by default. To enable advanced cookies mode:
  - `ALLOW_USER_SUPPLIED_COOKIES=true`
  - Optional limit: `YOUTUBE_COOKIES_MAX_CHARS=200000`
  - Restart backend after `.env` update.
  - Frontend accepts Netscape `cookies.txt` and common JSON cookie exports (auto-converted server-side).
