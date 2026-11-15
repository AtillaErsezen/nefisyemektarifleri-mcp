"""Daily smoke probe (CI): homepage + one search must answer 200.

Run with:  python tests/smoke_live.py
Exit 0 = site reachable, exit 1 = blocked/error (visible in CI).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nefisyemektarifleri_mcp import http, recipes as R


def main() -> int:
    try:
        home = http.fetch_home()
        assert "Nefis Yemek Tarifleri" in home, "homepage title missing"
        search = R.parse_search_page(http.fetch_search_page("mercimek"))
        assert search["total_results"] and search["total_results"] > 1000
        assert len(search["recipes"]) >= 10
        print(
            f"SMOKE OK: home 200, search 'mercimek' -> "
            f"{search['total_results']} results, {len(search['recipes'])} cards"
        )
        return 0
    except Exception as e:  # noqa: BLE001 — smoke must report, not crash
        print(f"SMOKE FAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
