# 💼 AI Job Search Assistant

A full-stack AI-powered job search tool that fetches **live jobs** from LinkedIn, Naukri.com,
and Google Jobs — with AI match scoring, auto-apply simulation, application tracker,
and Claude-powered cover letter generation.

---

## 📁 Project Structure

```
job_search_app/
│
├── backend/
│   ├── main.py              ← FastAPI server (job fetching, scoring, caching)
│   ├── requirements.txt     ← Python dependencies
│   └── .env                 ← Your config (API keys, CORS, cache TTL)
│
├── frontend/
│   └── index.html           ← Complete UI (no build step needed)
│
├── .vscode/
│   ├── launch.json          ← VS Code debugger config
│   └── extensions.json      ← Recommended extensions
│
├── start_windows.bat        ← One-click start for Windows
├── start_mac_linux.sh       ← One-click start for Mac/Linux
└── README.md                ← This file
```

---

## ⚡ Quick Start (3 steps)

### Step 1 — Open in VS Code
```
File → Open Folder → select the job_search_app folder
```

### Step 2 — Start the backend

**Option A: VS Code debugger (recommended)**
- Press `F5` or go to Run → Start Debugging → select "🚀 Start Backend API"

**Option B: Integrated terminal**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Option C: One-click script**
- Windows: double-click `start_windows.bat`
- Mac/Linux: `chmod +x start_mac_linux.sh && ./start_mac_linux.sh`

### Step 3 — Open the frontend
Open `frontend/index.html` in your browser:
- Right-click → Open with Live Server (if VS Code extension installed), **or**
- Just double-click the file in Explorer / Finder

✅ You're live! The app will automatically connect to `http://localhost:8000`.

---

## 🔑 Configuration (`.env`)

Edit `backend/.env`:

```env
# Optional: SerpAPI for richer Google Jobs results
# Free tier: 100 searches/month → https://serpapi.com
SERPAPI_KEY=your_key_here

# Allowed frontend origins (use * for local dev)
ALLOWED_ORIGINS=*

# Job cache lifetime in seconds (default 15 min)
CACHE_TTL=900
```

---

## 🌐 API Reference

Base URL: `http://localhost:8000`

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Status check |
| `/health` | GET | Health + cache info |
| `/jobs/search` | GET | Fetch & score live jobs |
| `/jobs/platforms` | GET | List supported platforms |
| `/cache` | DELETE | Clear job cache |
| `/docs` | GET | Interactive API docs (Swagger) |

### `/jobs/search` parameters

| Param | Required | Example |
|---|---|---|
| `keyword` | ✅ | `React Developer` |
| `location` | ✅ | `Pune` |
| `experience` | ❌ | `3-5 years` |
| `platforms` | ❌ | `linkedin,naukri,google` |
| `skills` | ❌ | `React,TypeScript,AWS` |
| `titles` | ❌ | `Senior Engineer,Tech Lead` |
| `serpapi_key` | ❌ | `abc123...` |

---

## 🧠 How AI Match Scoring Works

Every job is scored **0–99** based on:

| Factor | Points |
|---|---|
| Baseline | +50 |
| Skill overlap (your skills found in job description) | up to +30 |
| Title match (your target title matches job title) | up to +20 |

Colour coding in the UI:
- 🟢 **85%+** → Strong match
- 🟡 **70–84%** → Good match
- 🔴 **<70%** → Weak match

---

## 🔌 Platform Details

| Platform | Method | Rate limit | Auth needed? |
|---|---|---|---|
| LinkedIn | Guest HTML API | ~100/hour | None |
| Naukri.com | Public search API | ~200/hour | None |
| Google Jobs | SerpAPI (best quality) | 100/month free | API key |
| Google Jobs | Indeed fallback | ~50/hour | None |

---

## 🔧 VS Code Recommended Extensions

Install these for the best experience (prompted automatically):

| Extension | Purpose |
|---|---|
| **Python** (ms-python) | Python language support |
| **Pylance** | Fast Python intellisense |
| **Live Server** | Serve `index.html` with auto-reload |
| **Thunder Client** | Test API endpoints inside VS Code |

---

## 🚀 Features

- **Live job search** — real-time fetch from LinkedIn, Naukri, Google Jobs
- **AI match scoring** — each job scored against your skills and target titles
- **Auto-apply** — batch apply to all jobs above your match threshold
- **Application tracker** — track status (Applied → Shortlisted → Interview → Offer), export CSV
- **AI cover letters** — Claude-powered, tone-selectable, prefill from any job card
- **15-minute cache** — avoids hammering platforms on repeat searches
- **Profile persistence** — your profile, tracker and applied jobs saved in localStorage
- **API status indicator** — live backend health check in the sidebar

---

## 🛠 Troubleshooting

**Backend won't start**
```bash
# Make sure you're in the right folder
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**"API offline" shown in sidebar**
- Backend is not running — start it first (Step 2)
- Check port 8000 isn't blocked by firewall or used by another app

**No jobs returned**
- LinkedIn/Naukri may occasionally block scrapers — wait a few minutes and retry
- Try a different VPN or proxy for production use
- Add a SerpAPI key in Settings for more reliable Google Jobs results

**Cover letter fails**
- The app calls Anthropic's Claude API directly from the browser
- When running inside Claude.ai: works automatically (no key needed)
- When running standalone: add your Anthropic API key in Settings → Anthropic API

---

## 🏗 Production Deployment

```bash
# Install production server
pip install gunicorn

# Run with multiple workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

For production, also:
- Set `ALLOWED_ORIGINS` in `.env` to your frontend domain
- Use Redis instead of the in-memory `_cache` dict
- Add rotating proxies for scraping at scale
- Deploy frontend to Vercel/Netlify (just upload `index.html`)
- Deploy backend to Railway, Render, or any VPS

---

## 📝 License
MIT — free to use, modify and distribute.
