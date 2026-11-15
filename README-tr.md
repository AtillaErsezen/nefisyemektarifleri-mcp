# nefisyemektarifleri-mcp 🇹🇷

mcp-name: io.github.mohammad-abbasi-sh/nefisyemektarifleri-mcp

**Nefis Yemek Tarifleri** (nefisyemektarifleri.com) için resmi olmayan, **salt okunur** MCP sunucusu — Türkiye'nin en büyük tarif sitesi: her sorguda 14.000'den fazla tarifte arama, tam tarif detayları (miktarlı malzemeler, adımlar, püf noktaları, süreler, porsiyon, puan, besin değerleri), tam tarif kategori ağacı, popüler/trend/en yeni sıralamalı kategori listeleri, en çok yapılan tarifler ve günlük "Bugün Ne Pişirsem?" menüsü.

> "Turkey MCP factory" (Sepehr tarzı hat) parçasıdır. Nefis Yemek Tarifleri ile bağlantısı yoktur.

## Yapay zekâ ajanları için

MCP istemci yapılandırmanıza ekleyin (stdio):

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

Veya yerel çalıştırın: `python -m nefisyemektarifleri_mcp.server` (`mcp<2`, `curl-cffi`, `requests` gerekir).

## Araçlar

| Araç | Açıklama |
|------|----------|
| `nefis_search_recipes` | Yemek/malzeme ile tarif ara — `query`, `limit` (1..30), `page` (1..20) |
| `nefis_get_recipe` | Tam tarif — tam URL veya yalın slug (örn. `mercimek-corbasi-tarifi`) |
| `nefis_list_categories` | Tam kategori ağacı (24 ana kategori, 74 alt kategori) |
| `nefis_category_recipes` | Bir kategorideki tarifler — `category` slug/URL, `limit`, `page`, `sort` (popular/trending/newest) |
| `nefis_trending` | En çok yapılan tarifler ("En Çok Yapılanlar", 24 tarif) |
| `nefis_daily_menu` | Günün "Bugün Ne Pişirsem?" menüsü (25 tarif) |
| `nefis_health` | Erişilebilirlik kontrolü (ok / blocked / error) |

Örnek çıktı (`nefis_search_recipes` / "mercimek"):

```json
{"query": "mercimek", "total_results": 14694,
 "recipes": [{"title": "Mercimek Köftesi Nasıl Yapılır? (videolu)",
   "serves": "4-6", "prep_time": "50dk", "cook_time": "30dk",
   "author": "Elif Atalar", "saved_count": 385000, "comment_count": 2985}]}
```

Örnek çıktı (`nefis_get_recipe` / "mercimek-corbasi-tarifi"):

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

Notlar:
- Arama sitenin kendi `/ara/` sayfasıdır — Cloudflare, Referer göndermeyen istekleri reddeder; bu yüzden her istekte site Referer olarak gönderilir. Aktarım, Chrome TLS taklidi ve düz requests yedeği kullanır.
- Listeler WordPress tarzı sayfalanır (`/page/2/`); site `?sayfa=N` parametresini yok sayar (sessizce 1. sayfayı döndürür), sunucu bunu hiç kullanmaz.
- Süreler Türkçe kısaltmadır (`15dk`); porsiyonlar Türkçedir (`6-8 kişilik`); deftere eklenme/yorum sayıları Türkçe kısaltmalardan çevrilir (`385bin` → 385000).
- Veri: nefisyemektarifleri.com herkese açık sayfaları — anahtar yok, giriş yok, salt okunur.

## Geliştirme

```bash
python3 -m venv .venv && .venv/bin/pip install "mcp<2" curl-cffi requests pytest
.venv/bin/python -m pytest tests/ -q
```

- `tests/test_recipes.py` — çevrimdışı, gerçek kaydedilmiş örnekleri ayrıştırır
- `tests/test_live.py` — nefisyemektarifleri.com'a 9 temkinli canlı istek

## Lisans

MIT

---

Built by [Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
