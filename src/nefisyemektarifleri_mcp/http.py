"""HTTP layer for nefisyemektarifleri_mcp.

nefisyemektarifleri.com serves its pages server-rendered with no login
and no API key. Two transport facts discovered 2026-11-15:
- /ara/ (search) is behind a Cloudflare check that rejects requests
  WITHOUT a Referer — plain curl + ``Referer: https://www.nefisyemektarifleri.com/``
  returns HTTP 200, while the same request without it gets a 403
  "Just a moment..." page (and curl-cffi impersonation alone does not
  help). Every request therefore carries the site as Referer.
- Listing pagination is WordPress-style ``/page/N/`` (``?sayfa=N`` is
  ignored — it silently returns page 1).

Transport uses curl-cffi chrome120 impersonation (the proven
Turkey-factory pattern) with a plain-requests fallback, so one
transport failing does not break the server. Requests are kept
gentle (one at a time, ~0.8s apart) and read-only.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from curl_cffi import requests as _creq
import requests as _plain

BASE = "https://www.nefisyemektarifleri.com"
TIMEOUT = 30.0
MIN_INTERVAL = 0.8  # seconds between requests — be polite

_HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    # Cloudflare on /ara/ requires a Referer from the site itself.
    "Referer": BASE + "/",
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_last_fetch = 0.0


class NefisError(RuntimeError):
    pass


def _throttle() -> None:
    global _last_fetch
    wait = MIN_INTERVAL - (time.monotonic() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    _last_fetch = time.monotonic()


_PROFILES = ("chrome120", "chrome131", "safari17_0")
_MAX_ATTEMPTS = 2  # one retry with the next profile
_RETRY_BACKOFF = 1.0  # seconds between attempts
_profile_idx = 0  # sticky: profile that last succeeded


def _request(url: str, headers: dict, timeout: float = TIMEOUT):
    """GET with fingerprint rotation.

    Starts at the sticky profile (chrome120 on a fresh process), retries
    once with the next profile on HTTP 403/429 or a transport error, then
    returns the last response (so the caller raises the specific 403/429
    error) or raises a network error if every attempt failed at the
    transport.
    """
    global _profile_idx
    last_exc: Exception | None = None
    for k in range(_MAX_ATTEMPTS):
        profile = _PROFILES[(_profile_idx + k) % len(_PROFILES)]
        try:
            resp = _creq.get(url, impersonate=profile, headers=headers, timeout=timeout)
        except Exception as e:
            last_exc = e
            if k + 1 < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)
                continue
            raise NefisError(f"network error fetching {url}: {e}") from e
        if resp.status_code in (403, 429):
            if k + 1 < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)
                continue
            return resp
        _profile_idx = (_profile_idx + k) % len(_PROFILES)
        return resp
    raise NefisError(f"network error fetching {url}: {last_exc}") from last_exc


def _get(url: str) -> str:
    _throttle()
    headers = dict(_HEADERS)
    try:
        resp = _request(url, headers)
        status, text = resp.status_code, resp.text
    except Exception:
        # Fallback transport: plain requests with a browser UA + Referer.
        try:
            resp = _plain.get(url, headers={**headers, "User-Agent": _UA}, timeout=TIMEOUT)
            status, text = resp.status_code, resp.text
        except NefisError:
            raise
        except Exception as e:
            raise NefisError(f"network error fetching {url}: {e}") from e
    if status == 403:
        raise NefisError(
            "nefisyemektarifleri.com refused the request (HTTP 403, bot wall) — try again later"
        )
    if status == 429:
        raise NefisError(
            "nefisyemektarifleri.com rate-limited the request (HTTP 429) — try again later"
        )
    if status == 404:
        raise NefisError(f"nefisyemektarifleri.com has no page at {url} (HTTP 404)")
    if status != 200:
        raise NefisError(f"nefisyemektarifleri.com returned HTTP {status} for {url}")
    return text


def fetch_search_page(query: str, page: int = 1) -> str:
    """Search results: /ara/?s=<q> (page 1) or /ara/page/<n>/?s=<q>."""
    q = quote(query)
    if page <= 1:
        url = f"{BASE}/ara/?s={q}"
    else:
        url = f"{BASE}/ara/page/{page}/?s={q}"
    return _get(url)


def fetch_recipe_page(path: str) -> str:
    """Recipe detail: path like /mercimek-corbasi-tarifi/ or
    /video/lokanta-usulu-mercimek-corbasi-tarifi-videosu/."""
    if not path.startswith("/"):
        path = "/" + path
    return _get(f"{BASE}{path}")


def fetch_home() -> str:
    return _get(f"{BASE}/")


def fetch_categories_page() -> str:
    return _get(f"{BASE}/kategori/tarifler/")


def fetch_category_page(slug: str, page: int = 1, sort: str | None = None) -> str:
    """Category listing: /kategori/tarifler/<slug>/ (+ /page/<n>/).
    sort: 'popular' -> ?nytorderby=archive-populer,
    'trending' -> ?nytorderby=archive-trending,
    'newest' -> ?nytorderby=archive-newest, None -> site default."""
    slug = slug.strip().strip("/")
    if page > 1:
        url = f"{BASE}/kategori/tarifler/{slug}/page/{page}/"
    else:
        url = f"{BASE}/kategori/tarifler/{slug}/"
    order = {
        "popular": "archive-populer",
        "trending": "archive-trending",
        "newest": "archive-newest",
    }.get(sort or "")
    if order:
        url += f"?nytorderby={order}"
    return _get(url)


def fetch_trending() -> str:
    return _get(f"{BASE}/en-cok-yapilanlar/")


def fetch_daily() -> str:
    return _get(f"{BASE}/bugun-ne-pisirsem/")


def health_check() -> dict:
    """One polite probe of the source site.

    Returns {"status": "ok"|"blocked"|"error", "http_status": int|None,
    "url": ..., "detail": ...}. Used by the `nefis_health` tool
    and the daily smoke CI.
    """
    url = BASE + "/"
    try:
        fetch_home()
    except NefisError as e:
        msg = str(e)
        if "403" in msg:
            return {"status": "blocked", "http_status": 403, "url": url, "detail": msg}
        if "429" in msg:
            return {"status": "blocked", "http_status": 429, "url": url, "detail": msg}
        return {"status": "error", "http_status": None, "url": url, "detail": msg}
    return {"status": "ok", "http_status": 200, "url": url}
