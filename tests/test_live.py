"""Live tests: a few cautious requests against nefisyemektarifleri.com.

Run with:  .venv/bin/python -m pytest tests/test_live.py -q
Skipped automatically when the site is unreachable (network errors).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nefisyemektarifleri_mcp import http, recipes as R  # noqa: E402


def _live(fn):
    try:
        return fn()
    except http.NefisError as e:
        pytest.skip(f"site unreachable: {e}")


def test_live_search():
    data = _live(lambda: R.parse_search_page(http.fetch_search_page("mercimek")))
    assert data["total_results"] and data["total_results"] > 1000
    assert len(data["recipes"]) >= 10
    assert all(c["title"] and c["url"] for c in data["recipes"])


def test_live_search_page2():
    p1 = _live(lambda: R.parse_search_page(http.fetch_search_page("mercimek", 1)))
    p2 = _live(lambda: R.parse_search_page(http.fetch_search_page("mercimek", 2)))
    assert p1["recipes"][0]["url"] != p2["recipes"][0]["url"]


def test_live_recipe():
    r = _live(
        lambda: R.parse_recipe_page(
            http.fetch_recipe_page("/mercimek-corbasi-tarifi/"),
            url="https://www.nefisyemektarifleri.com/mercimek-corbasi-tarifi/",
        )
    )
    assert "Mercimek" in r["title"]
    assert r["rating"] and float(r["rating"]) >= 4.0
    assert len(r["ingredients"]) >= 1
    assert sum(len(g["items"]) for g in r["ingredients"]) >= 5
    assert len(r["steps"]) >= 3
    assert r["author"]["name"]


def test_live_categories():
    cats = _live(lambda: R.parse_categories(http.fetch_categories_page()))
    assert len(cats) >= 20
    assert any(c["slug"] == "corba-tarifleri" for c in cats)


def test_live_category_listing():
    cards = _live(
        lambda: R.parse_recipe_cards(http.fetch_category_page("corba-tarifleri"))
    )
    assert len(cards) >= 20
    assert all(c["title"] and c["url"] for c in cards)


def test_live_category_sort_newest():
    cards = _live(
        lambda: R.parse_recipe_cards(
            http.fetch_category_page("corba-tarifleri", sort="newest")
        )
    )
    assert len(cards) >= 10


def test_live_trending():
    rows = _live(lambda: R.parse_recipe_cards(http.fetch_trending()))
    assert len(rows) >= 20


def test_live_daily():
    rows = _live(lambda: R.parse_recipe_cards(http.fetch_daily()))
    assert len(rows) >= 20


def test_live_health():
    h = _live(http.health_check)
    assert h["status"] == "ok"
    assert h["http_status"] == 200
