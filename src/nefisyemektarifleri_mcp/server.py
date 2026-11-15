"""MCP server: unofficial read-only access to Nefis Yemek Tarifleri recipes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from . import http as _http
from . import recipes as _R

mcp = FastMCP("nefisyemektarifleri-mcp")

INSTRUCTIONS = """\
Unofficial read-only MCP server for Nefis Yemek Tarifleri \
(nefisyemektarifleri.com), Türkiye's biggest recipe site — search \
14,000+ recipes per query, full recipe details (ingredients with \
amounts, steps, tips, times, servings, ratings, nutrition), the full \
recipe-category tree, category listings with popular/trending/newest \
sorts, the most-made recipes and the daily "Bugün Ne Pişirsem?" menu. \
No login, no API key. Times are Turkish shorthand (15dk); servings \
are Turkish ("6-8 kişilik"). Read-only; transport uses Chrome TLS \
impersonation with a plain-requests fallback and always sends the \
site as Referer (Cloudflare requires it on /ara/); requests are \
spaced ~0.8s apart. Built by Mohammad Abbasi (mohammad-abbasi-sh) — https://almanibama.ir · https://mabbasi.ir — Turkey \
MCP factory.\
"""


_SOURCE = "nefisyemektarifleri.com"
_DISCLAIMER = (
    "Unofficial read-only data from nefisyemektarifleri.com; "
    "verify on the site before acting on it."
)
_SORTS = ("popular", "trending", "newest")


def _envelope() -> dict:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": _SOURCE,
        "disclaimer": _DISCLAIMER,
    }


def _ok(payload: dict) -> str:
    return json.dumps({**_envelope(), **payload}, ensure_ascii=False)


def _err(e: Exception) -> str:
    return _ok({"error": str(e)})


def _validate_limit(limit: int, lo: int = 1, hi: int = 30) -> int:
    if not lo <= limit <= hi:
        raise ValueError(f"limit must be between {lo} and {hi}")
    return limit


def _validate_page(page: int) -> int:
    if page < 1:
        raise ValueError("page must be >= 1")
    if page > 20:
        raise ValueError("page must be <= 20")
    return page


@mcp.tool()
def nefis_search_recipes(query: str, limit: int = 10, page: int = 1) -> str:
    """Search Nefis Yemek Tarifleri recipes by dish or ingredient.
    query: e.g. "mercimek", "tavuk", "sütlü tatlı". limit 1..30 (13 per
    page — the server fetches further pages as needed). page 1..20.
    Returns matching recipes (title, url, serves, prep/cook times,
    author, saved/comment counts, video flag, image) + total results."""
    try:
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        _validate_limit(limit)
        _validate_page(page)
        q = query.strip()
        recipes: list[dict] = []
        total = None
        p = page
        while len(recipes) < limit and p <= page + 3:
            data = _R.parse_search_page(_http.fetch_search_page(q, p))
            if total is None:
                total = data["total_results"]
            if not data["recipes"]:
                break
            recipes.extend(data["recipes"])
            p += 1
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok(
        {
            "query": q,
            "page": page,
            "total_results": total,
            "count": len(recipes[:limit]),
            "recipes": recipes[:limit],
        }
    )


@mcp.tool()
def nefis_get_recipe(url: str) -> str:
    """Full recipe detail: ingredients with amounts, steps, tips,
    times, servings, rating, nutrition, author.
    url: a full nefisyemektarifleri.com recipe URL
    (e.g. https://www.nefisyemektarifleri.com/mercimek-corbasi-tarifi/)
    or a bare slug/path like "mercimek-corbasi-tarifi"."""
    try:
        u = url.strip()
        if not u:
            raise ValueError("url must not be empty")
        path = _R.path_from_url(u)
        recipe = _R.parse_recipe_page(
            _http.fetch_recipe_page(path), url=f"{_R.BASE}{path}"
        )
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok(recipe)


@mcp.tool()
def nefis_list_categories() -> str:
    """The full recipe-category tree from nefisyemektarifleri.com
    (top-level categories with their subcategories: name, slug, url).
    Use a slug from here with nefis_category_recipes."""
    try:
        cats = _R.parse_categories(_http.fetch_categories_page())
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok(
        {
            "count": len(cats),
            "subcategories_total": sum(len(c.get("subcategories", [])) for c in cats),
            "categories": cats,
        }
    )


@mcp.tool()
def nefis_category_recipes(
    category: str, limit: int = 12, page: int = 1, sort: str = "popular"
) -> str:
    """Recipes in one category.
    category: a slug from nefis_list_categories (e.g. "corba-tarifleri")
    or a full category URL. limit 1..30. page 1..20.
    sort: "popular" (default), "trending" or "newest"."""
    try:
        if not category or not category.strip():
            raise ValueError("category must not be empty")
        _validate_limit(limit)
        _validate_page(page)
        if sort not in _SORTS:
            raise ValueError(f"sort must be one of {', '.join(_SORTS)}")
        c = category.strip()
        if c.startswith("http"):
            slug = c.rstrip("/").rsplit("/", 1)[-1]
        else:
            slug = c.strip("/")
        recipes: list[dict] = []
        has_next = False
        p = page
        while len(recipes) < limit and p <= page + 2:
            html = _http.fetch_category_page(slug, p, sort)
            page_cards = _R.parse_recipe_cards(html)
            if not page_cards:
                break
            recipes.extend(page_cards)
            has_next = '<link rel="next"' in html
            if not has_next:
                break
            p += 1
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok(
        {
            "category": slug,
            "sort": sort,
            "page": page,
            "has_next_page": has_next,
            "count": len(recipes[:limit]),
            "recipes": recipes[:limit],
        }
    )


@mcp.tool()
def nefis_trending(limit: int = 10) -> str:
    """The most-made recipes ("En Çok Yapılanlar") — 24 recipes.
    limit 1..24."""
    try:
        _validate_limit(limit, 1, 24)
        rows = _R.parse_recipe_cards(_http.fetch_trending())
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok({"count": len(rows[:limit]), "recipes": rows[:limit]})


@mcp.tool()
def nefis_daily_menu(limit: int = 10) -> str:
    """Today's "Bugün Ne Pişirsem?" menu — 25 recipes picked for today.
    limit 1..25."""
    try:
        _validate_limit(limit, 1, 25)
        rows = _R.parse_recipe_cards(_http.fetch_daily())
    except (ValueError, _http.NefisError) as e:
        return _err(e)
    return _ok({"count": len(rows[:limit]), "recipes": rows[:limit]})


@mcp.tool()
def nefis_health() -> str:
    """Check whether nefisyemektarifleri.com is reachable right now.

    Returns status ok (HTTP 200), blocked (HTTP 403/429 — bot wall or
    rate limit) or error, plus the HTTP status and the probed URL.
    One polite request; it does not fetch any listings."""
    return _ok(_http.health_check())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    import sys

    sys.exit(main())
