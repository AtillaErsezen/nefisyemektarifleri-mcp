"""Offline tests for the signed-in notebook tools (no network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nefisyemektarifleri_mcp import http as H  # noqa: E402
from nefisyemektarifleri_mcp import notebook as N  # noqa: E402
from nefisyemektarifleri_mcp import recipes as R  # noqa: E402
from nefisyemektarifleri_mcp import server as S  # noqa: E402

BASE = "https://www.nefisyemektarifleri.com"
SIGNED_IN = """<html><script>var nyt_user_nonce = 'abc123'; var nyt_post_id = 4697926;</script>
<a href="https://www.nefisyemektarifleri.com/u/test_1/tarif-defteri/?hide-user-header=1">Tarif Defterim</a>
<div data-content="defter-modal" id="defter-modal" class="inline-modals"><ul class="my-recipe-list">
<li class="fire-status" id="collection-11"><a href="#" data-collection-id="11" class=" recipe-name ">
  Tarif Defteri </a></li>
<li id="collection-22"><a href="#" data-collection-id="22" class="in-collection recipe-name">Tatlılar</a></li>
</ul><a href="#" class="create-book modal-trigger">Yeni Defter Oluştur</a></div></html>"""
INDEX = """<div class="col-xs-6 recipe-book-card" data-collection-id="11"><div><a href="x"><span class="title">Tarif Defteri</span></a></div></div>
<div class="col-xs-6 recipe-book-card" data-collection-id="22"><div><a href="y"><span class="title">Tatlılar</span></a></div></div>"""
CARD = ('<div class="recipe-cards "><div class="recipe-info"><h3><a class="title" '
        'href="https://www.nefisyemektarifleri.com/{slug}/" title="{t}">{t}</a></h3></div></div>')
NOTEBOOK = CARD.format(slug="sutlac", t="Sütlaç") + CARD.format(slug="revani", t="Revani")


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    f = tmp_path / "cookie.txt"
    f.write_text("s=1; t=a=b\n")
    monkeypatch.setenv("NEFIS_YEMEK_COOKIE_FILE", str(f))
    monkeypatch.setattr(H, "MIN_INTERVAL", 0)
    return f


class Fake(requests.adapters.BaseAdapter):
    """Answers requests from a handler(request) -> (status, text, headers)."""

    def __init__(self, handler):
        super().__init__()
        self.handler, self.seen = handler, []

    def send(self, request, **kw):
        self.seen.append(request)
        status, text, headers = self.handler(request)
        r = requests.Response()
        r.status_code, r._content, r.url, r.request = status, text.encode(), request.url, request
        r.headers.update(headers)
        return r

    def close(self):
        pass


def use(monkeypatch, handler) -> Fake:
    fake = Fake(handler)
    real = N._session

    def session():
        s = real()
        s.mount("https://", fake)
        s.mount("http://", fake)
        return s
    monkeypatch.setattr(N, "_session", session)
    return fake


# ------------------------------------------------------------ session file

def test_read_session(session_file, monkeypatch, tmp_path):
    assert N.read_session() == "s=1; t=a=b"
    session_file.write_text("  ")
    with pytest.raises(H.NefisError, match="(?i)cookie"):
        N.read_session()
    monkeypatch.setenv("NEFIS_YEMEK_COOKIE_FILE", str(tmp_path / "missing.txt"))
    with pytest.raises(H.NefisError, match="(?i)cookie"):
        N.read_session()


def test_session_sent_fresh_each_call_and_only_to_the_site_over_https(session_file, monkeypatch):
    def handler(req):
        if req.url.endswith("/old/"):
            return 301, "", {"location": BASE + "/new/"}
        if req.url.endswith("/away/"):
            return 302, "", {"location": "https://evil.example/x/"}
        if req.url.endswith("/plain/"):
            return 302, "", {"location": "http://www.nefisyemektarifleri.com/a/"}
        return 200, "ok", {"set-cookie": "x=9; Path=/"}

    fake = use(monkeypatch, handler)
    N.fetch_signed_in(BASE + "/old/")
    session_file.write_text("s=2")
    N.fetch_signed_in(BASE + "/b/")
    with pytest.raises(H.NefisError):
        N.fetch_signed_in(BASE + "/away/")
    with pytest.raises(H.NefisError):
        N.fetch_signed_in(BASE + "/plain/")
    cookies = [(r.url, r.headers.get("Cookie")) for r in fake.seen]
    assert cookies[1] == (BASE + "/new/", "s=1; t=a=b")  # same-site redirect keeps the session
    assert cookies[2] == (BASE + "/b/", "s=2")  # refreshed file, no stale x=9
    assert cookies[4] == ("https://evil.example/x/", None)  # never off-site
    assert cookies[6] == ("http://www.nefisyemektarifleri.com/a/", None)  # never over plain http
    assert "Chrome" not in fake.seen[0].headers["User-Agent"]  # says what it is


def test_errors_do_not_leak_the_session(session_file, monkeypatch):
    use(monkeypatch, lambda req: (500, "", {}))
    with pytest.raises(H.NefisError) as e:
        N.fetch_signed_in(BASE + "/a/")
    assert "s=1" not in str(e.value)


def test_bot_check_is_reported_not_retried(session_file, monkeypatch):
    fake = use(monkeypatch, lambda req: (403, "Just a moment...", {"cf-mitigated": "challenge"}))
    with pytest.raises(H.NefisError, match="bot check"):
        N.fetch_signed_in(BASE + "/a/")
    assert len(fake.seen) == 1


def test_lost_post_reply_says_state_is_unknown(session_file, monkeypatch):
    def handler(req):
        raise requests.ReadTimeout("lost")
    fake = use(monkeypatch, handler)
    with pytest.raises(H.NefisError, match="may or may not"):
        N.fetch_signed_in(N.AJAX_URL, {"action": "add_to_collection"})
    assert len(fake.seen) == 1


# ------------------------------------------------------------ parsers

def test_parse_signed_in():
    p = N.parse_signed_in(SIGNED_IN)
    assert p["nonce"] == "abc123" and p["post_id"] == 4697926
    assert p["notebook_index"] == BASE + "/u/test_1/tarif-defteri/"
    assert p["notebooks"] == [{"id": "11", "name": "Tarif Defteri", "has_recipe": False},
                              {"id": "22", "name": "Tatlılar", "has_recipe": True}]
    with pytest.raises(H.NefisError, match="(?i)cookie"):
        N.parse_signed_in("<html>signed out</html>")


def test_parse_notebook_index():
    assert N.parse_notebook_index(INDEX) == [{"id": "11", "name": "Tarif Defteri"}, {"id": "22", "name": "Tatlılar"}]


def test_pick_notebook_turkish_case():
    nbs = [{"id": "11", "name": "Tarif Defteri"}, {"id": "22", "name": "Tatlılar"}]
    assert N.pick_notebook(nbs, None)["id"] == "11"
    assert N.pick_notebook(nbs, "TATLILAR")["id"] == "22"
    with pytest.raises(H.NefisError, match="Tatlılar"):
        N.pick_notebook(nbs, "Çorbalar")


def test_cards_with_trailing_space_in_class_are_parsed():
    assert [c["title"] for c in R.parse_recipe_cards(NOTEBOOK)] == ["Sütlaç", "Revani"]


# ------------------------------------------------------------ tools

def fake_site(monkeypatch, reply='{"success": true, "msg": "Eklendi"}'):
    posts = []
    pages = {BASE + "/": SIGNED_IN, BASE + "/test-corba/": SIGNED_IN,
             BASE + "/u/test_1/tarif-defteri/": INDEX,
             BASE + "/u/test_1/tarif-defteri/?defter=22": NOTEBOOK}

    def fetch(url, data=None):
        if data is None:
            return url, pages[url]
        posts.append(data)
        return url, reply
    monkeypatch.setattr(N, "fetch_signed_in", fetch)
    return posts


def call(tool, *a):
    return json.loads(tool(*a))


def test_list_notebook_tool(monkeypatch):
    fake_site(monkeypatch)
    r = call(S.nefis_list_notebook, "tatlılar")
    assert r["notebook"] == "Tatlılar" and r["notebooks"] == ["Tarif Defteri", "Tatlılar"]
    assert [c["title"] for c in r["recipes"]] == ["Sütlaç", "Revani"]


def test_add_posts_expected_form(monkeypatch):
    posts = fake_site(monkeypatch)
    r = call(S.nefis_add_to_notebook, "test-corba")
    assert posts == [{"post_id": "4697926", "action": "add_to_collection", "nonce": "abc123", "collection": "11"}]
    assert r["added"] is True and r["notebook"] == "Tarif Defteri" and r["message"] == "Eklendi"
    assert r["url"] == BASE + "/test-corba/"


def test_add_when_already_there_and_remove_when_absent_do_not_post(monkeypatch):
    posts = fake_site(monkeypatch)
    assert call(S.nefis_add_to_notebook, "test-corba", "Tatlılar")["added"] is False
    assert call(S.nefis_remove_from_notebook, "test-corba")["removed"] is False
    assert posts == []


def test_remove_posts_remove_action(monkeypatch):
    posts = fake_site(monkeypatch, '{"success": true, "msg": "Çıkarıldı"}')
    r = call(S.nefis_remove_from_notebook, "test-corba", "tatlılar")
    assert posts[0]["action"] == "remove_from_collection" and posts[0]["collection"] == "22"
    assert r["removed"] is True


@pytest.mark.parametrize("reply,error", [('{"success": false, "msg": "Hata"}', "Hata"),
                                         ("-1", "(?i)cookie"),
                                         ("0", "unexpected reply"),
                                         ("<html>", "unexpected reply")])
def test_site_failures_become_errors(monkeypatch, reply, error):
    import re
    fake_site(monkeypatch, reply)
    r = call(S.nefis_add_to_notebook, "test-corba")
    assert re.search(error, r["error"])


def test_non_recipe_page_is_refused(monkeypatch):
    monkeypatch.setattr(N, "fetch_signed_in", lambda url, data=None: (url, "<script>nyt_user_nonce = 'x';</script>"))
    assert "recipe" in call(S.nefis_add_to_notebook, "kategori/tatlilar")["error"]


def test_reads_are_retried_after_network_errors_but_changes_are_not(session_file, monkeypatch):
    attempts = []

    def handler(req):
        attempts.append(req.method)
        if len(attempts) < 3 or req.method == "POST":
            raise requests.ConnectionError("TLS dropped")
        return 200, "ok", {}
    use(monkeypatch, handler)
    assert N.fetch_signed_in(BASE + "/a/") == (BASE + "/a/", "ok")
    assert attempts == ["GET"] * 3
    attempts.clear()
    with pytest.raises(H.NefisError, match="may or may not"):
        N.fetch_signed_in(N.AJAX_URL, {"action": "add_to_collection"})
    assert attempts == ["POST"]
