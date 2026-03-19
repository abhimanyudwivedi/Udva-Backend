# Udva — Architecture Reference

> **Product:** Udva — Rise above your competitors in AI search
> **Domain:** udva.io
> **Tagline:** Rise above your competitors in AI search
>
> **Purpose:** This file is the single source of truth for Udva's architecture.
> Paste it at the start of every Claude Code session to provide full context.
> Keep it updated as the codebase evolves.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Tech Stack](#2-tech-stack)
3. [Repository Structure](#3-repository-structure)
4. [Database Schema](#4-database-schema)
5. [Pillar 1 — AI Search Visibility Tracker](#5-pillar-1--ai-search-visibility-tracker)
6. [Pillar 2 — Social Listening](#6-pillar-2--social-listening)
7. [Pillar 3 — Engagement Engine](#7-pillar-3--engagement-engine)
8. [API Layer](#8-api-layer)
9. [Background Jobs (Celery)](#9-background-jobs-celery)
10. [Authentication & Billing](#10-authentication--billing)
11. [Infrastructure & Deployment](#11-infrastructure--deployment)
12. [Environment Variables](#12-environment-variables)
13. [Cost Assumptions](#13-cost-assumptions)
14. [Development Conventions](#14-development-conventions)

---

## 1. Product Overview

**Udva** (udva.io) is a three-pillar SaaS platform for AI search visibility and social monitoring. GEO stands for Generative Engine Optimization — the emerging discipline of making your brand visible and recommended by AI models like ChatGPT, Claude, Perplexity, and Gemini.

| Pillar | What it does | Key technology |
|--------|-------------|----------------|
| **AI Visibility Tracker** | Queries LLMs daily with brand prompts, parses responses, tracks brand mention scores over time | OpenAI, Anthropic, Google AI APIs |
| **Social Listening** | Crawls Reddit + Quora for keyword mentions, scores by AI-citation potential, fires alerts | PRAW, Serper.dev, Celery |
| **Engagement Engine** | Posts content into Reddit threads via a managed pool of aged accounts on behalf of customers | PRAW (multi-account), residential proxies, credit ledger |

**Target user:** Indie hackers, SaaS founders, agencies — anyone who wants to know if AI recommends their brand and where community conversations are shaping that.

**Positioning:** Udva helps you rise above competitors in AI search. Where CrowdReply starts at $99/month with limited features, Udva targets indie hackers and early-stage founders with more features at a lower price point.

---

## 2. Tech Stack

### Backend
| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Language | Python | 3.12 | Use `pyproject.toml` + `uv` for dependency management |
| API framework | FastAPI | latest | Async, typed, auto-generates OpenAPI docs |
| Data validation | Pydantic v2 | latest | Used for request/response models and settings |
| ORM | SQLAlchemy | 2.x async | Declarative models, async sessions |
| Migrations | Alembic | latest | One migration per schema change |
| Task queue | Celery | 5.x | With Redis broker and result backend |
| Scheduler | Celery Beat | bundled | Periodic tasks (crawls, LLM queries) |
| Cache / broker | Redis | 7.x | Celery broker + result store + rate-limit counters |
| Database | PostgreSQL | 16 | Primary data store |

### LLM Clients
| Provider | SDK | Model used |
|----------|-----|-----------|
| OpenAI | `openai` (official) | `gpt-4o` for queries, `gpt-4o-mini` for parsing |
| Anthropic | `anthropic` (official) | `claude-sonnet-4-6` for queries, `claude-haiku-4-5-20251001` for parsing |
| Google | `google-generativeai` | `gemini-2.5-flash` for queries |
| Perplexity | HTTP (requests) | `sonar-pro` for queries (optional, Growth+ plans) |

### Data Sources
| Source | Method | Library |
|--------|--------|---------|
| Reddit | Official API | `praw` 7.x |
| Quora | Google SERP (`site:quora.com`) | Serper.dev HTTP API |
| Facebook | Meta Graph API | `requests` (public pages only) |
| Google rank check | Serper.dev | HTTP API |

### Frontend
| Layer | Choice | Notes |
|-------|--------|-------|
| Framework | Next.js 14 (App Router) | Separate repo: `udva-frontend` |
| UI components | shadcn/ui + Tailwind CSS | |
| Charts | Recharts | Visibility score time-series |
| Auth | NextAuth.js + JWT | Reads tokens from FastAPI backend |

### Infrastructure
| Service | Provider | Notes |
|---------|----------|-------|
| Hosting | Railway | App server + workers + DB + Redis in one project |
| Email | Resend | Transactional alerts, 3K/day free |
| Payments | Stripe | Subscriptions + credit top-ups |
| Error tracking | Sentry (free tier) | Python + Next.js SDKs |
| DNS / SSL | Cloudflare | Free SSL, DDoS protection |

---

## 3. Repository Structure

```
udva-backend/                   # This repo (Python)
├── pyproject.toml              # Dependencies (managed with uv)
├── alembic.ini
├── alembic/
│   └── versions/               # One file per migration
├── app/
│   ├── main.py                 # FastAPI app init, router registration
│   ├── config.py               # Pydantic Settings — loads from env vars
│   ├── database.py             # Async SQLAlchemy engine + session factory
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── brand.py
│   │   ├── keyword.py
│   │   ├── query.py
│   │   ├── visibility_score.py
│   │   ├── citation_source.py
│   │   ├── mention.py
│   │   ├── campaign.py
│   │   └── credit_ledger.py
│   ├── schemas/                # Pydantic request/response schemas
│   │   ├── brand.py
│   │   ├── visibility.py
│   │   ├── mention.py
│   │   └── campaign.py
│   ├── routes/                 # FastAPI routers (one per domain)
│   │   ├── auth.py
│   │   ├── brands.py
│   │   ├── visibility.py
│   │   ├── listening.py
│   │   ├── campaigns.py
│   │   └── billing.py
│   ├── tasks/                  # Celery tasks (Pillar 1 + 2)
│   │   ├── __init__.py
│   │   ├── query_builder.py
│   │   ├── llm_dispatch.py
│   │   ├── response_parser.py
│   │   ├── score_writer.py
│   │   ├── citation_extractor.py
│   │   ├── competitor_diff.py
│   │   ├── rollup.py
│   │   ├── reddit_crawler.py
│   │   ├── quora_collector.py
│   │   ├── serp_ranker.py
│   │   ├── relevance_scorer.py
│   │   ├── deduplicator.py
│   │   └── alert_dispatcher.py
│   ├── engine/                 # Pillar 3 — Engagement Engine
│   │   ├── __init__.py
│   │   ├── account_manager.py
│   │   ├── proxy_manager.py
│   │   ├── post_scheduler.py
│   │   ├── post_executor.py
│   │   ├── upvote_engine.py
│   │   ├── stick_monitor.py
│   │   └── account_warmer.py
│   └── lib/                    # Shared utilities
│       ├── llm_clients.py      # Thin wrappers around each LLM SDK
│       ├── reddit_client.py    # PRAW singleton with auth
│       ├── serper_client.py    # Serper.dev HTTP wrapper
│       ├── email.py            # Resend integration
│       └── stripe_client.py   # Stripe webhook handler + billing helpers
├── celery_app.py               # Celery app init + beat schedule
├── tests/
│   ├── conftest.py
│   ├── test_llm_dispatch.py
│   ├── test_response_parser.py
│   ├── test_reddit_crawler.py
│   └── test_relevance_scorer.py
└── Dockerfile

udva-frontend/                  # Separate repo (Next.js)
├── app/
│   ├── (auth)/
│   ├── dashboard/
│   │   ├── visibility/
│   │   ├── listening/
│   │   └── campaigns/
│   └── settings/
├── components/
│   ├── charts/
│   └── ui/                     # shadcn/ui components
└── lib/
    └── api.ts                  # Typed API client (uses fetch)
```

---

## 4. Database Schema

### Core tables

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    hashed_pw   TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'trial',   -- trial | solo | indie | studio | agency
    stripe_customer_id TEXT,
    stripe_sub_id      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Brands (a user can own multiple brands per plan)
CREATE TABLE brands (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    domain      TEXT,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Tracked prompts (questions asked to LLMs)
CREATE TABLE queries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    prompt_text TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Competitor brands tracked alongside a brand
CREATE TABLE competitors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name        TEXT NOT NULL
);

-- Keywords for social listening
CREATE TABLE keywords (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    platform    TEXT NOT NULL DEFAULT 'reddit',  -- reddit | quora | facebook
    is_active   BOOLEAN DEFAULT TRUE
);

-- AI visibility scores (one row per query × model × day)
CREATE TABLE visibility_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id        UUID NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    brand_id        UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,      -- gpt-4o | claude-sonnet-4-6 | gemini-2.5-flash
    brand_mentioned BOOLEAN NOT NULL,
    mention_rank    INT,                -- 1 = first mention, NULL = not mentioned
    sentiment       TEXT,               -- positive | neutral | negative | NULL
    is_competitor   BOOLEAN DEFAULT FALSE,
    raw_response    TEXT,
    scored_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON visibility_scores (brand_id, scored_at DESC);
CREATE INDEX ON visibility_scores (query_id, model, scored_at DESC);

-- URLs that LLMs cited in responses
CREATE TABLE citation_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    url         TEXT NOT NULL,
    domain      TEXT NOT NULL,
    query_id    UUID REFERENCES queries(id),
    found_at    TIMESTAMPTZ DEFAULT now()
);

-- Social mentions (Reddit threads, Quora pages)
CREATE TABLE mentions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id        UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    keyword_id      UUID REFERENCES keywords(id),
    platform        TEXT NOT NULL,      -- reddit | quora | facebook
    url             TEXT NOT NULL,
    title           TEXT,
    content_snippet TEXT,
    author          TEXT,
    engagement      INT DEFAULT 0,      -- upvotes / score
    google_rank     INT,                -- 1–10 if on page 1, NULL otherwise
    relevance_score INT DEFAULT 0,      -- 0–100, computed by relevance_scorer
    url_hash        TEXT UNIQUE,        -- MD5(url + brand_id) for dedup
    found_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON mentions (brand_id, relevance_score DESC, found_at DESC);

-- Engagement campaigns (Pillar 3)
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id        UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    thread_url      TEXT NOT NULL,
    content         TEXT NOT NULL,
    post_type       TEXT NOT NULL,      -- comment | comment_with_link | post
    status          TEXT DEFAULT 'queued',  -- queued | posted | removed | refunded
    reddit_post_id  TEXT,               -- returned after posting
    upvote_count    INT DEFAULT 0,
    view_count      INT DEFAULT 0,
    credits_charged INT NOT NULL,
    account_id      UUID,               -- which account posted it
    posted_at       TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Credit ledger (Pillar 3)
CREATE TABLE credit_ledger (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id    UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    delta       INT NOT NULL,           -- positive = top-up, negative = spend
    reason      TEXT NOT NULL,          -- plan_credit | topup | comment | post | refund
    campaign_id UUID REFERENCES campaigns(id),
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Engagement accounts pool (Pillar 3, internal)
CREATE TABLE reddit_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        TEXT UNIQUE NOT NULL,
    encrypted_pw    TEXT NOT NULL,      -- AES-256 encrypted
    proxy_ip        TEXT,
    karma           INT DEFAULT 0,
    account_age_days INT DEFAULT 0,
    status          TEXT DEFAULT 'warming',  -- warming | active | banned | resting
    last_used_at    TIMESTAMPTZ,
    last_warmed_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. Pillar 1 — AI Search Visibility Tracker

### Flow

```
Celery Beat (daily, 6AM UTC)
    └── query_brand_visibility.delay(brand_id)
            └── query_builder.py
                    Loads active queries for brand
                    └── llm_dispatch.py
                            asyncio.gather() → 3 LLM calls in parallel
                            ├── OpenAI GPT-4o
                            ├── Claude Sonnet 4.6
                            └── Gemini 2.5 Flash
                    └── response_parser.py (per model response)
                            Calls GPT-4o-mini / Haiku 4.5
                            Returns: { brand_mentioned, rank, sentiment, cited_urls }
                    └── score_writer.py
                            INSERT INTO visibility_scores
                    └── citation_extractor.py
                            INSERT INTO citation_sources
```

### Key files

**`app/tasks/query_builder.py`**
```python
# Loads brand + queries from DB
# Returns list of { brand_name, prompt_text, query_id }
async def build_queries(brand_id: str) -> list[dict]:
    ...
```

**`app/tasks/llm_dispatch.py`**
```python
# Fan-out to all enabled models in parallel
# Returns list of { model, raw_response }
async def dispatch_to_llms(prompt: str, models: list[str]) -> list[dict]:
    results = await asyncio.gather(
        call_openai(prompt),
        call_claude(prompt),
        call_gemini(prompt),
        return_exceptions=True
    )
    return [r for r in results if not isinstance(r, Exception)]
```

**`app/tasks/response_parser.py`**
```python
# Sends raw LLM response to a cheap model for structured extraction
# SYSTEM PROMPT instructs: return only valid JSON, no preamble
# Returns: { brand_mentioned: bool, rank: int|null, sentiment: str, cited_urls: list[str] }
PARSER_SYSTEM_PROMPT = """
You are a structured data extractor. Given an AI model's response to a brand search query,
extract the following and return ONLY valid JSON with no markdown, no preamble:
{
  "brand_mentioned": true | false,
  "mention_rank": 1 (first brand mentioned) | 2 | null (not mentioned),
  "sentiment": "positive" | "neutral" | "negative" | null,
  "cited_urls": ["https://..."]
}
"""
```

**`app/tasks/competitor_diff.py`**
```python
# Runs same prompts for each competitor brand name
# Stored with is_competitor=True flag
# Enables "you vs competitor" chart on dashboard
```

### Celery Beat schedule entry
```python
# celery_app.py
app.conf.beat_schedule = {
    "daily-visibility-run": {
        "task": "app.tasks.llm_dispatch.run_all_brands",
        "schedule": crontab(hour=6, minute=0),   # 6AM UTC daily
    },
    "weekly-rollup": {
        "task": "app.tasks.rollup.compute_weekly_scores",
        "schedule": crontab(day_of_week=1, hour=2, minute=0),
    },
}
```

### Optimisation strategy
- **Batch API:** Non-urgent brands (all of them, since daily delay is fine) use OpenAI Batch API for 50% cost reduction
- **Prompt caching:** System prompt is identical per brand — prefix with `cache_control` for Anthropic (90% savings on repeated context)
- **Parser model:** Always use `gpt-4o-mini` or `claude-haiku-4-5-20251001` for parsing — never GPT-4o

---

## 6. Pillar 2 — Social Listening

### Flow

```
Celery Beat (every 6h for Studio/Agency, 24h for Solo/Indie)
    └── crawl_brand_keywords.delay(brand_id)
            ├── reddit_crawler.py
            │       PRAW search by keyword across subreddits
            │       → deduplicator.py (skip if url_hash exists)
            │       → serp_ranker.py (check Google rank via Serper)
            │       → relevance_scorer.py (0–100 score)
            │       → INSERT INTO mentions
            │
            ├── quora_collector.py
            │       Serper: site:quora.com + keyword
            │       → same dedup / rank / score pipeline
            │
            └── alert_dispatcher.py
                    For new mentions where relevance_score >= user.alert_threshold
                    → email via Resend
                    → Slack webhook POST (if configured)
```

### Key files

**`app/tasks/reddit_crawler.py`**
```python
import praw

# PRAW client is a singleton (see app/lib/reddit_client.py)
# Searches by keyword across relevant subreddits
# Returns list of { url, title, content_snippet, author, score, created_utc }
async def crawl_keyword(keyword: str, subreddits: list[str] = ["all"]) -> list[dict]:
    reddit = get_reddit_client()
    results = reddit.subreddit("+".join(subreddits)).search(
        keyword, sort="new", time_filter="week", limit=25
    )
    return [map_submission(s) for s in results]
```

**`app/tasks/relevance_scorer.py`**
```python
# Scoring weights (tunable):
# - keyword_match_exact:    +40 points
# - keyword_match_partial:  +20 points
# - google_rank_page1:      +30 points
# - engagement_high (>100): +20 points
# - engagement_medium:      +10 points
# - recency_24h:            +10 points
# - recency_week:           +5 points
# Cap at 100

def score_mention(mention: dict, keyword: str) -> int:
    score = 0
    if keyword.lower() in mention["title"].lower(): score += 40
    elif keyword.lower() in mention["content_snippet"].lower(): score += 20
    if mention.get("google_rank") and mention["google_rank"] <= 10: score += 30
    if mention["engagement"] > 100: score += 20
    elif mention["engagement"] > 20: score += 10
    hours_old = (now() - mention["created_at"]).total_seconds() / 3600
    if hours_old < 24: score += 10
    elif hours_old < 168: score += 5
    return min(score, 100)
```

**`app/tasks/deduplicator.py`**
```python
import hashlib

def make_url_hash(url: str, brand_id: str) -> str:
    return hashlib.md5(f"{url}:{brand_id}".encode()).hexdigest()

async def is_duplicate(url: str, brand_id: str, db) -> bool:
    h = make_url_hash(url, brand_id)
    return await db.scalar(select(exists().where(Mention.url_hash == h)))
```

**`app/tasks/serp_ranker.py`**
```python
# Calls Serper.dev with the thread URL as query to check Google ranking
# Returns rank (1–10) if found on page 1, else None
# Cost: $0.30 per 1K queries — very cheap

import httpx

async def get_google_rank(url: str) -> int | None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.SERPER_API_KEY},
            json={"q": url, "num": 10}
        )
    results = r.json().get("organic", [])
    for i, result in enumerate(results, 1):
        if url in result.get("link", ""):
            return i
    return None
```

---

## 7. Pillar 3 — Engagement Engine

> ⚠️ **Build after Pillars 1 + 2 are live and generating revenue.**  
> This pillar requires operational overhead (account management, proxies) and carries  
> platform ToS risk. Validate customer demand before investing build time.

### Account pool model

- Minimum viable pool: **50 Reddit accounts**
- Each account needs: separate proxy IP, karma ≥ 50, account age ≥ 30 days
- Account states: `warming → active → resting → banned`
- **Account warmer** (daily Celery job): each active account browses randomly, upvotes 2–3 posts — keeps accounts looking human

### Flow

```
Customer submits campaign (POST /campaigns)
    └── post_scheduler.py
            Selects best available account (highest karma, not recently used)
            Assigns proxy
            Queues post_executor task with randomised delay (15min–4hr jitter)
    └── post_executor.py
            PRAW with account credentials + proxy
            Submits comment or post
            Saves reddit_post_id to campaigns table
    └── upvote_engine.py (optional, if upvotes requested)
            Queues 3–10 upvote tasks from separate account pool
            Each upvote has 10–60 min delay between them
    └── stick_monitor.py (Celery beat, daily)
            Fetches each active campaign's post by reddit_post_id
            If deleted/removed: status = 'removed', trigger credit refund
```

### Key files

**`app/engine/account_manager.py`**
```python
# Selects best account for a posting task
# Avoids accounts used in last 4 hours
# Avoids accounts that have already posted in the target subreddit today
async def select_account(subreddit: str) -> RedditAccount | None:
    ...

# Marks account as 'resting' for 2h after each post
async def mark_used(account_id: str) -> None:
    ...
```

**`app/engine/proxy_manager.py`**
```python
# Each account has a dedicated residential proxy
# On connection failure: logs error, marks proxy as failed, alerts admin
# Proxy provider: Smartproxy or Bright Data (residential, $10–15/GB)

def get_proxy_for_account(account: RedditAccount) -> dict:
    return {
        "http": f"http://{account.proxy_ip}",
        "https": f"http://{account.proxy_ip}",
    }
```

**`app/engine/post_executor.py`**
```python
import praw

async def execute_post(campaign: Campaign, account: RedditAccount) -> str:
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        username=account.username,
        password=decrypt(account.encrypted_pw),
        user_agent=f"udva/1.0 by {account.username}",
        # proxy injected via requests session
    )
    subreddit = reddit.subreddit(extract_subreddit(campaign.thread_url))
    submission = reddit.submission(url=campaign.thread_url)

    if campaign.post_type in ("comment", "comment_with_link"):
        comment = submission.reply(campaign.content)
        return comment.id
    elif campaign.post_type == "post":
        post = subreddit.submit(title=campaign.title, selftext=campaign.content)
        return post.id
```

### Credit pricing
| Action | Credits charged | Your cost | Gross margin |
|--------|----------------|-----------|--------------|
| Comment | 1000 credits ($10) | ~$1.50 | ~$8.50 |
| Comment with link | 1500 credits ($15) | ~$2.00 | ~$13.00 |
| Post / thread | 2500 credits ($25) | ~$2.50 | ~$22.50 |

---

## 8. API Layer

### Route structure

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh

GET    /brands
POST   /brands
GET    /brands/{id}
PUT    /brands/{id}
DELETE /brands/{id}

GET    /brands/{id}/queries
POST   /brands/{id}/queries
DELETE /brands/{id}/queries/{query_id}

GET    /brands/{id}/keywords
POST   /brands/{id}/keywords
DELETE /brands/{id}/keywords/{keyword_id}

GET    /brands/{id}/visibility                  # time-series scores, all models
GET    /brands/{id}/visibility/compare          # brand vs competitors
GET    /brands/{id}/visibility/citations        # citation sources

GET    /brands/{id}/mentions                    # paginated mention feed
GET    /brands/{id}/mentions/{id}
POST   /brands/{id}/mentions/search             # ad-hoc single search

GET    /brands/{id}/campaigns
POST   /brands/{id}/campaigns                   # submit engagement order
GET    /brands/{id}/campaigns/{id}
GET    /brands/{id}/credits                     # current balance

POST   /billing/webhook                         # Stripe webhook (no auth)
POST   /billing/topup                           # purchase additional credits

GET    /settings
PUT    /settings                                # alert threshold, Slack webhook
```

### Shared request/response conventions
- All list endpoints: paginated with `?page=1&limit=20`
- All timestamps: ISO 8601, UTC
- Errors: `{ "detail": "message" }` (FastAPI default)
- Auth: Bearer JWT in `Authorization` header

---

## 9. Background Jobs (Celery)

### celery_app.py structure

```python
from celery import Celery
from celery.schedules import crontab

app = Celery("udva", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

app.conf.beat_schedule = {
    # Pillar 1 — runs every brand daily
    "run-visibility-tracker": {
        "task": "app.tasks.llm_dispatch.run_all_active_brands",
        "schedule": crontab(hour=6, minute=0),
    },
    # Pillar 1 — weekly rollup
    "weekly-score-rollup": {
        "task": "app.tasks.rollup.compute_weekly",
        "schedule": crontab(day_of_week=1, hour=3, minute=0),
    },
    # Pillar 2 — 6-hour crawl (Studio/Agency plans)
    "crawl-keywords-6h": {
        "task": "app.tasks.reddit_crawler.crawl_active_brands",
        "schedule": crontab(minute=0, hour="*/6"),
        "kwargs": {"plan_tier": ["studio", "agency"]},
    },
    # Pillar 2 — 24-hour crawl (Solo/Indie plans)
    "crawl-keywords-24h": {
        "task": "app.tasks.reddit_crawler.crawl_active_brands",
        "schedule": crontab(hour=8, minute=0),
        "kwargs": {"plan_tier": ["solo", "indie"]},
    },
    # Pillar 3 — account warming (daily)
    "warm-accounts": {
        "task": "app.engine.account_warmer.warm_all_accounts",
        "schedule": crontab(hour=2, minute=30),
    },
    # Pillar 3 — stick rate monitor (daily)
    "check-campaign-stick": {
        "task": "app.engine.stick_monitor.check_all_active_campaigns",
        "schedule": crontab(hour=4, minute=0),
    },
}

app.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
    "app.engine.*": {"queue": "engine"},   # separate queue for Pillar 3
}
```

### Retry strategy (all tasks)
```python
@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,       # 1 minute between retries
    autoretry_for=(Exception,),
    retry_backoff=True,           # exponential backoff
)
def my_task(self, ...):
    ...
```

---

## 10. Authentication & Billing

### Auth flow
1. User registers → password hashed with `bcrypt`
2. Login → returns `access_token` (JWT, 30min) + `refresh_token` (7 days)
3. All protected routes require `Authorization: Bearer <token>`
4. Token carries: `user_id`, `plan`, `exp`

### Stripe plan mapping
| Plan slug | Stripe Price ID | Monthly USD | Brands | LLM models | Keywords |
|-----------|----------------|-------------|--------|-----------|----------|
| `trial` | — | $0 (7 days) | 1 | 2 | 10 |
| `solo` | `price_solo` | $29 | 1 | 2 | 10 |
| `indie` | `price_indie` | $49 | 1 | 3 | 20 |
| `studio` | `price_studio` | $89 | 3 | 4 | 75 |
| `agency` | `price_agency` | $149 | 10 | 5 | 200 |

### Stripe webhook events handled
- `customer.subscription.created` → activate plan, grant credits
- `customer.subscription.updated` → upgrade/downgrade
- `customer.subscription.deleted` → downgrade to free/locked
- `invoice.payment_succeeded` → grant monthly credits
- `invoice.payment_failed` → send failed payment email
- `checkout.session.completed` → one-time credit top-up

---

## 11. Infrastructure & Deployment

### Railway project layout
```
udva (Railway project)
├── api          ← FastAPI app    (Dockerfile, PORT=8000)
├── worker       ← Celery worker  (same Dockerfile, CMD=celery worker)
├── beat         ← Celery beat    (same Dockerfile, CMD=celery beat)
├── postgres     ← Railway managed PostgreSQL 16
└── redis        ← Railway managed Redis 7
```

### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync --frozen
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Deployment trigger
- Push to `main` → Railway auto-deploys API, worker, and beat
- Alembic migrations run automatically on deploy via `railway run alembic upgrade head`

### Scaling notes
- Celery worker: set `--concurrency=4` initially (4 parallel tasks)
- Redis: Railway managed, upgrade to dedicated when queue depth > 1,000 jobs
- Postgres: connection pooling via `asyncpg` pool (max 10 connections per worker)

---

## 12. Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/udva

# Redis
REDIS_URL=redis://host:6379/0

# LLM APIs
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_API_KEY=AIza...
PERPLEXITY_API_KEY=pplx-...          # optional

# Data source APIs
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=udva/1.0
SERPER_API_KEY=...

# Auth
JWT_SECRET_KEY=...                    # 64-char random hex
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Payments
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_SOLO=price_...
STRIPE_PRICE_INDIE=price_...
STRIPE_PRICE_STUDIO=price_...
STRIPE_PRICE_AGENCY=price_...

# Email
RESEND_API_KEY=re_...
EMAIL_FROM=shipfast.pvt@gmail.com

# Encryption (for storing Reddit account passwords)
ACCOUNT_ENCRYPTION_KEY=...           # 32-byte AES key, base64-encoded

# Sentry
SENTRY_DSN=https://...

# App
ENVIRONMENT=production               # development | production
DEBUG=false
```

---

## 13. Cost Assumptions

| Item | Cost / month (10 customers) | Cost / month (50 customers) |
|------|-----------------------------|-----------------------------|
| Railway (API + worker + DB + Redis) | $35–50 | $80–120 |
| LLM APIs (batch + caching, 3 models) | $100–140 | $500–700 |
| Reddit API | $0–8 | $20–50 |
| Serper.dev (SERP checks) | $2 | $10 |
| Email (Resend) | $0 (free tier) | $0–20 |
| Engagement account proxies | $0 (not yet built) | $50–80 |
| **Total** | **~$150–200** | **~$700–1,000** |

**Revenue at $49/mo average:**
- 10 customers → $490 revenue → ~$290–340 margin (60–70%)
- 50 customers → $2,450+ revenue → ~$1,500–1,800 margin (65–75%)

---

## 14. Development Conventions

### Code style
- Formatter: `ruff format` (replaces Black)
- Linter: `ruff check`
- Type checking: `mypy` (strict mode)
- All async functions: use `async def` + `await`
- No bare `except:` — always catch specific exceptions

### Git conventions
- Branch naming: `feature/pillar1-llm-dispatch`, `fix/celery-beat-cron`
- One PR per feature — keep diffs reviewable
- Squash merge to `main`
- Never commit secrets — use `.env` (gitignored) locally, Railway env vars in production

### Testing
- Framework: `pytest` + `pytest-asyncio`
- Mock all external API calls in tests (`unittest.mock` or `respx` for httpx)
- Minimum coverage targets: 80% on `tasks/`, 70% on `engine/`
- Run before every merge: `pytest tests/ -v --tb=short`

### Claude Code session start template
```
Read ARCHITECTURE.md first.

Current task: [describe the specific module you're building]
Current file: [path/to/file.py]

Relevant models: [list the SQLAlchemy models involved]
Relevant env vars: [list what's needed]

Build [X] with:
- Async functions throughout
- Full type hints
- Docstrings on public functions
- Error handling with specific exception types
- pytest tests in tests/test_[module].py
```

---

*Last updated: March 2026*  
*Product: Udva · Domain: udva.io*  
*Stack: Python 3.12 · FastAPI · Celery · PostgreSQL · Redis · Railway*