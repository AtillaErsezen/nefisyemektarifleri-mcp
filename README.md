# nefisyemektarifleri-mcp 🇹🇷

mcp-name: io.github.mohammad-abbasi-sh/nefisyemektarifleri-mcp

Unofficial MCP server for **Nefis Yemek Tarifleri** (nefisyemektarifleri.com) — Türkiye's biggest recipe site: search 14,000+ recipes per query, full recipe details (ingredients with amounts, steps, tips, times, servings, ratings, nutrition), the full recipe-category tree, category listings with popular/trending/newest sorts, the most-made recipes and the daily "Bugün Ne Pişirsem?" menu. Optionally, it manages your own recipe notebook ("Tarif Defteri") on the site.

Forked from [mohammad-abbasi-sh/nefisyemektarifleri-mcp](https://github.com/mohammad-abbasi-sh/nefisyemektarifleri-mcp) at v0.1.0 (MIT).

> Part of the "Turkey MCP factory" (Sepehr-style pipeline). Not affiliated with Nefis Yemek Tarifleri.

## For AI agents

Add to your MCP client config (stdio):

```json
{
  "mcpServers": {
    "nefis": {
      "command": "uvx",
      "args": ["nefisyemektarifleri-mcp==0.1.0"]
    }
  }
}
```

Or run locally: `python -m nefisyemektarifleri_mcp.server` (needs `mcp<2`, `curl-cffi`, `requests`).

## Tools

| Tool | Description |
|------|-------------|
| `nefis_search_recipes` | Search recipes by dish/ingredient — `query`, `limit` (1..30), `page` (1..20) |
| `nefis_get_recipe` | Full recipe — full URL or bare slug (e.g. `mercimek-corbasi-tarifi`) |
| `nefis_list_categories` | Full category tree (24 top-level, 74 subcategories) |
| `nefis_category_recipes` | Recipes in one category — `category` slug/URL, `limit`, `page`, `sort` (popular/trending/newest) |
| `nefis_trending` | Most-made recipes ("En Çok Yapılanlar", 24) |
| `nefis_daily_menu` | Today's "Bugün Ne Pişirsem?" menu (25 recipes) |
| `nefis_health` | Reachability check (ok / blocked / error) |
| `nefis_list_notebook` | Recipes in your notebook ("Tarif Defteri") — `notebook` name, first one by default. Needs your session |
| `nefis_add_to_notebook` | Saves a recipe to your notebook — `url`, `notebook`. Needs your session |
| `nefis_remove_from_notebook` | Removes a recipe from your notebook — `url`, `notebook`. Needs your session |

Example output (`nefis_search_recipes` / "mercimek"):

```json
{"query": "mercimek", "total_results": 14694,
 "recipes": [{"title": "Mercimek Köftesi Nasıl Yapılır? (videolu)",
   "serves": "4-6", "prep_time": "50dk", "cook_time": "30dk",
   "author": "Elif Atalar", "saved_count": 385000, "comment_count": 2985}]}
```

Example output (`nefis_get_recipe` / "mercimek-corbasi-tarifi"):

```json
{"title": "Mercimek Çorbası Tarifi", "rating": 4.8, "rating_votes": 388,
 "serves": "6-8", "prep_time": "15dk", "cook_time": "30dk",
 "ingredients": [{"group": "Malzemeler",
   "items": ["2 su bardağı kırmızı mercimek", "1 adet soğan", "..."]},
  {"group": "Sosu için:",
   "items": ["2 yemek kaşığı tereyağı", "..."]}],
 "steps": ["Kırmızı mercimek çorbası için sıvı yağı ...", "..."],
 "nutrition_per_serving": {"calories_kcal": 284, "carbs_g": 25,
   "protein_g": 13, "fat_g": 12.5, "fiber_g": 5.05}}
```

Notes:
- Search is the site's own `/ara/` page — Cloudflare rejects requests without a Referer, so every request sends the site as Referer; transport uses Chrome TLS impersonation with a plain-requests fallback.
- Listings paginate WordPress-style (`/page/2/`); `?sayfa=N` is ignored by the site (it silently returns page 1), so the server never uses it.
- Times are Turkish shorthand (`15dk`); servings are Turkish (`6-8 kişilik`); saved/comment counts parse Turkish abbreviations (`385bin` → 385000).
- Data: nefisyemektarifleri.com public pages — no key, no login, read-only, except the three notebook tools.

## Recipe notebook (sign-in)

The notebook tools act on your own account. The server never signs in and never sees your password: it reuses your browser's session, saved in a file.

1. Sign in to nefisyemektarifleri.com in your browser.
2. Developer tools (F12) → **Application** → **Cookies** → `https://www.nefisyemektarifleri.com`: find the cookie whose name starts with `wordpress_logged_in_`. Take only that one; the list also shows Google's cookies, which belong to your Google account.
3. Save `<name>=<value>` on one line:

   ```bash
   mkdir -p ~/.config/nefis-yemek && install -m 600 /dev/null ~/.config/nefis-yemek/cookie.txt
   nano ~/.config/nefis-yemek/cookie.txt
   ```

   To keep it elsewhere, set `NEFIS_YEMEK_COOKIE_FILE` to its path.

The file is as good as being signed in: keep it private and never paste it into chats. It is read on every call, so when the tools say you are not signed in, save a fresh one (no restart). Notebook requests use a plain `requests` client that identifies itself (no browser impersonation, no Referer trick) and send the session only to `https://www.nefisyemektarifleri.com`. Adding or removing is never retried: if the reply is lost, the tool says so and you can check with `nefis_list_notebook`. `nefis_list_notebook` returns the first page of a notebook.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install "mcp<2" curl-cffi requests pytest
.venv/bin/python -m pytest tests/ -q
```

- `tests/test_recipes.py` — offline, parses real captured fixtures
- `tests/test_live.py` — 9 cautious live requests against nefisyemektarifleri.com
- `tests/test_notebook.py` — offline, notebook tools (no network)

## License

MIT

---

Built by [Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
