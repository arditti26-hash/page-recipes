#!/usr/bin/env python3
"""Mamacita's Recipes - Arditti Kitchen (cloud deployment with Google Sheets sync)"""

import os, json, re, base64, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.request, urllib.error

# ── Env config ────────────────────────────────────────────────────────────────
PORT             = int(os.environ.get("PORT", 8080))
GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO      = os.environ.get("GITHUB_REPO", "")          # e.g. arditti26-hash/page-recipes
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "")     # CSV export URL
CACHE_PATH       = "recipes-cache.json"

# ── In-memory recipe cache ────────────────────────────────────────────────────
_cache_lock  = threading.Lock()
_recipes_mem = None   # list of recipe dicts, None = not loaded yet
_syncing     = False

# ── GitHub helpers ─────────────────────────────────────────────────────────────

def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "mamacitas-recipes/1.0",
    }

def github_get_cache():
    """Fetch recipes-cache.json from GitHub. Returns (data_dict, sha)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CACHE_PATH}"
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        meta = json.loads(r.read())
    content = base64.b64decode(meta["content"]).decode("utf-8")
    return json.loads(content), meta["sha"]

def github_put_cache(data, sha, message="Sync recipes"):
    """Commit updated recipes-cache.json to GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CACHE_PATH}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(json.dumps(data, indent=2).encode()).decode(),
        "sha": sha,
    }).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        **_gh_headers(), "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ── Google Sheet helpers ───────────────────────────────────────────────────────

def get_sheet_urls():
    """Read URLs from Google Sheet CSV export."""
    req = urllib.request.Request(GOOGLE_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("utf-8", errors="replace")
    urls = []
    for line in text.strip().splitlines():
        cell = line.strip().strip('"').strip()
        if cell.startswith("http"):
            urls.append(cell)
    return urls

# ── Recipe fetching (stdlib only) ─────────────────────────────────────────────

def _find_schema_recipe(data):
    if not data:
        return None
    if isinstance(data, list):
        for item in data:
            found = _find_schema_recipe(item)
            if found:
                return found
    if isinstance(data, dict):
        if data.get("@type") == "Recipe":
            return data
        if "@graph" in data:
            return _find_schema_recipe(data["@graph"])
    return None

def _clean(v):
    if not v:
        return ""
    if isinstance(v, list):
        return [_clean(i) for i in v if _clean(i)]
    if isinstance(v, dict):
        return v.get("text") or v.get("name") or ""
    return re.sub(r"<[^>]+>", "", str(v)).strip()

def _parse_schema(r, url):
    instructions = []
    def flatten(arr):
        for item in arr:
            if isinstance(item, str):
                t = re.sub(r"<[^>]+>", "", item).strip()
                if t: instructions.append(t)
            elif isinstance(item, dict):
                if item.get("@type") == "HowToStep":
                    t = _clean(item.get("text") or item.get("name", ""))
                    if t: instructions.append(t)
                elif item.get("@type") == "HowToSection":
                    if item.get("name"): instructions.append(f'**{item["name"]}**')
                    flatten(item.get("itemListElement", []))
    raw = r.get("recipeInstructions", [])
    if isinstance(raw, list):
        flatten(raw)
    elif isinstance(raw, str):
        instructions.extend([l for l in raw.splitlines() if l.strip()])
    img = r.get("image", "")
    if isinstance(img, list):
        img = img[0].get("url", img[0]) if img else ""
    elif isinstance(img, dict):
        img = img.get("url", "")
    ingr = r.get("recipeIngredient", [])
    return {
        "title":       _clean(r.get("name")) or "Untitled Recipe",
        "description": _clean(r.get("description")) or "",
        "ingredients": [_clean(i) for i in ingr] if isinstance(ingr, list) else [],
        "instructions": [i for i in instructions if i],
        "image":       img or "",
        "url":         url,
        "source":      "schema",
    }

def fetch_recipe(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", errors="replace")

    for block in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        body, re.DOTALL | re.IGNORECASE
    ):
        try:
            data = json.loads(block.strip())
            schema = _find_schema_recipe(data)
            if schema:
                recipe = _parse_schema(schema, url)
                if not recipe["image"]:
                    m = re.search(r'<meta[^>]*(?:property=["\']og:image["\']|name=["\']twitter:image["\'])[^>]*content=["\'](.*?)["\']', body)
                    if m: recipe["image"] = m.group(1)
                return recipe
        except Exception:
            pass

    # Fallback: OG tags
    t = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', body)
    i = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', body)
    title = t.group(1) if t else url
    return {
        "title": title, "description": "", "ingredients": [], "instructions": [],
        "image": i.group(1) if i else "", "url": url, "source": "scrape"
    }

# ── Cache loading ─────────────────────────────────────────────────────────────

def load_recipes():
    global _recipes_mem
    with _cache_lock:
        if _recipes_mem is not None:
            return _recipes_mem
    try:
        data, _ = github_get_cache()
        recipes = []
        for url, r in (data.get("recipes") or {}).items():
            if r.get("source") != "error":
                recipes.append({**r, "url": url})
        for r in (data.get("manualRecipes") or []):
            recipes.append({**r, "isManual": True, "source": "manual"})
        with _cache_lock:
            _recipes_mem = recipes
        print(f"Loaded {len(recipes)} recipes from GitHub")
        return recipes
    except Exception as e:
        print(f"Could not load from GitHub: {e}")
        with _cache_lock:
            _recipes_mem = []
        return []

# ── Sync logic ────────────────────────────────────────────────────────────────

def do_sync():
    global _syncing, _recipes_mem
    if _syncing:
        return {"status": "already_syncing"}
    if not GITHUB_TOKEN or not GITHUB_REPO or not GOOGLE_SHEET_URL:
        return {"status": "error", "message": "Missing env vars (GITHUB_TOKEN, GITHUB_REPO, GOOGLE_SHEET_URL)"}
    _syncing = True
    try:
        sheet_urls = get_sheet_urls()
        data, sha  = github_get_cache()
        existing   = set(data.get("recipes", {}).keys())
        new_urls   = [u for u in sheet_urls if u not in existing]

        fetched, failed = 0, 0
        for url in new_urls:
            try:
                print(f"Fetching: {url}")
                recipe = fetch_recipe(url)
                data.setdefault("recipes", {})[url] = recipe
                fetched += 1
            except Exception as e:
                print(f"Failed {url}: {e}")
                data.setdefault("recipes", {})[url] = {
                    "title": url, "url": url, "error": str(e),
                    "ingredients": [], "instructions": [], "source": "error"
                }
                failed += 1

        if new_urls:
            _, sha = github_get_cache()   # refresh SHA before commit
            github_put_cache(data, sha, f"Sync: +{fetched} recipes")

        # Refresh in-memory cache
        recipes = []
        for url, r in data.get("recipes", {}).items():
            if r.get("source") != "error":
                recipes.append({**r, "url": url})
        with _cache_lock:
            _recipes_mem = recipes

        return {"status": "done", "new": len(new_urls), "fetched": fetched, "failed": failed}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        _syncing = False

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"UTF-8\" />\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n  <title>Mamacita's Recipes</title>\n  <style>\n    * { box-sizing: border-box; margin: 0; padding: 0; }\n\n    body {\n      font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;\n      background: #eef4fb;\n      color: #1a2a3a;\n      min-height: 100vh;\n    }\n\n    /* ── Header ── */\n    .header {\n      background: #fff;\n      border-bottom: 1px solid #cde0f5;\n      padding: 14px 28px;\n      position: sticky;\n      top: 0;\n      z-index: 100;\n    }\n\n    .header-top {\n      display: flex;\n      align-items: center;\n      gap: 16px;\n      margin-bottom: 10px;\n    }\n\n    .branding { line-height: 1.15; }\n\n    .branding h1 {\n      font-size: 20px;\n      font-weight: 800;\n      color: #0d3b6e;\n      letter-spacing: -0.4px;\n    }\n\n    .branding .sub {\n      font-size: 11px;\n      font-weight: 600;\n      letter-spacing: 1.2px;\n      text-transform: uppercase;\n      color: #4a90d9;\n    }\n\n    .header-controls {\n      display: flex;\n      align-items: center;\n      gap: 10px;\n      flex: 1;\n    }\n\n    .search-wrap {\n      flex: 1;\n      position: relative;\n      max-width: 480px;\n    }\n\n    .search-wrap svg {\n      position: absolute;\n      left: 13px;\n      top: 50%;\n      transform: translateY(-50%);\n      color: #7aaad4;\n      pointer-events: none;\n    }\n\n    #search {\n      width: 100%;\n      padding: 10px 14px 10px 40px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      font-size: 14px;\n      background: #f4f8fd;\n      outline: none;\n      transition: border-color 0.15s, background 0.15s;\n      color: #1a2a3a;\n    }\n\n    #search:focus { border-color: #1a6fba; background: #fff; }\n    #search::placeholder { color: #9ab8d8; }\n\n    .filter-wrap {\n      position: relative;\n    }\n\n    .filter-wrap svg {\n      position: absolute;\n      left: 11px;\n      top: 50%;\n      transform: translateY(-50%);\n      color: #f0a500;\n      pointer-events: none;\n    }\n\n    #ratingFilter {\n      padding: 10px 14px 10px 32px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      font-size: 13px;\n      font-weight: 500;\n      background: #f4f8fd;\n      color: #1a2a3a;\n      outline: none;\n      cursor: pointer;\n      transition: border-color 0.15s;\n      appearance: none;\n      -webkit-appearance: none;\n      pr: 28px;\n    }\n\n    #ratingFilter:focus { border-color: #1a6fba; }\n\n    .sync-btn {\n      display: flex;\n      align-items: center;\n      gap: 7px;\n      padding: 9px 15px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 9px;\n      background: #fff;\n      font-size: 13px;\n      font-weight: 600;\n      color: #1a6fba;\n      cursor: pointer;\n      white-space: nowrap;\n      transition: all 0.15s;\n    }\n\n    .sync-btn:hover { border-color: #1a6fba; background: #eef4fb; }\n    .sync-btn.syncing { opacity: 0.6; pointer-events: none; }\n    .sync-btn.syncing .sync-icon { animation: spin 1s linear infinite; }\n\n    @keyframes spin { to { transform: rotate(360deg); } }\n\n    /* ── Stats bar ── */\n    .stats {\n      padding: 8px 28px;\n      font-size: 12px;\n      color: #6a8fad;\n      display: flex;\n      gap: 12px;\n      align-items: center;\n    }\n\n    .stats .dot { width: 6px; height: 6px; border-radius: 50%; background: #4caf50; display: inline-block; }\n\n    /* ── Grid ── */\n    .grid {\n      display: grid;\n      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));\n      gap: 18px;\n      padding: 18px 28px 48px;\n    }\n\n    .card {\n      background: #fff;\n      border: 1px solid #d5e8f5;\n      border-radius: 14px;\n      overflow: hidden;\n      cursor: pointer;\n      transition: box-shadow 0.15s, transform 0.15s;\n      display: flex;\n      flex-direction: column;\n    }\n\n    .card:hover {\n      box-shadow: 0 6px 24px rgba(26, 111, 186, 0.13);\n      transform: translateY(-2px);\n    }\n\n    .card-img {\n      width: 100%;\n      height: 155px;\n      background: #deeaf8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      font-size: 36px;\n      overflow: hidden;\n      flex-shrink: 0;\n      position: relative;\n    }\n\n    .card-img img {\n      width: 100%;\n      height: 100%;\n      object-fit: cover;\n      display: block;\n    }\n\n    .card-body {\n      padding: 13px 14px 10px;\n      flex: 1;\n      display: flex;\n      flex-direction: column;\n      gap: 6px;\n    }\n\n    .card-title {\n      font-size: 14px;\n      font-weight: 600;\n      line-height: 1.35;\n      color: #0d3b6e;\n      display: -webkit-box;\n      -webkit-line-clamp: 2;\n      -webkit-box-orient: vertical;\n      overflow: hidden;\n    }\n\n    .card-meta {\n      font-size: 11px;\n      color: #7aaad4;\n      display: flex;\n      gap: 7px;\n      flex-wrap: wrap;\n    }\n\n    .card-meta .tag {\n      background: #eef4fb;\n      padding: 2px 8px;\n      border-radius: 20px;\n      color: #4a80b0;\n    }\n\n    .card-meta .tag.manual { background: #fff8e1; color: #b07d00; }\n    .card-meta .tag.error { background: #fdeaea; color: #c0392b; }\n\n    /* ── Rating row on card ── */\n    .card-rating {\n      display: flex;\n      align-items: center;\n      gap: 6px;\n      padding: 8px 14px 12px;\n      border-top: 1px solid #edf4fb;\n      flex-shrink: 0;\n    }\n\n    .rating-label {\n      font-size: 11px;\n      color: #9ab8d8;\n      font-weight: 500;\n      width: 30px;\n      flex-shrink: 0;\n    }\n\n    .rating-dots {\n      display: flex;\n      gap: 3px;\n    }\n\n    .rating-dot {\n      width: 18px;\n      height: 18px;\n      border-radius: 50%;\n      border: 1.5px solid #c5daf0;\n      background: #f4f8fd;\n      cursor: pointer;\n      font-size: 9px;\n      font-weight: 700;\n      color: #9ab8d8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      transition: all 0.1s;\n      flex-shrink: 0;\n    }\n\n    .rating-dot:hover,\n    .rating-dot.active {\n      background: #1a6fba;\n      border-color: #1a6fba;\n      color: #fff;\n    }\n\n    .rating-dot.active { box-shadow: 0 0 0 2px #a8cff0; }\n\n    .rating-score {\n      font-size: 12px;\n      font-weight: 700;\n      color: #1a6fba;\n      margin-left: 4px;\n    }\n\n    .empty {\n      grid-column: 1/-1;\n      text-align: center;\n      padding: 60px 20px;\n      color: #9ab8d8;\n    }\n\n    /* ── Modal ── */\n    .overlay {\n      display: none;\n      position: fixed;\n      inset: 0;\n      background: rgba(10, 30, 60, 0.5);\n      z-index: 200;\n      align-items: flex-start;\n      justify-content: center;\n      padding: 32px 16px;\n      overflow-y: auto;\n    }\n\n    .overlay.open { display: flex; }\n\n    .modal {\n      background: #fff;\n      border-radius: 18px;\n      width: 100%;\n      max-width: 740px;\n      overflow: hidden;\n      position: relative;\n      margin: auto;\n    }\n\n    .modal-hero {\n      width: 100%;\n      height: 250px;\n      background: #deeaf8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      font-size: 64px;\n      overflow: hidden;\n    }\n\n    .modal-hero img { width: 100%; height: 100%; object-fit: cover; display: block; }\n\n    .modal-close {\n      position: absolute;\n      top: 14px;\n      right: 14px;\n      width: 34px;\n      height: 34px;\n      border-radius: 50%;\n      background: rgba(10,30,60,0.45);\n      border: none;\n      color: #fff;\n      font-size: 17px;\n      cursor: pointer;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n    }\n\n    .modal-body { padding: 26px 30px 40px; }\n\n    .modal-header-row {\n      display: flex;\n      align-items: flex-start;\n      justify-content: space-between;\n      gap: 16px;\n      margin-bottom: 6px;\n    }\n\n    .modal-title {\n      font-size: 24px;\n      font-weight: 800;\n      line-height: 1.25;\n      color: #0d3b6e;\n      letter-spacing: -0.3px;\n    }\n\n    .modal-rating-badge {\n      flex-shrink: 0;\n      background: #eef4fb;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      padding: 6px 12px;\n      text-align: center;\n      min-width: 56px;\n    }\n\n    .modal-rating-badge .badge-num {\n      font-size: 22px;\n      font-weight: 800;\n      color: #1a6fba;\n      line-height: 1;\n    }\n\n    .modal-rating-badge .badge-label {\n      font-size: 9px;\n      color: #9ab8d8;\n      font-weight: 600;\n      letter-spacing: 0.5px;\n      text-transform: uppercase;\n    }\n\n    .modal-rating-badge.unrated .badge-num { color: #c5daf0; font-size: 13px; font-weight: 500; }\n\n    .modal-source {\n      font-size: 12px;\n      color: #9ab8d8;\n      margin-bottom: 18px;\n    }\n\n    .modal-source a { color: #1a6fba; text-decoration: none; }\n    .modal-source a:hover { text-decoration: underline; }\n\n    .modal-description {\n      font-size: 14px;\n      color: #4a6a8a;\n      line-height: 1.65;\n      margin-bottom: 24px;\n    }\n\n    /* Modal rating row */\n    .modal-rate-row {\n      display: flex;\n      align-items: center;\n      gap: 10px;\n      margin-bottom: 24px;\n      padding: 12px 16px;\n      background: #f4f8fd;\n      border-radius: 10px;\n      border: 1px solid #dceaf8;\n    }\n\n    .modal-rate-row .rate-label {\n      font-size: 12px;\n      font-weight: 600;\n      color: #4a80b0;\n      white-space: nowrap;\n    }\n\n    .modal-rate-dots {\n      display: flex;\n      gap: 4px;\n      flex-wrap: wrap;\n    }\n\n    .modal-rate-dot {\n      width: 28px;\n      height: 28px;\n      border-radius: 50%;\n      border: 1.5px solid #c5daf0;\n      background: #fff;\n      cursor: pointer;\n      font-size: 11px;\n      font-weight: 700;\n      color: #7aaad4;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      transition: all 0.12s;\n    }\n\n    .modal-rate-dot:hover { background: #deeaf8; border-color: #1a6fba; color: #1a6fba; }\n    .modal-rate-dot.active { background: #1a6fba; border-color: #1a6fba; color: #fff; box-shadow: 0 0 0 3px #a8cff0; }\n\n    .modal-columns {\n      display: grid;\n      grid-template-columns: 1fr 1.6fr;\n      gap: 30px;\n    }\n\n    @media (max-width: 600px) { .modal-columns { grid-template-columns: 1fr; } }\n\n    .section-label {\n      font-size: 10px;\n      font-weight: 700;\n      letter-spacing: 1px;\n      text-transform: uppercase;\n      color: #7aaad4;\n      margin-bottom: 12px;\n    }\n\n    .ingredients-list {\n      list-style: none;\n      display: flex;\n      flex-direction: column;\n      gap: 7px;\n    }\n\n    .ingredients-list li {\n      font-size: 13px;\n      line-height: 1.5;\n      padding-left: 14px;\n      position: relative;\n      color: #2a3f5a;\n    }\n\n    .ingredients-list li::before {\n      content: '';\n      position: absolute;\n      left: 0;\n      top: 7px;\n      width: 5px;\n      height: 5px;\n      border-radius: 50%;\n      background: #1a6fba;\n    }\n\n    .ingredients-list li.section-header {\n      font-size: 10px;\n      font-weight: 700;\n      letter-spacing: 0.8px;\n      text-transform: uppercase;\n      color: #7aaad4;\n      padding-left: 0;\n      margin-top: 10px;\n    }\n    .ingredients-list li.section-header::before { display: none; }\n\n    .instructions-list {\n      list-style: none;\n      display: flex;\n      flex-direction: column;\n      gap: 14px;\n    }\n\n    .instructions-list li {\n      font-size: 13px;\n      line-height: 1.65;\n      padding-left: 36px;\n      position: relative;\n      color: #2a3f5a;\n    }\n\n    .instructions-list li::before {\n      content: attr(data-n);\n      position: absolute;\n      left: 0;\n      top: 0;\n      width: 24px;\n      height: 24px;\n      border-radius: 50%;\n      background: #1a6fba;\n      color: #fff;\n      font-size: 11px;\n      font-weight: 700;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n    }\n\n    .step-section {\n      font-size: 10px;\n      font-weight: 700;\n      text-transform: uppercase;\n      letter-spacing: 0.8px;\n      color: #7aaad4;\n      padding-left: 0 !important;\n      margin-top: 8px;\n    }\n\n    .step-section::before { display: none !important; }\n    .no-content { font-size: 13px; color: #b0c8e0; font-style: italic; }\n  </style>\n</head>\n<body>\n\n  <div class=\"header\">\n    <div class=\"header-top\">\n      <div class=\"branding\">\n        <h1>Mamacita's Recipes</h1>\n        <div class=\"sub\">Arditti Kitchen</div>\n      </div>\n    </div>\n    <div class=\"header-controls\">\n      <div class=\"search-wrap\">\n        <svg width=\"15\" height=\"15\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" viewBox=\"0 0 24 24\">\n          <circle cx=\"11\" cy=\"11\" r=\"8\"/><path d=\"m21 21-4.35-4.35\"/>\n        </svg>\n        <input id=\"search\" type=\"text\" placeholder=\"Search recipes, ingredients...\" autocomplete=\"off\" />\n      </div>\n      <div class=\"filter-wrap\">\n        <svg width=\"13\" height=\"13\" viewBox=\"0 0 24 24\" fill=\"currentColor\">\n          <path d=\"M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z\"/>\n        </svg>\n        <select id=\"ratingFilter\" onchange=\"applyFilters()\">\n          <option value=\"0\">All ratings</option>\n          <option value=\"1\">★ 1+</option>\n          <option value=\"2\">★ 2+</option>\n          <option value=\"3\">★ 3+</option>\n          <option value=\"4\">★ 4+</option>\n          <option value=\"5\">★ 5+</option>\n          <option value=\"6\">★ 6+</option>\n          <option value=\"7\">★ 7+</option>\n          <option value=\"8\">★ 8+</option>\n          <option value=\"9\">★ 9+</option>\n          <option value=\"10\">★ 10</option>\n        </select>\n      </div>\n      <div class=\"filter-wrap\">\n        <svg width=\"13\" height=\"13\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" style=\"color:#4a90d9\">\n          <path d=\"M18 8h1a4 4 0 0 1 0 8h-1\"/><path d=\"M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z\"/><line x1=\"6\" y1=\"1\" x2=\"6\" y2=\"4\"/><line x1=\"10\" y1=\"1\" x2=\"10\" y2=\"4\"/><line x1=\"14\" y1=\"1\" x2=\"14\" y2=\"4\"/>\n        </svg>\n        <select id=\"proteinFilter\" onchange=\"applyFilters()\">\n          <option value=\"\">All proteins</option>\n          <option value=\"chicken\">&#x1F413; Chicken</option>\n          <option value=\"turkey\">&#x1F983; Turkey</option>\n          <option value=\"beef\">&#x1F969; Beef</option>\n          <option value=\"salmon\">&#x1F41F; Salmon / Fish</option>\n          <option value=\"shrimp\">&#x1F364; Shrimp</option>\n          <option value=\"tofu\">&#x1FAD8; Tofu</option>\n          <option value=\"chickpea\">&#x1FAD8; Chickpeas / Beans</option>\n          <option value=\"vegetarian\">&#x1F966; Vegetarian</option>\n        </select>\n      </div>\n      <button class=\"sync-btn\" id=\"syncBtn\" onclick=\"syncNow()\">\n        <svg class=\"sync-icon\" width=\"13\" height=\"13\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.2\" viewBox=\"0 0 24 24\">\n          <path d=\"M23 4v6h-6M1 20v-6h6\"/><path d=\"M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15\"/>\n        </svg>\n        Sync Notes\n      </button>\n    </div>\n  </div>\n\n  <div class=\"stats\" id=\"stats\">Loading recipes…</div>\n  <div class=\"grid\" id=\"grid\"></div>\n\n  <!-- Modal -->\n  <div class=\"overlay\" id=\"overlay\" onclick=\"closeModal(event)\">\n    <div class=\"modal\" id=\"modal\">\n      <div class=\"modal-hero\" id=\"modalHero\">&#x1F37D;️</div>\n      <button class=\"modal-close\" onclick=\"closeOverlay()\">✕</button>\n      <div class=\"modal-body\">\n        <div class=\"modal-header-row\">\n          <div class=\"modal-title\" id=\"modalTitle\"></div>\n          <div class=\"modal-rating-badge unrated\" id=\"modalBadge\">\n            <div class=\"badge-num\" id=\"modalBadgeNum\">—</div>\n            <div class=\"badge-label\">/ 10</div>\n          </div>\n        </div>\n        <div class=\"modal-source\" id=\"modalSource\"></div>\n        <div class=\"modal-description\" id=\"modalDesc\"></div>\n        <div class=\"modal-rate-row\">\n          <span class=\"rate-label\">Your rating:</span>\n          <div class=\"modal-rate-dots\" id=\"modalRateDots\"></div>\n        </div>\n        <div class=\"modal-columns\">\n          <div>\n            <div class=\"section-label\">Ingredients</div>\n            <ul class=\"ingredients-list\" id=\"modalIngredients\"></ul>\n          </div>\n          <div>\n            <div class=\"section-label\">Instructions</div>\n            <ol class=\"instructions-list\" id=\"modalInstructions\"></ol>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <script>\n    let allRecipes = [];\n    let ratings = {};\n    let currentRecipeKey = null;\n    let syncAvailable = false;\n\n    const RATINGS_KEY = 'mamacita_ratings';\n\n    function loadRatingsFromStorage() {\n      try { return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}'); } catch(e) { return {}; }\n    }\n\n    function saveRatingsToStorage(r) {\n      localStorage.setItem(RATINGS_KEY, JSON.stringify(r));\n    }\n\n    function recipeKey(r) {\n      return r.url || r.title || '';\n    }\n\n    async function loadData() {\n      const [recipesRes, configRes] = await Promise.all([\n        fetch('/api/recipes'),\n        fetch('/api/config'),\n      ]);\n      allRecipes = await recipesRes.json();\n      const config = await configRes.json();\n      syncAvailable = config.syncAvailable;\n      ratings = loadRatingsFromStorage();\n\n      allRecipes.sort((a, b) => {\n        const aHas = a.ingredients.length + a.instructions.length;\n        const bHas = b.ingredients.length + b.instructions.length;\n        if (aHas !== bHas) return bHas - aHas;\n        return (a.title || '').localeCompare(b.title || '');\n      });\n\n      applyFilters();\n      updateStats();\n    }\n\n    function updateStats() {\n      const total = allRecipes.length;\n      const rated = Object.keys(ratings).length;\n      document.getElementById('stats').innerHTML =\n        `<span class=\"dot\"></span> ${total} recipes &nbsp;·&nbsp; ${rated} rated`;\n    }\n\n    const PROTEIN_KEYWORDS = {\n      chicken:    ['chicken'],\n      turkey:     ['turkey'],\n      beef:       ['beef', 'steak', 'ground beef', 'pot roast', 'braised beef'],\n      salmon:     ['salmon', 'tuna', 'halibut', 'cod', 'fish', 'halloumi'],\n      shrimp:     ['shrimp', 'prawn'],\n      tofu:       ['tofu'],\n      chickpea:   ['chickpea', 'black bean', 'lentil', 'cannellini', 'white bean', 'great northern', 'adzuki', 'bean'],\n    };\n\n    function detectProtein(r) {\n      const text = [r.title || '', ...(r.ingredients || [])].join(' ').toLowerCase();\n      const found = new Set();\n      for (const [type, words] of Object.entries(PROTEIN_KEYWORDS)) {\n        if (words.some(w => text.includes(w))) found.add(type);\n      }\n      // vegetarian = no animal proteins\n      const animalProteins = ['chicken','turkey','beef','salmon','shrimp'];\n      if (!animalProteins.some(p => found.has(p))) found.add('vegetarian');\n      return found;\n    }\n\n    function applyFilters() {\n      const q = document.getElementById('search').value.toLowerCase().trim();\n      const minRating = parseInt(document.getElementById('ratingFilter').value) || 0;\n      const protein = document.getElementById('proteinFilter').value;\n\n      let filtered = allRecipes.filter(r => {\n        if (minRating > 0) {\n          const score = ratings[recipeKey(r)];\n          if (!score || score < minRating) return false;\n        }\n        if (protein) {\n          if (!detectProtein(r).has(protein)) return false;\n        }\n        if (!q) return true;\n        const haystack = [\n          r.title || '',\n          r.description || '',\n          ...(r.ingredients || []),\n          ...(r.instructions || []),\n          r.url || '',\n        ].join(' ').toLowerCase();\n        return q.split(' ').every(w => haystack.includes(w));\n      });\n\n      renderGrid(filtered);\n    }\n\n    function renderGrid(recipes) {\n      const grid = document.getElementById('grid');\n      if (!recipes.length) {\n        grid.innerHTML = `<div class=\"empty\"><div style=\"font-size:40px;margin-bottom:10px\">&#x1F50D;</div><div>No recipes found</div></div>`;\n        return;\n      }\n      grid.innerHTML = recipes.map((r, i) => {\n        const key = recipeKey(r);\n        const score = ratings[key];\n        const tag = r.isManual ? 'manual' : r.source === 'error' ? 'error' : '';\n        const tagLabel = r.isManual ? 'Note' : r.source === 'error' ? 'Error' : r.ingredients.length > 0 ? `${r.ingredients.length} ingr.` : 'Link only';\n        const domain = r.url ? (() => { try { return new URL(r.url).hostname.replace('www.',''); } catch(e) { return ''; }})() : '';\n        const imgHtml = r.image\n          ? `<img src=\"${esc(r.image)}\" onerror=\"this.style.display='none'\" loading=\"lazy\" />`\n          : '&#x1F37D;️';\n\n        const dots = Array.from({length:10},(_,n)=>{\n          const val = n+1;\n          const active = score && score >= val ? 'active' : '';\n          return `<div class=\"rating-dot ${active}\" data-val=\"${val}\" onclick=\"rateFromCard(event,'${esc(key)}',${val})\" title=\"${val}/10\">${val}</div>`;\n        }).join('');\n\n        return `<div class=\"card\" onclick=\"openRecipeByKey('${esc(key)}')\">\n          <div class=\"card-img\">${imgHtml}</div>\n          <div class=\"card-body\">\n            <div class=\"card-title\">${esc(r.title || r.url || 'Untitled')}</div>\n            <div class=\"card-meta\">\n              ${domain ? `<span class=\"tag\">${esc(domain)}</span>` : ''}\n              <span class=\"tag ${tag}\">${tagLabel}</span>\n            </div>\n          </div>\n          <div class=\"card-rating\">\n            <div class=\"rating-label\">${score ? `${score}/10` : 'Rate'}</div>\n            <div class=\"rating-dots\">${dots}</div>\n          </div>\n        </div>`;\n      }).join('');\n    }\n\n    function rateFromCard(e, key, val) {\n      e.stopPropagation();\n      saveRating(key, val);\n    }\n\n    function saveRating(key, val) {\n      const current = ratings[key];\n      const newVal = current === val ? null : val;\n      if (newVal === null) { delete ratings[key]; } else { ratings[key] = newVal; }\n      saveRatingsToStorage(ratings);\n      if (currentRecipeKey === key) renderModalRating(key);\n      applyFilters();\n      updateStats();\n    }\n\n    function openRecipeByKey(key) {\n      const r = allRecipes.find(x => recipeKey(x) === key);\n      if (!r) return;\n      currentRecipeKey = key;\n\n      document.getElementById('modalTitle').textContent = r.title || 'Untitled';\n\n      const src = document.getElementById('modalSource');\n      src.innerHTML = r.url\n        ? `<a href=\"${esc(r.url)}\" target=\"_blank\" rel=\"noopener\">${esc(r.url)}</a>`\n        : '<em>From your Apple Notes</em>';\n\n      const desc = document.getElementById('modalDesc');\n      desc.textContent = r.description || '';\n      desc.style.display = r.description ? 'block' : 'none';\n\n      const hero = document.getElementById('modalHero');\n      hero.innerHTML = r.image\n        ? `<img src=\"${esc(r.image)}\" onerror=\"this.style.display='none'\" />`\n        : '&#x1F37D;️';\n\n      const ingList = document.getElementById('modalIngredients');\n      ingList.innerHTML = r.ingredients.length\n        ? r.ingredients.map(i => {\n            if (i.startsWith('—') && i.endsWith('—')) {\n              return `<li class=\"section-header\">${esc(i.replace(/^—\\s*|\\s*—$/g,''))}</li>`;\n            }\n            return `<li>${esc(i)}</li>`;\n          }).join('')\n        : `<p class=\"no-content\">No ingredients listed</p>`;\n\n      const insList = document.getElementById('modalInstructions');\n      if (!r.instructions.length) {\n        insList.innerHTML = `<p class=\"no-content\">No instructions available</p>`;\n      } else {\n        let n = 0;\n        insList.innerHTML = r.instructions.map(step => {\n          if (step.startsWith('**') && step.endsWith('**')) {\n            return `<li class=\"step-section\">${esc(step.replace(/\\*\\*/g,''))}</li>`;\n          }\n          n++;\n          return `<li data-n=\"${n}\">${esc(step)}</li>`;\n        }).join('');\n      }\n\n      renderModalRating(key);\n      document.getElementById('overlay').classList.add('open');\n      document.body.style.overflow = 'hidden';\n    }\n\n    function renderModalRating(key) {\n      const score = ratings[key];\n      const badge = document.getElementById('modalBadge');\n      const badgeNum = document.getElementById('modalBadgeNum');\n      if (score) {\n        badge.classList.remove('unrated');\n        badgeNum.textContent = score;\n      } else {\n        badge.classList.add('unrated');\n        badgeNum.textContent = '—';\n      }\n      const dotsEl = document.getElementById('modalRateDots');\n      dotsEl.innerHTML = Array.from({length:10},(_,n) => {\n        const val = n+1;\n        const active = score === val ? 'active' : '';\n        return `<div class=\"modal-rate-dot ${active}\" onclick=\"saveRating('${esc(key)}',${val})\">${val}</div>`;\n      }).join('');\n    }\n\n    function closeOverlay() {\n      document.getElementById('overlay').classList.remove('open');\n      document.body.style.overflow = '';\n      currentRecipeKey = null;\n    }\n\n    function closeModal(e) {\n      if (e.target === document.getElementById('overlay')) closeOverlay();\n    }\n\n    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlay(); });\n\n    document.getElementById('search').addEventListener('input', applyFilters);\n\n    async function syncNow() {\n      const btn = document.getElementById('syncBtn');\n      btn.classList.add('syncing');\n      btn.lastChild.textContent = ' Syncing…';\n      try {\n        const res = await fetch('/api/sync', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });\n        const data = await res.json();\n        await loadData();\n        btn.lastChild.textContent = ` Done (${data.fetched||0} new)`;\n        setTimeout(() => { btn.lastChild.textContent = ' Sync Recipes'; }, 3000);\n      } catch(e) {\n        btn.lastChild.textContent = ' Error';\n        setTimeout(() => { btn.lastChild.textContent = ' Sync Recipes'; }, 3000);\n      }\n      btn.classList.remove('syncing');\n    }\n\n    function esc(str) {\n      return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');\n    }\n\n    loadData();\n  </script>\n</body>\n</html>\n"

# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def send_body(self, body, ct="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/recipes":
            self.send_body(json.dumps(load_recipes()), "application/json")
        elif path == "/api/config":
            self.send_body(json.dumps({"syncAvailable": bool(GITHUB_TOKEN and GOOGLE_SHEET_URL)}), "application/json")
        else:
            self.send_body(HTML)

    def do_POST(self):
        if self.path == "/api/sync":
            result = do_sync()
            self.send_body(json.dumps(result), "application/json")
        else:
            self.send_body(json.dumps({"error": "not found"}), "application/json", 404)

    def log_message(self, fmt, *args):
        pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == "__main__":
    print(f"Mamacita's Recipes running on port {PORT}")
    threading.Thread(target=load_recipes, daemon=True).start()
    ThreadedHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
