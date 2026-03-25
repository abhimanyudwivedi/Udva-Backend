"""Brand management endpoints — CRUD for brands, queries, and keywords.

All routes require a valid Bearer access token.  Ownership is verified on
every brand-scoped request: a user can only read or modify their own brands.
404 is returned (not 403) when a brand is not found or belongs to another
user — this avoids leaking the existence of other users' resources.

Plan limits enforced:
    trial / solo  — 1 brand,  10 keywords, 10 queries
    indie         — 1 brand,  20 keywords, 20 queries
    studio        — 3 brands, 75 keywords, 50 queries
    agency        — 10 brands, 200 keywords, 100 queries
"""

import json
import re
import uuid
import logging

import asyncio

import anthropic as _anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.lib.auth import get_current_user
from app.lib.llm_clients import call_claude, call_gemini, call_openai, get_anthropic_client
from app.models.brand import Brand
from app.models.competitor import Competitor
from app.models.keyword import Keyword
from app.models.query import Query as QueryModel
from app.models.user import User
from app.schemas.brand import (
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    CompetitorCreate,
    CompetitorEntry,
    CompetitorResponse,
    CompetitorSuggestionsResponse,
    KeywordCreate,
    KeywordResponse,
    OnboardingScanResponse,
    OnboardingScanResult,
    PaginatedBrands,
    PaginatedKeywords,
    PaginatedQueries,
    QueryCreate,
    QueryResponse,
    SuggestionsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Plan limits
# ---------------------------------------------------------------------------

# Query limits are not defined in the Architecture plan table; these are
# sensible per-tier values that scale with keyword limits.
_PLAN_LIMITS: dict[str, dict[str, int]] = {
    "trial":      {"brands": 1,  "keywords": 10,  "queries": 10},
    "starter":    {"brands": 1,  "keywords": 20,  "queries": 20},
    "growth":     {"brands": 3,  "keywords": 75,  "queries": 75},
    "enterprise": {"brands": 10, "keywords": 200, "queries": 200},
}

_DEFAULT_LIMITS: dict[str, int] = {"brands": 1, "keywords": 10, "queries": 10}


def _limits(plan: str) -> dict[str, int]:
    """Return the plan limits dict for *plan*, falling back to trial defaults."""
    return _PLAN_LIMITS.get(plan, _DEFAULT_LIMITS)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_brand_or_404(
    brand_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Brand:
    """Fetch a brand that belongs to *current_user*, or raise 404.

    Returns 404 for both "not found" and "belongs to someone else" to prevent
    user enumeration.
    """
    result = await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.user_id == current_user.id)
    )
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


# ---------------------------------------------------------------------------
# Brand endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedBrands, summary="List brands")
async def list_brands(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedBrands:
    """Return all active brands owned by the authenticated user.

    Args:
        page:         1-based page number.
        limit:        Results per page (max 100).
        current_user: Injected from Bearer token.
        db:           Injected async session.
    """
    offset = (page - 1) * limit

    total_result = await db.execute(
        select(func.count()).select_from(Brand).where(
            Brand.user_id == current_user.id,
            Brand.is_active.is_(True),
        )
    )
    total: int = total_result.scalar_one()

    brands_result = await db.execute(
        select(Brand)
        .where(Brand.user_id == current_user.id, Brand.is_active.is_(True))
        .order_by(Brand.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    brands = brands_result.scalars().all()

    return PaginatedBrands(
        items=[BrandResponse.model_validate(b) for b in brands],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a brand")
async def create_brand(
    body: BrandCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrandResponse:
    """Create a new brand for the authenticated user.

    Enforces the plan brand limit before inserting.

    Raises:
        HTTPException 403: Plan brand limit reached.
    """
    limits = _limits(current_user.plan)

    count_result = await db.execute(
        select(func.count()).select_from(Brand).where(
            Brand.user_id == current_user.id,
            Brand.is_active.is_(True),
        )
    )
    current_count: int = count_result.scalar_one()

    if current_count >= limits["brands"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your {current_user.plan} plan allows up to {limits['brands']} brand(s). "
                "Upgrade to add more."
            ),
        )

    brand = Brand(
        user_id=current_user.id,
        name=body.name.strip(),
        domain=body.domain.strip() if body.domain else None,
        is_active=True,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)

    logger.info("create_brand: user_id=%s brand_id=%s", current_user.id, brand.id)
    return BrandResponse.model_validate(brand)


@router.get("/{brand_id}", response_model=BrandResponse, summary="Get a brand")
async def get_brand(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrandResponse:
    """Return a single brand by ID.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)
    return BrandResponse.model_validate(brand)


@router.put("/{brand_id}", response_model=BrandResponse, summary="Update a brand")
async def update_brand(
    brand_id: uuid.UUID,
    body: BrandUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrandResponse:
    """Update the name and/or domain of a brand.

    Only fields present in the request body are changed.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    if body.name is not None:
        brand.name = body.name.strip()
    if body.domain is not None:
        brand.domain = body.domain.strip() or None

    await db.commit()
    await db.refresh(brand)
    return BrandResponse.model_validate(brand)


@router.delete(
    "/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a brand",
)
async def delete_brand(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a brand by setting is_active to False.

    Historical visibility scores and mentions are preserved.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)
    brand.is_active = False
    await db.commit()
    logger.info("delete_brand: user_id=%s brand_id=%s", current_user.id, brand_id)


# ---------------------------------------------------------------------------
# Query (tracked prompt) endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/queries",
    response_model=PaginatedQueries,
    summary="List tracked prompts",
)
async def list_queries(
    brand_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedQueries:
    """Return all active queries for a brand.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    await _get_brand_or_404(brand_id, current_user, db)
    offset = (page - 1) * limit

    total_result = await db.execute(
        select(func.count()).select_from(QueryModel).where(
            QueryModel.brand_id == brand_id,
            QueryModel.is_active.is_(True),
        )
    )
    total: int = total_result.scalar_one()

    queries_result = await db.execute(
        select(QueryModel)
        .where(QueryModel.brand_id == brand_id, QueryModel.is_active.is_(True))
        .order_by(QueryModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    queries = queries_result.scalars().all()

    return PaginatedQueries(
        items=[QueryResponse.model_validate(q) for q in queries],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "/{brand_id}/queries",
    response_model=QueryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a tracked prompt",
)
async def create_query(
    brand_id: uuid.UUID,
    body: QueryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Add a new LLM prompt to track for a brand.

    Enforces the plan query limit.

    Raises:
        HTTPException 403: Plan query limit reached.
        HTTPException 404: Brand not found or belongs to another user.
    """
    await _get_brand_or_404(brand_id, current_user, db)
    limits = _limits(current_user.plan)

    count_result = await db.execute(
        select(func.count()).select_from(QueryModel).where(
            QueryModel.brand_id == brand_id,
            QueryModel.is_active.is_(True),
        )
    )
    current_count: int = count_result.scalar_one()

    if current_count >= limits["queries"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your {current_user.plan} plan allows up to {limits['queries']} tracked "
                "prompt(s) per brand. Upgrade to add more."
            ),
        )

    query = QueryModel(
        brand_id=brand_id,
        prompt_text=body.prompt_text.strip(),
        is_active=True,
    )
    db.add(query)
    await db.commit()
    await db.refresh(query)

    return QueryResponse.model_validate(query)


@router.delete(
    "/{brand_id}/queries/{query_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a tracked prompt",
)
async def delete_query(
    brand_id: uuid.UUID,
    query_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a query by setting is_active to False.

    Historical visibility scores linked to this query are preserved.

    Raises:
        HTTPException 404: Brand or query not found.
    """
    await _get_brand_or_404(brand_id, current_user, db)

    result = await db.execute(
        select(QueryModel).where(
            QueryModel.id == query_id,
            QueryModel.brand_id == brand_id,
            QueryModel.is_active.is_(True),
        )
    )
    query = result.scalar_one_or_none()
    if query is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

    query.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Keyword endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/keywords",
    response_model=PaginatedKeywords,
    summary="List keywords",
)
async def list_keywords(
    brand_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedKeywords:
    """Return all active keywords for a brand.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    await _get_brand_or_404(brand_id, current_user, db)
    offset = (page - 1) * limit

    total_result = await db.execute(
        select(func.count()).select_from(Keyword).where(
            Keyword.brand_id == brand_id,
            Keyword.is_active.is_(True),
        )
    )
    total: int = total_result.scalar_one()

    keywords_result = await db.execute(
        select(Keyword)
        .where(Keyword.brand_id == brand_id, Keyword.is_active.is_(True))
        .order_by(Keyword.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    keywords = keywords_result.scalars().all()

    return PaginatedKeywords(
        items=[KeywordResponse.model_validate(k) for k in keywords],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "/{brand_id}/keywords",
    response_model=KeywordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a keyword",
)
async def create_keyword(
    brand_id: uuid.UUID,
    body: KeywordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeywordResponse:
    """Add a keyword to monitor for a brand.

    Keywords are counted across all platforms for the plan limit.

    Raises:
        HTTPException 403: Plan keyword limit reached.
        HTTPException 404: Brand not found or belongs to another user.
    """
    await _get_brand_or_404(brand_id, current_user, db)
    limits = _limits(current_user.plan)

    count_result = await db.execute(
        select(func.count()).select_from(Keyword).where(
            Keyword.brand_id == brand_id,
            Keyword.is_active.is_(True),
        )
    )
    current_count: int = count_result.scalar_one()

    if current_count >= limits["keywords"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your {current_user.plan} plan allows up to {limits['keywords']} "
                "keyword(s) per brand. Upgrade to add more."
            ),
        )

    keyword = Keyword(
        brand_id=brand_id,
        keyword=body.keyword.strip(),
        platform=body.platform,
        is_active=True,
    )
    db.add(keyword)
    await db.commit()
    await db.refresh(keyword)

    return KeywordResponse.model_validate(keyword)


@router.delete(
    "/{brand_id}/keywords/{keyword_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a keyword",
)
async def delete_keyword(
    brand_id: uuid.UUID,
    keyword_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a keyword by setting is_active to False.

    Existing mentions linked to this keyword are preserved.

    Raises:
        HTTPException 404: Brand or keyword not found.
    """
    await _get_brand_or_404(brand_id, current_user, db)

    result = await db.execute(
        select(Keyword).where(
            Keyword.id == keyword_id,
            Keyword.brand_id == brand_id,
            Keyword.is_active.is_(True),
        )
    )
    keyword = result.scalar_one_or_none()
    if keyword is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")

    keyword.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

_SUGGESTIONS_SYSTEM = (
    "You are a marketing assistant. Return ONLY valid JSON with no markdown, "
    "no preamble, no explanation. The JSON must have exactly two keys: "
    '"queries" (array of 3 strings) and "keywords" (array of 3 strings).'
)


def _parse_suggestions(raw: str) -> dict[str, list[str]] | None:
    """Extract queries/keywords dict from LLM output, handling markdown fences."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    queries = parsed.get("queries")
    keywords = parsed.get("keywords")
    if not isinstance(queries, list) or not isinstance(keywords, list):
        return None
    return {
        "queries": [str(q).strip() for q in queries if str(q).strip()][:5],
        "keywords": [str(k).strip() for k in keywords if str(k).strip()][:5],
    }


@router.get("/{brand_id}/suggestions", response_model=SuggestionsResponse,
            summary="Get AI-generated query and keyword suggestions")
async def get_suggestions(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionsResponse:
    """Return LLM-generated suggestions for AI queries and keywords for a brand.

    Calls Claude Haiku once with the brand name and domain. Returns empty lists
    on LLM failure so the frontend can fall back to hardcoded templates.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    domain_hint = f" (website: {brand.domain})" if brand.domain else ""
    prompt = (
        f'Generate suggestions for a brand called "{brand.name}"{domain_hint}.\n\n'
        "Return exactly this JSON with no other text:\n"
        '{"queries": ["...", "...", "..."], "keywords": ["...", "...", "..."]}'
    )

    raw = ""
    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SUGGESTIONS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        first = response.content[0]
        raw = first.text if hasattr(first, "text") else ""
    except _anthropic.AnthropicError as exc:
        logger.warning("get_suggestions: anthropic error brand_id=%s: %s", brand_id, exc)

    parsed = _parse_suggestions(raw) if raw else None
    if parsed is None:
        logger.warning("get_suggestions: parse failed brand_id=%s raw=%.200r", brand_id, raw)
        return SuggestionsResponse(queries=[], keywords=[])

    logger.info(
        "get_suggestions: brand_id=%s queries=%d keywords=%d",
        brand_id, len(parsed["queries"]), len(parsed["keywords"]),
    )
    return SuggestionsResponse(queries=parsed["queries"], keywords=parsed["keywords"])


# ---------------------------------------------------------------------------
# Competitor suggestions + save
# ---------------------------------------------------------------------------

_COMPETITOR_SYSTEM = (
    "You are a market research assistant. Return ONLY valid JSON with no markdown, "
    "no preamble, no explanation. The JSON must have exactly one key: "
    '"competitors" (array of 5 competitor brand name strings).'
)


@router.get(
    "/{brand_id}/competitor-suggestions",
    response_model=CompetitorSuggestionsResponse,
    summary="Get AI-generated competitor suggestions",
)
async def get_competitor_suggestions(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompetitorSuggestionsResponse:
    """Return 5 LLM-generated competitor name suggestions for a brand.

    Calls Claude Haiku with brand name + domain. Returns empty list on failure.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    domain_hint = f" (website: {brand.domain})" if brand.domain else ""
    prompt = (
        f'List 5 direct competitors for a brand called "{brand.name}"{domain_hint}.\n\n'
        'Return exactly this JSON with no other text:\n'
        '{"competitors": ["Competitor A", "Competitor B", "Competitor C", "Competitor D", "Competitor E"]}'
    )

    raw = ""
    try:
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_COMPETITOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        first = response.content[0]
        raw = first.text if hasattr(first, "text") else ""
    except _anthropic.AnthropicError as exc:
        logger.warning("get_competitor_suggestions: anthropic error brand_id=%s: %s", brand_id, exc)

    if raw:
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL)
        try:
            parsed = json.loads(stripped)
            competitors = parsed.get("competitors")
            if isinstance(competitors, list):
                names = [str(c).strip() for c in competitors if str(c).strip()][:5]
                logger.info("get_competitor_suggestions: brand_id=%s count=%d", brand_id, len(names))
                return CompetitorSuggestionsResponse(competitors=names)
        except json.JSONDecodeError:
            pass

    logger.warning("get_competitor_suggestions: parse failed brand_id=%s", brand_id)
    return CompetitorSuggestionsResponse(competitors=[])


@router.post(
    "/{brand_id}/competitors",
    response_model=list[CompetitorResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Save selected competitors",
)
async def create_competitors(
    brand_id: uuid.UUID,
    body: CompetitorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CompetitorResponse]:
    """Bulk-save competitor names for a brand (used during onboarding).

    Replaces any existing competitors for this brand.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    await _get_brand_or_404(brand_id, current_user, db)

    # Clear existing competitors for this brand before saving new selection
    existing = await db.execute(
        select(Competitor).where(Competitor.brand_id == brand_id)
    )
    for c in existing.scalars().all():
        await db.delete(c)

    saved = []
    for entry in body.competitors:
        name = entry.name.strip()
        if not name:
            continue
        competitor = Competitor(
            brand_id=brand_id,
            name=name,
            domain=entry.domain.strip() if entry.domain else None,
        )
        db.add(competitor)
        saved.append(competitor)

    await db.commit()
    for c in saved:
        await db.refresh(c)

    logger.info("create_competitors: brand_id=%s saved=%d", brand_id, len(saved))
    return [CompetitorResponse.model_validate(c) for c in saved]


# ---------------------------------------------------------------------------
# Onboarding scan
# ---------------------------------------------------------------------------

_ONBOARDING_MODELS = [
    ("chatgpt",  "ChatGPT",  call_openai),
    ("claude",   "Claude",   call_claude),
    ("gemini",   "Gemini",   call_gemini),
]


@router.post(
    "/{brand_id}/onboarding-scan",
    response_model=OnboardingScanResponse,
    summary="Run a one-shot AI visibility scan for onboarding",
)
async def onboarding_scan(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingScanResponse:
    """Run a live scan across ChatGPT, Claude, and Gemini for the brand's first query.

    Used during onboarding to generate the blurred preview report. Runs the
    three LLM calls in parallel. Does not write to visibility_scores — results
    are ephemeral display-only data used to show the user their initial report.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
        HTTPException 400: Brand has no active queries yet.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    # Use the first active query for the scan
    query_result = await db.execute(
        select(QueryModel)
        .where(QueryModel.brand_id == brand_id, QueryModel.is_active.is_(True))
        .order_by(QueryModel.created_at.asc())
        .limit(1)
    )
    query = query_result.scalar_one_or_none()
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one AI query before running a scan.",
        )

    prompt = query.prompt_text
    brand_name_lower = brand.name.lower()

    # Fan out to all three models in parallel
    responses = await asyncio.gather(
        *[fn(prompt) for _, _, fn in _ONBOARDING_MODELS],
        return_exceptions=True,
    )

    results: list[OnboardingScanResult] = []
    for (key, display, _), raw in zip(_ONBOARDING_MODELS, responses):
        if isinstance(raw, Exception) or not raw:
            raw = ""
        mentioned = brand_name_lower in raw.lower()
        snippet = raw[:300].strip() if raw else ""
        results.append(OnboardingScanResult(
            model=key,
            display_name=display,
            mentioned=mentioned,
            response_snippet=snippet,
        ))

    mentioned_count = sum(1 for r in results if r.mentioned)
    logger.info(
        "onboarding_scan: brand_id=%s mentioned=%d/3",
        brand_id, mentioned_count,
    )
    return OnboardingScanResponse(
        brand_name=brand.name,
        prompt_used=prompt,
        results=results,
    )
