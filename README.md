# News App
# AI News Aggregator

The backend collects and enriches AI, technology, and Indian politics news into MongoDB Atlas. The Vite frontend provides search, filtering, sorting, pagination, and direct publisher links.

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Configure MongoDB, provider, and Gemini settings in `backend/.env`. Create a MongoDB Atlas cluster, database user, and network access rule, then copy the Python driver connection string into `MONGODB_URI`. Run `POST http://127.0.0.1:8000/admin/ingest` once to populate the database.

## Frontend

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_BASE_URL` in `frontend/.env` when the backend is hosted elsewhere.

## One-command startup


## Vercel deployment

Deploy the backend and frontend as separate Vercel projects from this repository:

1. Create a Vercel project with **Root Directory** set to `backend`. Vercel will use `api/index.py` as the FastAPI entry point.
2. Add `MONGODB_URI`, `MONGODB_DATABASE`, `NEWSDATA_API_KEY`, `GUARDIAN_API_KEY`, `GEMINI_API_KEY`, and `GEMINI_MODEL` in the backend project's Environment Variables.
3. Create a second Vercel project with **Root Directory** set to `frontend`.
4. Set `VITE_API_BASE_URL` in the frontend project's Environment Variables to the deployed backend URL, then redeploy.

Do not commit either `.env` file. The root `.gitignore` excludes secrets, virtual environments, dependency folders, build output, caches, logs, and Vercel metadata.
From the project root, start both services in separate PowerShell windows:

```powershell
.\run.ps1
```

The dashboard also includes **Settings > API Configuration**, where you can change or test the backend URL. The saved value is kept in browser localStorage; reset it to return to `http://localhost:8000`. For a deployed frontend, set `VITE_API_BASE_URL` in `frontend/.env` before building.
## Relevance filtering

Ingestion first resolves Google News redirect URLs, normalizes and deduplicates articles, and applies local keyword rules. Clearly irrelevant articles are discarded before storage. Only ambiguous candidates are sent to Gemini for structured category, relevance, importance, summary, and impact analysis. Gemini is called through its HTTP API, so no separate Gemini SDK is required.
