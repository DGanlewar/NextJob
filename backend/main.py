"""
AI Job Search Backend — main.py
FastAPI server fetching live jobs from LinkedIn, Naukri, and Google Jobs
with timeframe filtering: 24h, 3d, 1w, 1m, any
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import re
import time
import hashlib
import os
from typing import Optional
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Job Search API",
    version="1.1.0",
    description="Live job fetching from LinkedIn, Naukri & Google Jobs with timeframe filtering",
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))

def cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires"]:
        return e["data"]
    return None

def cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires": time.time() + ttl}

def make_id(source: str, title: str, company: str) -> str:
    return hashlib.md5(f"{source}:{title}:{company}".encode()).hexdigest()[:12]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Timeframe helpers ──────────────────────────────────────────────────────────
TIMEFRAME_DAYS = {
    "24h": 1,
    "3d":  3,
    "1w":  7,
    "1m":  30,
    "any": None,   # no filter
}

# Per-platform URL param (days) used when fetching
LINKEDIN_TIMEFRAME = {
    "24h": "r86400",    # 24 hours  (seconds)
    "3d":  "r259200",   # 3 days
    "1w":  "r604800",   # 7 days
    "1m":  "r2592000",  # 30 days
    "any": "",
}
INDEED_FROMAGE = {          # "fromage" = days old
    "24h": "1",
    "3d":  "3",
    "1w":  "7",
    "1m":  "30",
    "any": "",
}
NAUKRI_FRESHNESS = {        # Naukri freshness param
    "24h": "1",
    "3d":  "3",
    "1w":  "7",
    "1m":  "30",
    "any": "",
}


def parse_posted_date(raw: str) -> Optional[datetime]:
    """Try to parse an ISO date string; return None if unparseable."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def fmt_posted(raw: str) -> str:
    """Human-readable posted label."""
    if not raw:
        return "Recently"
    dt = parse_posted_date(raw)
    if not dt:
        return raw[:10] if len(raw) >= 10 else raw
    delta = (datetime.utcnow() - dt).days
    if delta == 0:  return "Today"
    if delta == 1:  return "1d ago"
    if delta < 7:   return f"{delta}d ago"
    if delta < 30:  return f"{delta // 7}w ago"
    return f"{delta // 30}mo ago"


def posted_days_ago(raw: str) -> Optional[int]:
    """Return how many days ago the job was posted (None if unknown)."""
    dt = parse_posted_date(raw)
    if dt is None:
        return None
    return (datetime.utcnow() - dt).days


def within_timeframe(posted_raw: str, timeframe: str) -> bool:
    """Return True if the job falls within the selected timeframe."""
    max_days = TIMEFRAME_DAYS.get(timeframe)
    if max_days is None:          # "any" → no filter
        return True
    days = posted_days_ago(posted_raw)
    if days is None:              # unknown date → include it (benefit of doubt)
        return True
    return days <= max_days


# ── Match scoring ──────────────────────────────────────────────────────────────
def compute_match(job: dict, skills: list, titles: list) -> int:
    score = 50
    text  = f"{job.get('title','')} {job.get('description','')} {' '.join(job.get('skills',[]))}".lower()
    if skills:
        hits   = sum(1 for s in skills if s.strip().lower() in text)
        score += int((hits / len(skills)) * 30)
    if titles:
        if any(t.strip().lower() in job.get("title","").lower() for t in titles):
            score += 20
    return min(score, 99)


# ── LinkedIn ───────────────────────────────────────────────────────────────────
async def fetch_linkedin(keyword: str, location: str, timeframe: str, client: httpx.AsyncClient) -> list:
    key = f"li:{keyword}:{location}:{timeframe}"
    if (c := cache_get(key)): return c
    jobs = []
    try:
        kw  = keyword.replace(" ", "%20")
        loc = location.replace(" ", "%20")
        tf  = LINKEDIN_TIMEFRAME.get(timeframe, "")
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={kw}&location={loc}&start=0&count=25"
            + (f"&f_TPR={tf}" if tf else "")
        )
        r = await client.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            for card in soup.find_all("li"):
                t  = card.find("h3", class_=re.compile("base-search-card__title"))
                co = card.find("h4", class_=re.compile("base-search-card__subtitle"))
                lo = card.find("span", class_=re.compile("job-search-card__location"))
                a  = card.find("a", class_=re.compile("base-card__full-link"))
                tm = card.find("time")
                if not t: continue
                raw_date = tm.get("datetime", "") if tm else ""
                jobs.append({
                    "id":            make_id("li", t.get_text(strip=True), co.get_text(strip=True) if co else ""),
                    "title":         t.get_text(strip=True),
                    "company":       co.get_text(strip=True) if co else "Unknown",
                    "location":      lo.get_text(strip=True) if lo else location,
                    "platform":      "LinkedIn",
                    "platform_code": "li",
                    "link":          a["href"].split("?")[0] if a else "https://linkedin.com/jobs",
                    "posted_raw":    raw_date,
                    "posted":        fmt_posted(raw_date),
                    "salary":        "Not listed",
                    "type":          "Full-time",
                    "description":   "",
                    "skills":        [],
                    "match":         0,
                })
        logger.info(f"LinkedIn [{timeframe}] → {len(jobs)} jobs")
    except Exception as e:
        logger.warning(f"LinkedIn error: {e}")
    cache_set(key, jobs)
    return jobs


# ── Naukri ─────────────────────────────────────────────────────────────────────
async def fetch_naukri(keyword: str, location: str, experience: str, timeframe: str, client: httpx.AsyncClient) -> list:
    key = f"nk:{keyword}:{location}:{experience}:{timeframe}"
    if (c := cache_get(key)): return c
    jobs = []
    exp_map = {"0-1 years":"0","1-3 years":"1","3-5 years":"3","5-10 years":"5","10+ years":"10"}
    exp_val = exp_map.get(experience, "3")
    fresh   = NAUKRI_FRESHNESS.get(timeframe, "")
    try:
        params = {
            "noOfResults": 25, "urlType": "search_by_keyword", "searchType": "adv",
            "keyword": keyword, "location": location, "experience": exp_val,
            "k": keyword, "l": location, "nk": "v2", "src": "jobsearchDesk",
        }
        if fresh:
            params["jobAge"] = fresh      # Naukri freshness filter
        headers = {
            **HEADERS, "appid": "109", "systemid": "109",
            "Referer": f"https://www.naukri.com/{keyword.lower().replace(' ','-')}-jobs",
        }
        r = await client.get("https://www.naukri.com/jobapi/v3/search",
                             params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            for j in r.json().get("jobDetails", [])[:20]:
                salary, loc_label = "Not listed", location
                for p in j.get("placeholders", []):
                    if p.get("type") == "salary":   salary    = p.get("label", "Not listed")
                    if p.get("type") == "location": loc_label = p.get("label", location)
                skills   = [s.get("label","") for s in j.get("tagsAndSkills",[]) if s.get("label")]
                raw_date = j.get("createdDate","")
                jobs.append({
                    "id":            make_id("nk", j.get("title",""), j.get("companyName","")),
                    "title":         j.get("title",""),
                    "company":       j.get("companyName","Unknown"),
                    "location":      loc_label,
                    "platform":      "Naukri",
                    "platform_code": "nk",
                    "link":          j.get("jdURL","https://naukri.com"),
                    "posted_raw":    raw_date,
                    "posted":        fmt_posted(raw_date),
                    "salary":        salary,
                    "type":          j.get("jobType","Full-time"),
                    "description":   j.get("jobDescription","")[:400],
                    "skills":        skills[:6],
                    "match":         0,
                })
        logger.info(f"Naukri [{timeframe}] → {len(jobs)} jobs")
    except Exception as e:
        logger.warning(f"Naukri error: {e}")
    cache_set(key, jobs)
    return jobs


# ── Google Jobs ────────────────────────────────────────────────────────────────
async def fetch_google_jobs(keyword: str, location: str, timeframe: str,
                             client: httpx.AsyncClient, serpapi_key: Optional[str] = None) -> list:
    key = f"gg:{keyword}:{location}:{timeframe}"
    if (c := cache_get(key)): return c
    jobs = []

    # Option A: SerpAPI
    if serpapi_key:
        try:
            chips_map = {"24h": "date_posted:today", "3d": "date_posted:3days",
                         "1w": "date_posted:week",   "1m": "date_posted:month"}
            params = {
                "engine": "google_jobs", "q": f"{keyword} {location}",
                "hl": "en", "gl": "in", "api_key": serpapi_key,
            }
            chip = chips_map.get(timeframe)
            if chip:
                params["chips"] = chip
            r = await client.get("https://serpapi.com/search.json", timeout=15, params=params)
            if r.status_code == 200:
                for j in r.json().get("jobs_results", [])[:20]:
                    ext      = j.get("detected_extensions", {})
                    raw_date = ext.get("posted_at", "")
                    jobs.append({
                        "id":            make_id("gg", j.get("title",""), j.get("company_name","")),
                        "title":         j.get("title",""),
                        "company":       j.get("company_name","Unknown"),
                        "location":      j.get("location", location),
                        "platform":      "Google Jobs",
                        "platform_code": "gg",
                        "link":          j.get("share_link","https://jobs.google.com"),
                        "posted_raw":    raw_date,
                        "posted":        fmt_posted(raw_date),
                        "salary":        ext.get("salary","Not listed"),
                        "type":          ext.get("schedule_type","Full-time"),
                        "description":   j.get("description","")[:400],
                        "skills":        [],
                        "match":         0,
                    })
            logger.info(f"Google Jobs/SerpAPI [{timeframe}] → {len(jobs)} jobs")
        except Exception as e:
            logger.warning(f"SerpAPI error: {e}")

    # Option B: Indeed fallback
    if not jobs:
        try:
            fromage = INDEED_FROMAGE.get(timeframe, "")
            kw  = keyword.replace(" ", "+")
            loc = location.replace(" ", "+")
            url = f"https://www.indeed.com/jobs?q={kw}&l={loc}" + (f"&fromage={fromage}" if fromage else "")
            r = await client.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                for card in soup.find_all("div", class_=re.compile("job_seen_beacon")):
                    t   = card.find("h2", class_=re.compile("jobTitle"))
                    co  = card.find("span", {"data-testid": "company-name"})
                    lo  = card.find("div",  {"data-testid": "text-location"})
                    sal = card.find("div",  {"data-testid": "attribute_snippet_testid"})
                    a   = card.find("a", id=re.compile("job_"))
                    if not t: continue
                    href = a["href"] if a and a.get("href") else ""
                    jobs.append({
                        "id":            make_id("gg", t.get_text(strip=True), co.get_text(strip=True) if co else ""),
                        "title":         t.get_text(strip=True).replace("new","").strip(),
                        "company":       co.get_text(strip=True) if co else "Unknown",
                        "location":      lo.get_text(strip=True) if lo else location,
                        "platform":      "Google Jobs",
                        "platform_code": "gg",
                        "link":          f"https://indeed.com{href}" if href.startswith("/") else href or "https://indeed.com",
                        "posted_raw":    "",
                        "posted":        "Recent",
                        "salary":        sal.get_text(strip=True) if sal else "Not listed",
                        "type":          "Full-time",
                        "description":   "",
                        "skills":        [],
                        "match":         0,
                    })
            logger.info(f"Google Jobs/Indeed [{timeframe}] → {len(jobs)} jobs")
        except Exception as e:
            logger.warning(f"Indeed fallback error: {e}")

    cache_set(key, jobs)
    return jobs


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "running", "docs": "/docs", "version": "1.1.0"}

@app.get("/health")
def health():
    return {"status": "ok", "cache_entries": len(_cache), "timestamp": datetime.utcnow().isoformat()}

@app.get("/jobs/search")
async def search_jobs(
    keyword:     str           = Query(...,      description="Job title or skill"),
    location:    str           = Query("India",  description="City or Remote"),
    experience:  str           = Query("3-5 years"),
    platforms:   str           = Query("linkedin,naukri,google"),
    skills:      str           = Query("",       description="Comma-separated skills for scoring"),
    titles:      str           = Query("",       description="Comma-separated target titles"),
    timeframe:   str           = Query("1w",     description="24h | 3d | 1w | 1m | any"),
    serpapi_key: Optional[str] = Query(None,     description="SerpAPI key (optional)"),
):
    """
    Fetch and score live jobs.
    timeframe values:
      24h  → posted in last 24 hours
      3d   → posted in last 3 days
      1w   → posted this week (default)
      1m   → posted this month
      any  → no date filter
    """
    if timeframe not in TIMEFRAME_DAYS:
        timeframe = "1w"

    serpapi_key   = serpapi_key or os.getenv("SERPAPI_KEY") or None
    platform_list = [p.strip().lower() for p in platforms.split(",")]
    user_skills   = [s.strip() for s in skills.split(",") if s.strip()]
    user_titles   = [t.strip() for t in titles.split(",") if t.strip()]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            fetch_linkedin(keyword, location, timeframe, client)
                if "linkedin" in platform_list else asyncio.sleep(0),
            fetch_naukri(keyword, location, experience, timeframe, client)
                if "naukri" in platform_list else asyncio.sleep(0),
            fetch_google_jobs(keyword, location, timeframe, client, serpapi_key)
                if "google" in platform_list else asyncio.sleep(0),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs, seen = [], set()
    skipped_by_date = 0

    for r in results:
        if not isinstance(r, list):
            continue
        for j in r:
            if j["id"] in seen:
                continue
            # ── Timeframe post-filter (catches anything the platform param missed) ──
            if not within_timeframe(j.get("posted_raw", ""), timeframe):
                skipped_by_date += 1
                continue
            seen.add(j["id"])
            j["match"] = compute_match(j, user_skills, user_titles)
            all_jobs.append(j)

    all_jobs.sort(key=lambda x: x["match"], reverse=True)

    logger.info(f"Returning {len(all_jobs)} jobs (skipped {skipped_by_date} outside [{timeframe}])")

    return {
        "total":           len(all_jobs),
        "skipped_by_date": skipped_by_date,
        "timeframe":       timeframe,
        "keyword":         keyword,
        "location":        location,
        "platforms":       platform_list,
        "jobs":            all_jobs,
        "fetched_at":      datetime.utcnow().isoformat(),
    }

@app.get("/jobs/timeframes")
def get_timeframes():
    return {"timeframes": [
        {"id": "24h", "label": "Last 24 hours"},
        {"id": "3d",  "label": "Last 3 days"},
        {"id": "1w",  "label": "This week"},
        {"id": "1m",  "label": "This month"},
        {"id": "any", "label": "Any time"},
    ]}

@app.get("/jobs/platforms")
def get_platforms():
    return {"platforms": [
        {"id": "linkedin", "name": "LinkedIn",    "code": "li", "color": "#0A66C2"},
        {"id": "naukri",   "name": "Naukri.com",  "code": "nk", "color": "#FF7555"},
        {"id": "google",   "name": "Google Jobs", "code": "gg", "color": "#4285F4"},
    ]}

@app.delete("/cache")
def clear_cache():
    _cache.clear()
    return {"message": "Cache cleared"}
