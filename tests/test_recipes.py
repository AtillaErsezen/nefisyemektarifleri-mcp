"""Offline tests: parse real captured fixtures (see tests/fixtures/)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nefisyemektarifleri_mcp import recipes as R  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- search

def test_search_total_and_cards():
    data = R.parse_search_page(load("search.html"))
    assert data["total_results"] == 14694
    assert len(data["recipes"]) == 13
    first = data["recipes"][0]
    assert first["title"] == "Mercimek Köftesi Nasıl Yapılır? (videolu)"
    assert first["url"] == "https://www.nefisyemektarifleri.com/video/mercimek-koftesi-nasil-yapilir/"
    assert first["serves"] == "4-6"
    assert first["prep_time"] == "50dk"
    assert first["cook_time"] == "30dk"
    assert first["author"] == "Elif Atalar"
    assert first["saved_count"] == 385000  # "385bin"
    assert first["comment_count"] == 2985
    assert first["has_video"] is True
    assert first["image"].startswith("https://i.nefisyemektarifleri.com/")


def test_search_page2_differs():
    p1 = R.parse_search_page(load("search.html"))["recipes"]
    p2 = R.parse_search_page(load("search_page2.html"))["recipes"]
    assert len(p2) == 13
    assert p2[0]["title"] == "Diyet Mercimek Mantısı"
    assert {c["url"] for c in p1} != {c["url"] for c in p2}


def test_parse_tr_count():
    assert R._parse_tr_count("385bin") == 385000
    assert R._parse_tr_count("89bin") == 89000
    assert R._parse_tr_count("87.718") == 87718
    assert R._parse_tr_count("2985") == 2985
    assert R._parse_tr_count("1,2 mn") == 1200000
    assert R._parse_tr_count("729.641") == 729641
    assert R._parse_tr_count("") is None


# ---------------------------------------------------------------- recipe

def test_recipe_detail():
    r = R.parse_recipe_page(
        load("recipe.html"),
        url="https://www.nefisyemektarifleri.com/mercimek-corbasi-tarifi/",
    )
    assert r["title"] == "Mercimek Çorbası Tarifi"
    assert r["recipe_id"] == 1284
    assert r["rating"] == 4.8
    assert r["rating_votes"] == 388
    assert r["serves"] == "6-8"
    assert r["prep_time"] == "15dk"
    assert r["cook_time"] == "30dk"
    assert r["cook_type"] == "Haşlama"
    assert r["main_category"] == "Çorba Tarifleri"
    assert "corba-tarifleri" in r["categories"]
    assert r["author"]["name"] == "Elif Atalar"
    assert r["author"]["handle"] == "ElifAtalar"
    assert r["author"]["followers"] == 729641
    assert r["comments_count"] == 1699
    assert r["cooked_count"] == 1648
    assert r["saved_count"] == 87718
    assert r["claps"] == 853
    assert r["has_video"] is True
    assert r["date_published"] == "2014-01-10T18:05:36+03:00"
    assert r["description"].startswith("Tam kıvamında mercimek çorbası")
    assert r["intro"].startswith("Mercimek çorbası evlerimizde en çok pişen")
    assert "<" not in r["intro"]


def test_recipe_ingredients_grouped():
    r = R.parse_recipe_page(load("recipe.html"))
    groups = r["ingredients"]
    assert len(groups) == 2
    assert groups[0]["group"] == "Malzemeler"
    assert len(groups[0]["items"]) == 10
    assert groups[0]["items"][0] == "2 su bardağı kırmızı mercimek"
    assert groups[1]["group"] == "Sosu için:"
    assert groups[1]["items"] == [
        "2 yemek kaşığı tereyağı",
        "1 tatlı kaşığı kırmızı toz biber",
    ]
    assert "kırmızı mercimek" in r["ingredient_names"]


def test_recipe_steps_tips_nutrition_images():
    r = R.parse_recipe_page(load("recipe.html"))
    assert len(r["steps"]) == 9
    assert r["steps"][0].startswith("Kırmızı mercimek çorbası için sıvı yağı")
    assert len(r["tips"]) == 13
    assert r["tips"][0].startswith("Mercimeklerin bol su ile")
    nut = r["nutrition_per_serving"]
    assert nut["calories_kcal"] == 284
    assert nut["carbs_g"] == 25
    assert nut["protein_g"] == 13
    assert nut["fat_g"] == 12.5
    assert nut["fiber_g"] == 5.05
    assert len(r["images"]) == 7
    assert r["images"][0].endswith("mercimek-corbasi-tarifi.jpg")
    assert "mercimek" in r["tags"]


def test_recipe_no_title_raises():
    try:
        R.parse_recipe_page("<html><body>nope</body></html>")
    except ValueError as e:
        assert "title" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_slugify_and_path():
    assert R.slugify("Mercimek Çorbası") == "mercimek-corbasi"
    assert R.path_from_url(
        "https://www.nefisyemektarifleri.com/mercimek-corbasi-tarifi/"
    ) == "/mercimek-corbasi-tarifi/"
    assert R.path_from_url("mercimek-corbasi-tarifi") == "/mercimek-corbasi-tarifi/"


# ---------------------------------------------------------------- categories

def test_categories_tree():
    cats = R.parse_categories(load("categories.html"))
    assert len(cats) == 24
    assert sum(len(c["subcategories"]) for c in cats) == 74
    tatli = [c for c in cats if c["slug"] == "tatli-tarifleri"][0]
    assert tatli["name"] == "Tatlı Tarifleri"
    assert len(tatli["subcategories"]) == 14
    corba = [c for c in cats if c["slug"] == "corba-tarifleri"][0]
    assert corba["name"] == "Çorba Tarifleri"
    assert corba["url"].endswith("/kategori/tarifler/corba-tarifleri/")


def test_category_page_cards():
    cards = R.parse_recipe_cards(load("category.html"))
    assert len(cards) == 39
    assert cards[0]["title"] == "Yayla Çorbası Nasıl Yapılır? Videolu"
    p2 = R.parse_recipe_cards(load("category_page2.html"))
    assert len(p2) == 23
    assert p2[0]["title"] == "Şifa Deposu Tavuklu Kereviz Çorbası"
    assert {c["url"] for c in cards} != {c["url"] for c in p2}


def test_trending_and_daily():
    trending = R.parse_recipe_cards(load("trending.html"))
    assert len(trending) == 24
    assert trending[0]["title"] == "Pankek Tarifi Videosu"
    daily = R.parse_recipe_cards(load("daily.html"))
    assert len(daily) == 25
    assert daily[0]["title"] == "Erişteli Yeşil Mercimek Çorbası (Videolu)"
