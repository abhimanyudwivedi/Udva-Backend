"""Celery application — named 'udva', full beat schedule, task routing."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Celery(
    "udva",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        # Pillar 1 — AI Visibility Tracker
        "app.tasks.query_builder",
        "app.tasks.llm_dispatch",
        "app.tasks.response_parser",
        "app.tasks.score_writer",
        "app.tasks.citation_extractor",
        "app.tasks.competitor_diff",
        "app.tasks.rollup",
        # Pillar 2 — Social Listening
        "app.tasks.reddit_crawler",
        "app.tasks.quora_collector",
        "app.tasks.serp_ranker",
        "app.tasks.relevance_scorer",
        "app.tasks.deduplicator",
        "app.tasks.alert_dispatcher",
        # Pillar 3 — Engagement Engine (not yet implemented)
        # "app.engine.account_warmer",
        # "app.engine.stick_monitor",
        # "app.engine.post_executor",
    ],
)

# ---------------------------------------------------------------------------
# Serialisation & timezone
# ---------------------------------------------------------------------------
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------------
# Beat schedule (periodic tasks)
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    # ------------------------------------------------------------------
    # Pillar 1 — runs every brand daily at 6AM UTC
    # ------------------------------------------------------------------
    "run-visibility-tracker": {
        "task": "app.tasks.llm_dispatch.run_all_active_brands",
        "schedule": crontab(hour=6, minute=0),
    },
    # Pillar 1 — weekly score rollup (Monday 3AM UTC)
    "weekly-score-rollup": {
        "task": "app.tasks.rollup.compute_weekly_task",
        "schedule": crontab(day_of_week=1, hour=3, minute=0),
    },
    # ------------------------------------------------------------------
    # Pillar 2 — 6-hour keyword crawl for Studio / Agency plans
    # ------------------------------------------------------------------
    "crawl-keywords-6h": {
        "task": "app.tasks.reddit_crawler.crawl_active_brands",
        "schedule": crontab(minute=0, hour="*/6"),
        "kwargs": {"plan_tier": ["studio", "agency"]},
    },
    # Pillar 2 — 24-hour keyword crawl for Solo / Indie plans (8AM UTC)
    "crawl-keywords-24h": {
        "task": "app.tasks.reddit_crawler.crawl_active_brands",
        "schedule": crontab(hour=8, minute=0),
        "kwargs": {"plan_tier": ["solo", "indie"]},
    },
    # Pillar 3 — not yet implemented
    # "warm-accounts": {
    #     "task": "app.engine.account_warmer.warm_all_accounts",
    #     "schedule": crontab(hour=2, minute=30),
    # },
    # "check-campaign-stick": {
    #     "task": "app.engine.stick_monitor.check_all_active_campaigns",
    #     "schedule": crontab(hour=4, minute=0),
    # },
}

# ---------------------------------------------------------------------------
# Task routing — keep Pillar 3 on a dedicated queue
# ---------------------------------------------------------------------------
app.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
    "app.engine.*": {"queue": "engine"},
}
