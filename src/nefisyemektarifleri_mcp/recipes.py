"""Domain logic: parse nefisyemektarifleri.com pages into compact dicts.

Data sources (all public, no login, no key):
- search:   GET /ara/?s=<q> — server-rendered cards, 13/page, /ara/page/<n>/
- recipe:   /<slug>-tarifi/ or /video/<slug>/ — dataLayer RecipeDetail JSON
             (rating, serves, times, tags, ingredients) + HTML lists
             (ingredients with amounts, steps, tips, nutrition)
- categories: /kategori/tarifler/ — full category tree (124 links)
- category:  /kategori/tarifler/<slug>/ — 42 cards/page, /page/<n>/,
             ?nytorderby=archive-populer|archive-trending|archive-newest
- trending:  /en-cok-yapilanlar/ — 24 most-made recipes
- daily:     /bugun-ne-pisirsem/ — 25 "what to cook today" recipes
Stdlib parsing only (re / json / html).
"""
from __future__ import annotations

import html as _html
import json
import re

BASE = "https://www.nefisyemektarifleri.com"

_TR_MAP = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u", "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
    }
)


def slugify(text: str) -> str:
    """Turkish-aware slug: 'Mercimek Çorbası' -> 'mercimek-corbasi'."""
    s = text.strip().translate(_TR_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(str(text))).strip()


def _text(html: str) -> str:
    """HTML -> plain text (tags stripped, entities decoded, ws collapsed)."""
    return _clean(re.sub(r"<[^>]+>", " ", html))


def _parse_tr_count(raw: str | None) -> int | None:
    """Turkish abbreviated counts: '385bin' -> 385000, '87.718' -> 87718,
    '2985' -> 2985, '1,2 mn' -> 1200000. Returns None when unparseable."""
    if not raw:
        return None
    s = _clean(raw).lower().replace("\xa0", " ")
    mult = 1
    if s.endswith("bin"):
        mult, s = 1000, s[:-3].strip()
    elif s.endswith("milyon"):
        mult, s = 1_000_000, s[:-6].strip()
    elif s.endswith("mn"):
        mult, s = 1_000_000, s[:-2].strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def _balanced_json(text: str, start: int) -> str | None:
    """Extract the {...} JSON object starting at text[start] == '{',
    honouring strings. Returns the raw JSON substring or None."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _datalayer(html: str) -> dict | None:
    """The dataLayer.push({... 'recipe': {...} ...}) block of a recipe page."""
    for m in re.finditer(r"dataLayer\.push\(\s*\{", html):
        raw = _balanced_json(html, m.start() + len("dataLayer.push("))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("recipe"), dict):
            return data
    return None


# ---------------------------------------------------------------- cards

_CARD_SPLIT = re.compile(r'<div class="recipe-cards">')


def _parse_card(chunk: str) -> dict | None:
    """One <div class='recipe-cards'> chunk -> compact recipe summary."""
    m = re.search(r'data-jshref="(https://www\.nefisyemektarifleri\.com/[^"]+)"', chunk)
    url = m.group(1) if m else ""
    if not url:
        m = re.search(r'<a class="title" href="([^"]+)"', chunk)
        url = m.group(1) if m else ""
    if not url:
        return None
    tm = re.search(r'<a class="title"[^>]*>(.*?)</a>', chunk, re.S)
    title = _clean(tm.group(1)) if tm else ""
    if not title:
        return None
    em = re.search(r'<span class="recipe-elements">(.*?)</span>', chunk, re.S)
    elements = _clean(em.group(1)) if em else ""
    serves = prep = cook = None
    if elements:
        sm = re.search(r"([\d\-–]+)\s*kişilik", elements)
        serves = sm.group(1) if sm else None
        pm = re.search(r"(\d+\s*dk)\s*Hazırlık", elements)
        prep = _clean(pm.group(1)) if pm else None
        cm = re.search(r"(\d+\s*dk)\s*Pişirme", elements)
        cook = _clean(cm.group(1)) if cm else None
    om = re.search(r'<a[^>]*class="recipe-owner"[^>]*>', chunk)
    author = author_url = None
    if om:
        tag = om.group(0)
        hm = re.search(r'href="([^"]+)"', tag)
        tm = re.search(r'title="([^"]+)"', tag)
        author_url = hm.group(1) if hm else None
        author = _clean(tm.group(1)) if tm else None
    saved = comments = None
    sm = re.search(
        r'collection-button[^>]*>.*?<span class="count">([^<]+)</span>', chunk, re.S
    )
    if sm:
        saved = _parse_tr_count(sm.group(1))
    cm = re.search(
        r'comment-button[^>]*>.*?<span class="count">([^<]+)</span>', chunk, re.S
    )
    if cm:
        comments = _parse_tr_count(cm.group(1))
    im = re.search(r'<img[^>]*\ssrc="([^"]+)"', chunk)
    image = im.group(1) if im else ""
    return {
        "title": title,
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "serves": serves,
        "prep_time": prep,
        "cook_time": cook,
        "author": author,
        "author_url": author_url,
        "saved_count": saved,
        "comment_count": comments,
        "has_video": "/video/" in url or "icon-play" in chunk,
        "image": image,
    }


def parse_recipe_cards(html: str) -> list[dict]:
    """All recipe-cards on a page, deduped by URL, in page order."""
    out, seen = [], set()
    for chunk in _CARD_SPLIT.split(html)[1:]:
        card = _parse_card(chunk)
        if card and card["url"] not in seen:
            seen.add(card["url"])
            out.append(card)
    return out


def parse_search_page(html: str) -> dict:
    """Search results page -> {total_results, recipes}."""
    total = None
    m = re.search(r"<strong>([\d\.]+)</strong>\s*sonuç bulundu", html)
    if m:
        total = int(m.group(1).replace(".", ""))
    return {"total_results": total, "recipes": parse_recipe_cards(html)}


# ---------------------------------------------------------------- recipe

def _ingredients(html: str) -> list[dict]:
    """Grouped ingredients with amounts.

    <ul class='recipe-materials'> blocks, each optionally preceded by a
    <p>Group:</p> label (e.g. 'Sosu için:'). Returns
    [{group, items: [...]}, ...]."""
    groups: list[dict] = []
    for m in re.finditer(
        r"(?:<p>([^<]{1,80})</p>\s*)?<ul class=\"recipe-materials\">(.*?)</ul>",
        html,
        re.S,
    ):
        label = _clean(m.group(1))
        items = [
            _clean(x)
            for x in re.findall(
                r'<li[^>]*itemprop="recipeIngredient"[^>]*>(.*?)</li>', m.group(2), re.S
            )
        ]
        items = [i for i in items if i]
        if not items:
            continue
        groups.append({"group": label or "Malzemeler", "items": items})
    return groups


def _steps(html: str) -> list[str]:
    m = re.search(
        r'<ol[^>]*itemprop="recipeInstructions"[^>]*>(.*?)</ol>', html, re.S
    )
    if not m:
        return []
    return [_clean(x) for x in re.findall(r"<li>(.*?)</li>", m.group(1), re.S) if _clean(x)]


def _tips(html: str) -> list[str]:
    m = re.search(r'<section id="additional-description">(.*?)</section>', html, re.S)
    if not m:
        return []
    return [_clean(x) for x in re.findall(r"<li>(.*?)</li>", m.group(1), re.S) if _clean(x)]


def _nutrition(html: str) -> dict:
    """Per-serving nutrition from the 'Besin Değerleri' block.

    The page carries a detail table like ``Karbonhidrat(g) 25
    Protein(g) 13 Yağ(g) 12.5 Lif(g) 5.05 ...`` plus a ``284 kcal``
    header — parse both (best effort, floats where the site has them).
    """
    i = html.find("Besin Değerleri")
    if i < 0:
        return {}
    seg = _text(html[i : i + 12000])
    out: dict = {}
    m = re.search(r"(\d+)\s*kcal", seg)
    if m:
        out["calories_kcal"] = int(m.group(1))
    labels = (
        ("carbs_g", "Karbonhidrat", "g"),
        ("protein_g", "Protein", "g"),
        ("fat_g", "Yağ", "g"),
        ("fiber_g", "Lif", "g"),
        ("cholesterol_mg", "Kolesterol", "mg"),
        ("sodium_mg", "Sodyum", "mg"),
        ("potassium_mg", "Potasyum", "mg"),
        ("calcium_mg", "Kalsiyum", "mg"),
        ("vitamin_a_iu", "Vitamin A", "iu"),
        ("vitamin_c_mg", "Vitamin C", "mg"),
        ("iron_mg", "Demir", "mg"),
    )
    for key, label, unit in labels:
        m = re.search(
            re.escape(label) + r"\(" + unit + r"\)\s*([\d,\.]+)", seg
        )
        if m:
            v = float(m.group(1).replace(",", "."))
            out[key] = int(v) if v == int(v) else v
    return out


def _author(html: str) -> dict:
    """Main recipe author from <section class='post-author-section ...'>."""
    m = re.search(
        r'<section class="post-author-section[^>]*>.*?<a href="(https://www\.nefisyemektarifleri\.com/u/[^"]+)" title="([^"]+)"',
        html,
        re.S,
    )
    if not m:
        return {}
    seg = html[m.start() : m.start() + 3000]
    followers = None
    fm = re.search(r"([\d\.]+)\s*Takipçi", _text(seg))
    if fm:
        followers = _parse_tr_count(fm.group(1))
    handle = None
    hm = re.search(r"@([A-Za-z0-9_]+)", _text(seg))
    if hm:
        handle = hm.group(1)
    return {
        "name": _clean(m.group(2)),
        "profile_url": m.group(1),
        "handle": handle,
        "followers": followers,
    }


def _images(html: str) -> list[str]:
    """Step photos from the Yapılışı figures + og:image first.

    Only the figures between the 'Yapılışı' heading and the tips
    section belong to this recipe — later figures are related recipes.
    """
    out, seen = [], set()
    m = re.search(r'og:image" content="([^"]+)"', html)
    if m:
        out.append(m.group(1))
        seen.add(m.group(1))
    h2 = re.search(r"<h2[^>]*>\s*Yapılışı\s*</h2>", html)
    start = h2.end() if h2 else 0
    end = html.find('<section id="additional-description">', start)
    seg = html[start : end if end > 0 else start + 40000]
    for src in re.findall(
        r"<figure[^>]*class=['\"][^'\"]*recipe-image[^'\"]*['\"][^>]*>"
        r".*?<img[^>]*\ssrc=\"([^\"]+)\"",
        seg,
        re.S,
    ):
        if src not in seen:
            seen.add(src)
            out.append(src)
    return out


def parse_recipe_page(html: str, url: str = "") -> dict:
    """Full recipe detail from a /<slug>-tarifi/ or /video/<slug>/ page."""
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    title = _clean(h1.group(1)) if h1 else ""
    if not title:
        raise ValueError("no recipe title found on this page")
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    dl = _datalayer(html) or {}
    rec = dl.get("recipe") or {}
    contrib = dl.get("contributor") or {}
    intro = None
    m = re.search(
        r'class="owners-words[^>]*>.*?<blockquote>(.*?)</blockquote>', html, re.S
    )
    if m:
        intro = _text(m.group(1))
    pub = re.search(r'article:published_time" content="([^"]+)"', html)
    votes = None
    vm = re.search(r"([\d\.]+)\s*oy,\s*ortalama:\s*([\d,\.]+)", _text(html))
    if vm:
        votes = int(vm.group(1).replace(".", ""))
    author = _author(html)
    if not author and contrib:
        author = {"contributor_id": str(contrib.get("id"))}
    return {
        "title": title,
        "url": url,
        "description": _clean(desc.group(1)) if desc else None,
        "intro": intro,
        "author": author,
        "rating": rec.get("rating"),
        "rating_votes": votes,
        "serves": _clean(rec.get("serves")),
        "prep_time": rec.get("prepTime") or "",
        "cook_time": rec.get("cookDuration") or "",
        "cook_type": rec.get("cookType") or "",
        "categories": rec.get("categories") or [],
        "main_category": rec.get("mainCategory") or "",
        "tags": rec.get("tags") or [],
        "ingredients": _ingredients(html),
        "ingredient_names": [i.get("ingredient_name") for i in rec.get("ingredients") or []],
        "steps": _steps(html),
        "tips": _tips(html),
        "nutrition_per_serving": _nutrition(html),
        "comments_count": rec.get("comments"),
        "cooked_count": rec.get("cooked"),
        "saved_count": rec.get("saved"),
        "claps": rec.get("claps"),
        "has_video": rec.get("hasVideo") == "Evet" or "/video/" in url,
        "images": _images(html),
        "date_published": pub.group(1) if pub else None,
        "recipe_id": rec.get("id"),
    }


# ---------------------------------------------------------------- categories

def parse_categories(html: str) -> list[dict]:
    """Category tree from /kategori/tarifler/.

    Top-level = /kategori/tarifler/<slug>/, sub = .../<slug>/<sub>/.
    Returns [{name, slug, url, subcategories: [...]}, ...]."""
    found: dict[str, dict] = {}
    order: list[str] = []
    for href, name in re.findall(
        r'href="(https://www\.nefisyemektarifleri\.com/kategori/tarifler/[^"#]+)"[^>]*>([^<]+)</a>',
        html,
    ):
        name = _clean(name)
        if not name:
            continue
        path = href.rstrip("/").split("/kategori/tarifler/")[-1]
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        slug = parts[-1]
        if slug in found:
            continue
        found[slug] = {
            "name": name,
            "slug": slug,
            "url": href,
            "subcategories": [],
            "_parts": parts,
        }
        order.append(slug)
    # Two passes: parents may appear after their children in the page.
    top: list[dict] = []
    for slug in order:
        node = found[slug]
        parts = node.pop("_parts")
        if len(parts) == 1:
            top.append(node)
        else:
            parent = found.get(parts[-2])
            if parent is not None:
                parent["subcategories"].append(node)
            else:  # orphan subcategory — surface it at top level
                top.append(node)
    return top


def path_from_url(url: str) -> str:
    """Full nefis URL (or bare slug) -> site path like /mercimek-corbasi-tarifi/."""
    u = url.strip()
    if u.startswith("http"):
        u = re.sub(r"^https?://[^/]+", "", u)
    if not u.startswith("/"):
        u = "/" + u
    if not u.endswith("/"):
        u += "/"
    return u
