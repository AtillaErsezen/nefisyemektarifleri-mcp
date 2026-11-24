"""Signed-in tools: the user's recipe notebook ("Tarif Defteri") on nefisyemektarifleri.com.

The server never signs in and never sees a password. It reuses the user's browser session:
the `Cookie` value saved in a local file (NEFIS_YEMEK_COOKIE_FILE, default
~/.config/nefis-yemek/cookie.txt). These requests use a plain `requests` session that says
what it is: no browser impersonation, no fingerprint rotation, no retries after a block.

Site facts (observed 2026-11-24, signed in):
- Signed-in pages carry `nyt_user_nonce = '<token>'`; recipe pages also `nyt_post_id = <n>`
  and a `#defter-modal` listing the user's notebooks (`data-collection-id`, `in-collection`).
- Add/remove: POST /wp-admin/admin-ajax.php?ajaxget=1 with post_id, action
  (add_to_collection | remove_from_collection), nonce, collection -> {"success", "msg"}.
- Notebooks: /u/<user>/tarif-defteri/ (.recipe-book-card), one notebook: ?defter=<id>.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.cookies import create_cookie

from . import http as _http
from . import recipes as _R

HOST = "www.nefisyemektarifleri.com"
AJAX_URL = _http.BASE + "/wp-admin/admin-ajax.php?ajaxget=1"
DEFAULT_COOKIE_FILE = "~/.config/nefis-yemek/cookie.txt"
UA = "Mozilla/5.0 (compatible; nefisyemektarifleri-mcp; user's own notebook, user-triggered)"


def cookie_path() -> Path:
    return Path(os.environ.get("NEFIS_YEMEK_COOKIE_FILE") or DEFAULT_COOKIE_FILE).expanduser()


def _not_signed_in() -> _http.NefisError:
    return _http.NefisError(
        f"Not signed in: save your browser's nefisyemektarifleri.com cookie to {cookie_path()} "
        "(see the README). Sessions expire; save a fresh one if this keeps happening."
    )


def read_session() -> str:
    """The saved Cookie value, read on every call so a refreshed file needs no restart."""
    try:
        value = cookie_path().read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if not value:
        raise _not_signed_in()
    return value


def _session() -> requests.Session:
    # A fresh session per call: only the file's cookies count. They are scoped to the site and
    # marked secure, so requests sends them on same-site https redirects and nowhere else.
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    for pair in read_session().split(";"):
        name, _, value = pair.strip().partition("=")
        if name:
            s.cookies.set_cookie(create_cookie(name, value, domain=HOST, path="/", secure=True))
    return s


def fetch_signed_in(url: str, data: dict | None = None) -> tuple[str, str]:
    """GET (or POST form `data`) with the saved session. Returns (final_url, text)."""
    s = _session()
    attempts = 3 if data is None else 1  # reads are retried; a resent change could undo the first one
    try:
        for attempt in range(attempts):
            _http._throttle()
            if attempt:
                time.sleep(_http.MIN_INTERVAL * attempt)  # the site drops bursts at the TLS layer
            try:
                r = s.get(url, timeout=_http.TIMEOUT) if data is None else s.post(url, data=data, timeout=_http.TIMEOUT)
                break
            except requests.RequestException as e:
                if attempt == attempts - 1:
                    raise _http.NefisError(
                        f"network error ({type(e).__name__}) for {urlparse(url).path}"
                        + ("; the notebook may or may not have changed, check with nefis_list_notebook"
                           if data is not None else "")
                    ) from None
    finally:
        s.close()
    if r.headers.get("cf-mitigated") or r.status_code in (403, 429):
        raise _http.NefisError("nefisyemektarifleri.com answered with a bot check; try again later in the browser")
    final = urlparse(r.url)
    if final.hostname != HOST or final.scheme != "https":
        raise _http.NefisError(f"redirected away from https://{HOST}; stopped")
    if r.status_code != 200:
        raise _http.NefisError(f"nefisyemektarifleri.com returned HTTP {r.status_code} for {final.path}")
    return r.url, r.text


def parse_signed_in(html: str) -> dict:
    """Token, recipe id (recipe pages), notebook page link, and the "Deftere Ekle" notebooks."""
    nonce = re.search(r"nyt_user_nonce\s*=\s*['\"]([^'\"]+)", html)
    if not nonce:
        raise _not_signed_in()
    post_id = re.search(r"nyt_post_id\s*=\s*(\d+)", html)
    index = re.search(r'href="(https://www\.nefisyemektarifleri\.com/u/[^/"]+/tarif-defteri/)', html)
    modal = re.search(r'id="defter-modal".*?</ul>', html, re.S)
    notebooks = []
    for tag, name in re.findall(r'(<a[^>]*data-collection-id="\d+"[^>]*>)(.*?)</a>', modal.group(0) if modal else "", re.S):
        notebooks.append({
            "id": re.search(r'data-collection-id="(\d+)"', tag).group(1),
            "name": _R._clean(name),
            "has_recipe": bool(re.search(r'class="[^"]*\bin-collection\b', tag)),
        })
    return {"nonce": nonce.group(1), "post_id": int(post_id.group(1)) if post_id else None,
            "notebook_index": index.group(1) if index else None, "notebooks": notebooks}


def parse_notebook_index(html: str) -> list[dict]:
    out = []
    for chunk in re.split(r'(?=<div[^>]*class="[^"]*\brecipe-book-card\b)', html)[1:]:
        cid = re.search(r'data-collection-id="(\d+)"', chunk)
        title = re.search(r'class="title"[^>]*>(.*?)<', chunk, re.S)
        if cid and title:
            out.append({"id": cid.group(1), "name": _R._clean(title.group(1))})
    return out


def pick_notebook(notebooks: list[dict], name: str | None) -> dict:
    if not notebooks:
        raise _http.NefisError("no notebooks found on your account")
    if name is None:
        return notebooks[0]
    for nb in notebooks:
        if _R.slugify(nb["name"]) == _R.slugify(name):  # Turkish-safe: "TATLILAR" matches "Tatlılar"
            return nb
    raise _http.NefisError(f"no notebook named {name!r}; your notebooks: {', '.join(n['name'] for n in notebooks)}")


def list_notebook(notebook: str | None = None) -> dict:
    index = parse_signed_in(fetch_signed_in(_http.BASE + "/")[1])["notebook_index"]
    if not index:
        raise _http.NefisError("could not find your notebook page on the site")
    notebooks = parse_notebook_index(fetch_signed_in(index)[1])
    nb = pick_notebook(notebooks, notebook)
    # shortcut: first page of the notebook only (22 recipes fit on one page); add paging if long notebooks get cut
    recipes = _R.parse_recipe_cards(fetch_signed_in(f"{index}?defter={nb['id']}")[1])
    return {"notebook": nb["name"], "notebooks": [n["name"] for n in notebooks], "recipes": recipes}


def set_in_notebook(url: str, notebook: str | None, add: bool) -> dict:
    final_url, html = fetch_signed_in(_http.BASE + _R.path_from_url(url))
    page = parse_signed_in(html)
    if page["post_id"] is None:
        raise _http.NefisError(f"{final_url} is not a recipe page")
    nb = pick_notebook(page["notebooks"], notebook)
    key = "added" if add else "removed"
    title = re.search(r'<h1[^>]*class="[^"]*recipe-name[^"]*"[^>]*>(.*?)</h1>', html, re.S)
    result = {"recipe": _R._clean(title.group(1)) if title else None, "url": final_url, "notebook": nb["name"]}
    if nb["has_recipe"] == add:  # already as asked; the site's button would toggle it back
        return {**result, key: False, "message": "already in the notebook" if add else "not in the notebook"}
    _, reply = fetch_signed_in(AJAX_URL, {
        "post_id": str(page["post_id"]), "action": "add_to_collection" if add else "remove_from_collection",
        "nonce": page["nonce"], "collection": nb["id"]})
    try:
        reply = json.loads(reply)
    except ValueError:
        reply = None
    if reply == -1:  # WordPress: token rejected, i.e. the session is stale
        raise _not_signed_in()
    if not isinstance(reply, dict):
        raise _http.NefisError("the site gave an unexpected reply; the notebook may not have changed")
    if reply.get("success") is not True:
        raise _http.NefisError(f"the site refused: {reply.get('msg') or 'no reason given'}")
    return {**result, key: True, "message": reply.get("msg") or ""}
