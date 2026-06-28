#!/usr/bin/env python3
"""Mamacita's Recipes - Arditti Kitchen (cloud deployment with Google Sheets sync)"""

import os, json, re, base64, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.request, urllib.error

# ── Env config ────────────────────────────────────────────────────────────────
PORT             = int(os.environ.get("PORT", 8080))
GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO      = os.environ.get("GITHUB_REPO", "")
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "")
CACHE_PATH       = "recipes-cache.json"

# ── In-memory recipe store ────────────────────────────────────────────────────
_cache_lock  = threading.Lock()
_recipes_mem = None   # dict: url -> recipe; None = not loaded yet
_syncing     = False

# ── GitHub helpers (READ-ONLY) ─────────────────────────────────────────────────

def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "mamacitas-recipes/1.0",
    }

def github_get_cache():
    """Fetch recipes-cache.json from GitHub. Returns data_dict."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CACHE_PATH}"
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        meta = json.loads(r.read())
    content = base64.b64decode(meta["content"]).decode("utf-8")
    return json.loads(content)

# ── Google Sheet helpers ───────────────────────────────────────────────────────

def get_sheet_urls():
    """Read URLs from Google Sheet — checks column B (hyperlinks) then column A."""
    import csv, io
    req = urllib.request.Request(GOOGLE_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("utf-8", errors="replace")
    skip = {"search.app", "share.google"}
    urls = []
    seen = set()
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        for cell in row[:2]:
            cell = cell.strip()
            if cell.startswith("http") and not any(s in cell for s in skip):
                if cell not in seen:
                    seen.add(cell)
                    urls.append(cell)
    return urls

# ── Recipe fetching ────────────────────────────────────────────────────────────

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
        "title":        _clean(r.get("name")) or "Untitled Recipe",
        "description":  _clean(r.get("description")) or "",
        "ingredients":  [_clean(i) for i in ingr] if isinstance(ingr, list) else [],
        "instructions": [i for i in instructions if i],
        "image":        img or "",
        "url":          url,
        "source":       "schema",
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

    t = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', body)
    i = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', body)
    return {
        "title": t.group(1) if t else url, "description": "", "ingredients": [],
        "instructions": [], "image": i.group(1) if i else "", "url": url, "source": "scrape"
    }

# ── Startup loader ────────────────────────────────────────────────────────────

def load_recipes():
    """Load seed recipes from GitHub (read-only). Returns list for /api/recipes."""
    global _recipes_mem
    with _cache_lock:
        if _recipes_mem is not None:
            return list(_recipes_mem.values())
    try:
        data = github_get_cache()
        recipes = {}
        for url, r in (data.get("recipes") or {}).items():
            if r.get("source") != "error":
                recipes[url] = {**r, "url": url}
        for r in (data.get("manualRecipes") or []):
            key = r.get("url") or r.get("title", "")
            recipes[key] = {**r, "isManual": True, "source": "manual"}
        with _cache_lock:
            _recipes_mem = recipes
        print(f"Loaded {len(recipes)} seed recipes from GitHub")
    except Exception as e:
        print(f"Could not load from GitHub: {e}")
        with _cache_lock:
            _recipes_mem = {}

    # Kick off Sheet sync in background so new recipes appear after startup
    if GOOGLE_SHEET_URL:
        threading.Thread(target=_background_sheet_sync, daemon=True).start()

    with _cache_lock:
        return list(_recipes_mem.values())

def _background_sheet_sync():
    """On startup, silently fetch any Sheet URLs not already in memory."""
    global _recipes_mem
    try:
        sheet_urls = get_sheet_urls()
        with _cache_lock:
            existing = set(_recipes_mem.keys())
        new_urls = [u for u in sheet_urls if u not in existing]
        if not new_urls:
            print("Startup sync: no new Sheet URLs to fetch")
            return
        print(f"Startup sync: fetching {len(new_urls)} new Sheet URLs")
        fetched = 0
        for url in new_urls:
            try:
                recipe = fetch_recipe(url)
                with _cache_lock:
                    _recipes_mem[url] = {**recipe, "url": url}
                fetched += 1
                print(f"Startup fetched: {recipe.get('title','?')}")
            except Exception as e:
                print(f"Startup fetch failed {url}: {e}")
        print(f"Startup sync done: +{fetched} recipes")
    except Exception as e:
        print(f"Startup sheet sync error: {e}")

# ── Sync logic (button-triggered) ─────────────────────────────────────────────

def do_sync():
    """Fetch any new Sheet URLs not already in memory. No GitHub writes."""
    global _syncing, _recipes_mem
    if _syncing:
        return {"status": "already_syncing"}
    if not GOOGLE_SHEET_URL:
        return {"status": "error", "message": "GOOGLE_SHEET_URL not set"}
    _syncing = True
    try:
        sheet_urls = get_sheet_urls()
        with _cache_lock:
            existing = set(_recipes_mem.keys() if _recipes_mem else [])
        new_urls = [u for u in sheet_urls if u not in existing]

        fetched, failed = 0, 0
        for url in new_urls:
            try:
                print(f"Fetching: {url}")
                recipe = fetch_recipe(url)
                with _cache_lock:
                    _recipes_mem[url] = {**recipe, "url": url}
                fetched += 1
                print(f"OK: {recipe.get('title','?')}")
            except Exception as e:
                print(f"FAILED {url}: {e}")
                failed += 1

        total = len(_recipes_mem) if _recipes_mem else 0
        return {"status": "done", "new": len(new_urls), "fetched": fetched, "failed": failed, "total": total}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        _syncing = False

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Mamacita\'s Recipes</title>\n  <style>\n    * { box-sizing: border-box; margin: 0; padding: 0; }\n\n    body {\n      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n      background: #eef4fb;\n      color: #1a2a3a;\n      min-height: 100vh;\n    }\n\n    /* ── Header ── */\n    .header {\n      background: #fff;\n      border-bottom: 1px solid #cde0f5;\n      padding: 14px 28px;\n      position: sticky;\n      top: 0;\n      z-index: 100;\n    }\n\n    .header-top {\n      display: flex;\n      align-items: center;\n      gap: 16px;\n      margin-bottom: 10px;\n    }\n\n    .branding { line-height: 1.15; }\n\n    .branding h1 {\n      font-size: 20px;\n      font-weight: 800;\n      color: #0d3b6e;\n      letter-spacing: -0.4px;\n    }\n\n    .branding .sub {\n      font-size: 11px;\n      font-weight: 600;\n      letter-spacing: 1.2px;\n      text-transform: uppercase;\n      color: #4a90d9;\n    }\n\n    .header-controls {\n      display: flex;\n      align-items: center;\n      gap: 10px;\n      flex: 1;\n    }\n\n    .search-wrap {\n      flex: 1;\n      position: relative;\n      max-width: 480px;\n    }\n\n    .search-wrap svg {\n      position: absolute;\n      left: 13px;\n      top: 50%;\n      transform: translateY(-50%);\n      color: #7aaad4;\n      pointer-events: none;\n    }\n\n    #search {\n      width: 100%;\n      padding: 10px 14px 10px 40px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      font-size: 14px;\n      background: #f4f8fd;\n      outline: none;\n      transition: border-color 0.15s, background 0.15s;\n      color: #1a2a3a;\n    }\n\n    #search:focus { border-color: #1a6fba; background: #fff; }\n    #search::placeholder { color: #9ab8d8; }\n\n    .filter-wrap {\n      position: relative;\n    }\n\n    .filter-wrap svg {\n      position: absolute;\n      left: 11px;\n      top: 50%;\n      transform: translateY(-50%);\n      color: #f0a500;\n      pointer-events: none;\n    }\n\n    #ratingFilter {\n      padding: 10px 14px 10px 32px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      font-size: 13px;\n      font-weight: 500;\n      background: #f4f8fd;\n      color: #1a2a3a;\n      outline: none;\n      cursor: pointer;\n      transition: border-color 0.15s;\n      appearance: none;\n      -webkit-appearance: none;\n      pr: 28px;\n    }\n\n    #ratingFilter:focus { border-color: #1a6fba; }\n\n    /* ── Add Recipe row ── */\n    .add-row {\n      display: flex;\n      align-items: center;\n      gap: 8px;\n      padding: 8px 0 0;\n      border-top: 1px solid #eef4fb;\n    }\n\n    .add-url-input {\n      flex: 1;\n      padding: 8px 13px;\n      border: 1.5px solid #c5daf0;\n      border-radius: 9px;\n      font-size: 13px;\n      background: #f4f8fd;\n      color: #1a2a3a;\n      outline: none;\n      transition: border-color 0.15s;\n    }\n\n    .add-url-input:focus { border-color: #1a6fba; background: #fff; }\n    .add-url-input::placeholder { color: #9ab8d8; }\n\n    .add-btn {\n      padding: 8px 16px;\n      background: #1a6fba;\n      color: #fff;\n      border: none;\n      border-radius: 9px;\n      font-size: 13px;\n      font-weight: 600;\n      cursor: pointer;\n      white-space: nowrap;\n      transition: background 0.15s;\n    }\n\n    .add-btn:hover { background: #0d5099; }\n    .add-btn:disabled { opacity: 0.55; cursor: default; }\n\n    .add-status {\n      font-size: 12px;\n      font-weight: 600;\n      white-space: nowrap;\n      min-width: 120px;\n    }\n\n    .add-status.ok { color: #27ae60; }\n    .add-status.err { color: #c0392b; }\n    .add-status.exists { color: #f0a500; }\n\n    /* ── Stats bar ── */\n    .stats {\n      padding: 8px 28px;\n      font-size: 12px;\n      color: #6a8fad;\n      display: flex;\n      gap: 12px;\n      align-items: center;\n    }\n\n    .stats .dot { width: 6px; height: 6px; border-radius: 50%; background: #4caf50; display: inline-block; }\n\n    /* ── Grid ── */\n    .grid {\n      display: grid;\n      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));\n      gap: 18px;\n      padding: 18px 28px 48px;\n    }\n\n    .card {\n      background: #fff;\n      border: 1px solid #d5e8f5;\n      border-radius: 14px;\n      overflow: hidden;\n      cursor: pointer;\n      transition: box-shadow 0.15s, transform 0.15s;\n      display: flex;\n      flex-direction: column;\n    }\n\n    .card:hover {\n      box-shadow: 0 6px 24px rgba(26, 111, 186, 0.13);\n      transform: translateY(-2px);\n    }\n\n    .card-img {\n      width: 100%;\n      height: 155px;\n      background: #deeaf8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      font-size: 36px;\n      overflow: hidden;\n      flex-shrink: 0;\n      position: relative;\n    }\n\n    .card-img img {\n      width: 100%;\n      height: 100%;\n      object-fit: cover;\n      display: block;\n    }\n\n    .card-body {\n      padding: 13px 14px 10px;\n      flex: 1;\n      display: flex;\n      flex-direction: column;\n      gap: 6px;\n    }\n\n    .card-title {\n      font-size: 14px;\n      font-weight: 600;\n      line-height: 1.35;\n      color: #0d3b6e;\n      display: -webkit-box;\n      -webkit-line-clamp: 2;\n      -webkit-box-orient: vertical;\n      overflow: hidden;\n    }\n\n    .card-meta {\n      font-size: 11px;\n      color: #7aaad4;\n      display: flex;\n      gap: 7px;\n      flex-wrap: wrap;\n    }\n\n    .card-meta .tag {\n      background: #eef4fb;\n      padding: 2px 8px;\n      border-radius: 20px;\n      color: #4a80b0;\n    }\n\n    .card-meta .tag.manual { background: #fff8e1; color: #b07d00; }\n    .card-meta .tag.error { background: #fdeaea; color: #c0392b; }\n\n    /* ── Rating row on card ── */\n    .card-rating {\n      display: flex;\n      align-items: center;\n      gap: 6px;\n      padding: 8px 14px 12px;\n      border-top: 1px solid #edf4fb;\n      flex-shrink: 0;\n    }\n\n    .rating-label {\n      font-size: 11px;\n      color: #9ab8d8;\n      font-weight: 500;\n      width: 30px;\n      flex-shrink: 0;\n    }\n\n    .rating-dots {\n      display: flex;\n      gap: 3px;\n    }\n\n    .rating-dot {\n      width: 18px;\n      height: 18px;\n      border-radius: 50%;\n      border: 1.5px solid #c5daf0;\n      background: #f4f8fd;\n      cursor: pointer;\n      font-size: 9px;\n      font-weight: 700;\n      color: #9ab8d8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      transition: all 0.1s;\n      flex-shrink: 0;\n    }\n\n    .rating-dot:hover,\n    .rating-dot.active {\n      background: #1a6fba;\n      border-color: #1a6fba;\n      color: #fff;\n    }\n\n    .rating-dot.active { box-shadow: 0 0 0 2px #a8cff0; }\n\n    .rating-score {\n      font-size: 12px;\n      font-weight: 700;\n      color: #1a6fba;\n      margin-left: 4px;\n    }\n\n    .empty {\n      grid-column: 1/-1;\n      text-align: center;\n      padding: 60px 20px;\n      color: #9ab8d8;\n    }\n\n    /* ── Modal ── */\n    .overlay {\n      display: none;\n      position: fixed;\n      inset: 0;\n      background: rgba(10, 30, 60, 0.5);\n      z-index: 200;\n      align-items: flex-start;\n      justify-content: center;\n      padding: 32px 16px;\n      overflow-y: auto;\n    }\n\n    .overlay.open { display: flex; }\n\n    .modal {\n      background: #fff;\n      border-radius: 18px;\n      width: 100%;\n      max-width: 740px;\n      overflow: hidden;\n      position: relative;\n      margin: auto;\n    }\n\n    .modal-hero {\n      width: 100%;\n      height: 250px;\n      background: #deeaf8;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      font-size: 64px;\n      overflow: hidden;\n    }\n\n    .modal-hero img { width: 100%; height: 100%; object-fit: cover; display: block; }\n\n    .modal-close {\n      position: absolute;\n      top: 14px;\n      right: 14px;\n      width: 34px;\n      height: 34px;\n      border-radius: 50%;\n      background: rgba(10,30,60,0.45);\n      border: none;\n      color: #fff;\n      font-size: 17px;\n      cursor: pointer;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n    }\n\n    .modal-delete {\n      position: absolute;\n      top: 14px;\n      left: 14px;\n      width: 34px;\n      height: 34px;\n      border-radius: 50%;\n      background: rgba(10,30,60,0.45);\n      border: none;\n      color: #fff;\n      font-size: 15px;\n      cursor: pointer;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      transition: background 0.15s;\n    }\n\n    .modal-delete:hover { background: rgba(180,30,30,0.75); }\n\n    .modal-body { padding: 26px 30px 40px; }\n\n    .modal-header-row {\n      display: flex;\n      align-items: flex-start;\n      justify-content: space-between;\n      gap: 16px;\n      margin-bottom: 6px;\n    }\n\n    .modal-title {\n      font-size: 24px;\n      font-weight: 800;\n      line-height: 1.25;\n      color: #0d3b6e;\n      letter-spacing: -0.3px;\n    }\n\n    .modal-rating-badge {\n      flex-shrink: 0;\n      background: #eef4fb;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px;\n      padding: 6px 12px;\n      text-align: center;\n      min-width: 56px;\n    }\n\n    .modal-rating-badge .badge-num {\n      font-size: 22px;\n      font-weight: 800;\n      color: #1a6fba;\n      line-height: 1;\n    }\n\n    .modal-rating-badge .badge-label {\n      font-size: 9px;\n      color: #9ab8d8;\n      font-weight: 600;\n      letter-spacing: 0.5px;\n      text-transform: uppercase;\n    }\n\n    .modal-rating-badge.unrated .badge-num { color: #c5daf0; font-size: 13px; font-weight: 500; }\n\n    .modal-source {\n      font-size: 12px;\n      color: #9ab8d8;\n      margin-bottom: 14px;\n    }\n\n    .modal-source a { color: #1a6fba; text-decoration: none; }\n    .modal-source a:hover { text-decoration: underline; }\n\n    .view-recipe-btn {\n      display: inline-flex;\n      align-items: center;\n      gap: 7px;\n      padding: 10px 18px;\n      background: #1a6fba;\n      color: #fff;\n      border-radius: 10px;\n      font-size: 14px;\n      font-weight: 600;\n      text-decoration: none;\n      margin-bottom: 20px;\n      transition: background 0.15s;\n    }\n\n    .view-recipe-btn:hover { background: #0d5099; color: #fff; }\n\n    .view-recipe-btn.secondary {\n      background: #eef4fb;\n      color: #1a6fba;\n      border: 1.5px solid #c5daf0;\n    }\n\n    .view-recipe-btn.secondary:hover { background: #deeaf8; color: #1a6fba; }\n\n    .modal-description {\n      font-size: 14px;\n      color: #4a6a8a;\n      line-height: 1.65;\n      margin-bottom: 24px;\n    }\n\n    /* Modal rating row */\n    .modal-rate-row {\n      display: flex;\n      align-items: center;\n      gap: 10px;\n      margin-bottom: 24px;\n      padding: 12px 16px;\n      background: #f4f8fd;\n      border-radius: 10px;\n      border: 1px solid #dceaf8;\n    }\n\n    .modal-rate-row .rate-label {\n      font-size: 12px;\n      font-weight: 600;\n      color: #4a80b0;\n      white-space: nowrap;\n    }\n\n    .modal-rate-dots {\n      display: flex;\n      gap: 4px;\n      flex-wrap: wrap;\n    }\n\n    .modal-rate-dot {\n      width: 28px;\n      height: 28px;\n      border-radius: 50%;\n      border: 1.5px solid #c5daf0;\n      background: #fff;\n      cursor: pointer;\n      font-size: 11px;\n      font-weight: 700;\n      color: #7aaad4;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n      transition: all 0.12s;\n    }\n\n    .modal-rate-dot:hover { background: #deeaf8; border-color: #1a6fba; color: #1a6fba; }\n    .modal-rate-dot.active { background: #1a6fba; border-color: #1a6fba; color: #fff; box-shadow: 0 0 0 3px #a8cff0; }\n\n    .modal-columns {\n      display: grid;\n      grid-template-columns: 1fr 1.6fr;\n      gap: 30px;\n    }\n\n    @media (max-width: 600px) { .modal-columns { grid-template-columns: 1fr; } }\n\n    .section-label {\n      font-size: 10px;\n      font-weight: 700;\n      letter-spacing: 1px;\n      text-transform: uppercase;\n      color: #7aaad4;\n      margin-bottom: 12px;\n    }\n\n    .ingredients-list {\n      list-style: none;\n      display: flex;\n      flex-direction: column;\n      gap: 7px;\n    }\n\n    .ingredients-list li {\n      font-size: 13px;\n      line-height: 1.5;\n      padding-left: 14px;\n      position: relative;\n      color: #2a3f5a;\n    }\n\n    .ingredients-list li::before {\n      content: \'\';\n      position: absolute;\n      left: 0;\n      top: 7px;\n      width: 5px;\n      height: 5px;\n      border-radius: 50%;\n      background: #1a6fba;\n    }\n\n    .ingredients-list li.section-header {\n      font-size: 10px;\n      font-weight: 700;\n      letter-spacing: 0.8px;\n      text-transform: uppercase;\n      color: #7aaad4;\n      padding-left: 0;\n      margin-top: 10px;\n    }\n    .ingredients-list li.section-header::before { display: none; }\n\n    .instructions-list {\n      list-style: none;\n      display: flex;\n      flex-direction: column;\n      gap: 14px;\n    }\n\n    .instructions-list li {\n      font-size: 13px;\n      line-height: 1.65;\n      padding-left: 36px;\n      position: relative;\n      color: #2a3f5a;\n    }\n\n    .instructions-list li::before {\n      content: attr(data-n);\n      position: absolute;\n      left: 0;\n      top: 0;\n      width: 24px;\n      height: 24px;\n      border-radius: 50%;\n      background: #1a6fba;\n      color: #fff;\n      font-size: 11px;\n      font-weight: 700;\n      display: flex;\n      align-items: center;\n      justify-content: center;\n    }\n\n    .step-section {\n      font-size: 10px;\n      font-weight: 700;\n      text-transform: uppercase;\n      letter-spacing: 0.8px;\n      color: #7aaad4;\n      padding-left: 0 !important;\n      margin-top: 8px;\n    }\n\n    .step-section::before { display: none !important; }\n    .no-content { font-size: 13px; color: #b0c8e0; font-style: italic; }\n\n    /* ── This Week ── */\n    .week-btn {\n      margin-left: auto;\n      width: 28px; height: 28px;\n      border-radius: 50%;\n      border: 1.5px solid #c5daf0;\n      background: #f4f8fd;\n      cursor: pointer;\n      font-size: 14px;\n      display: flex; align-items: center; justify-content: center;\n      flex-shrink: 0;\n      transition: all 0.12s;\n      line-height: 1;\n    }\n    .week-btn:hover { border-color: #1a6fba; background: #eef4fb; }\n    .week-btn.on { background: #1a6fba; border-color: #1a6fba; filter: brightness(1.1); }\n    .this-week-section { padding: 14px 28px 0; }\n    .this-week-label {\n      font-size: 10px; font-weight: 700; letter-spacing: 1.2px;\n      text-transform: uppercase; color: #1a6fba; margin-bottom: 10px;\n      display: flex; align-items: center; gap: 8px;\n    }\n    .this-week-label::after { content: \'\'; flex: 1; height: 1px; background: #c5daf0; }\n    .this-week-grid {\n      display: grid;\n      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));\n      gap: 18px; margin-bottom: 18px;\n    }\n    .this-week-grid .card { border-color: #1a6fba; box-shadow: 0 0 0 2px #1a6fba22; }\n    .modal-week-btn {\n      display: inline-flex; align-items: center; gap: 7px;\n      padding: 9px 16px;\n      background: #f4f8fd; color: #1a6fba;\n      border: 1.5px solid #c5daf0;\n      border-radius: 10px; font-size: 13px; font-weight: 600;\n      cursor: pointer; transition: all 0.15s; margin-bottom: 16px;\n    }\n    .modal-week-btn:hover { background: #eef4fb; border-color: #1a6fba; }\n    .modal-week-btn.on { background: #1a6fba; color: #fff; border-color: #1a6fba; }\n  </style>\n</head>\n<body>\n\n  <div class="header">\n    <div class="header-top">\n      <div class="branding">\n        <h1>Mamacita\'s Recipes</h1>\n        <div class="sub">Arditti Kitchen</div>\n      </div>\n    </div>\n    <div class="header-controls">\n      <div class="search-wrap">\n        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">\n          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>\n        </svg>\n        <input id="search" type="text" placeholder="Search recipes, ingredients..." autocomplete="off" />\n      </div>\n      <select id="ratingFilter" onchange="applyFilters()" style="padding:10px 14px;border:1.5px solid #c5daf0;border-radius:10px;font-size:13px;font-weight:500;background:#f4f8fd;color:#1a2a3a;outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">\n        <option value="0">All ratings</option>\n        <option value="1">&#x2605; 1+</option>\n        <option value="2">&#x2605; 2+</option>\n        <option value="3">&#x2605; 3+</option>\n        <option value="4">&#x2605; 4+</option>\n        <option value="5">&#x2605; 5+</option>\n        <option value="6">&#x2605; 6+</option>\n        <option value="7">&#x2605; 7+</option>\n        <option value="8">&#x2605; 8+</option>\n        <option value="9">&#x2605; 9+</option>\n        <option value="10">&#x2605; 10</option>\n      </select>\n      <select id="proteinFilter" onchange="applyFilters()" style="padding:10px 14px;border:1.5px solid #c5daf0;border-radius:10px;font-size:13px;font-weight:500;background:#f4f8fd;color:#1a2a3a;outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">\n        <option value="">All proteins</option>\n        <option value="chicken">Chicken</option>\n        <option value="turkey">Turkey</option>\n        <option value="beef">Beef</option>\n        <option value="salmon">Salmon / Fish</option>\n        <option value="shrimp">Shrimp</option>\n        <option value="tofu">Tofu</option>\n        <option value="chickpea">Chickpeas / Beans</option>\n        <option value="vegetarian">Vegetarian</option>\n      </select>\n\n    </div>\n    <div class="add-row">\n      <input class="add-url-input" id="addUrl" type="url" placeholder="Paste a recipe URL to add it..." autocomplete="off" onkeydown="if(event.key===\'Enter\')addRecipe()" />\n      <button class="add-btn" id="addBtn" onclick="addRecipe()">Add Recipe</button>\n      <span class="add-status" id="addStatus"></span>\n    </div>\n  </div>\n\n  <div id="thisWeekSection" style="display:none"><div class="this-week-section"><div class="this-week-label">&#x1F4C5; Meals This Week<button onclick="clearThisWeek()" style="margin-left:12px;font-size:10px;font-weight:600;letter-spacing:0.5px;padding:3px 10px;border:1.5px solid #c5daf0;border-radius:8px;background:#fff;color:#9ab8d8;cursor:pointer;text-transform:uppercase;" title="Clear all meals this week">Clear All</button></div><div class="this-week-grid" id="thisWeekGrid"></div></div></div>\n  <div class="stats" id="stats">Loading recipes&#x2026;</div>\n  <div class="grid" id="grid"></div>\n\n  <!-- Modal -->\n  <div class="overlay" id="overlay" onclick="closeModal(event)">\n    <div class="modal" id="modal">\n      <div class="modal-hero" id="modalHero">&#x1F37D;&#xFE0F;</div>\n      <button class="modal-delete" onclick="deleteRecipe()" title="Delete recipe">&#x1F5D1;</button>\n      <button class="modal-close" onclick="closeOverlay()">&#x2715;</button>\n      <div class="modal-body">\n        <div class="modal-header-row">\n          <div class="modal-title" id="modalTitle"></div>\n          <div class="modal-rating-badge unrated" id="modalBadge">\n            <div class="badge-num" id="modalBadgeNum">&#x2014;</div>\n            <div class="badge-label">/ 10</div>\n          </div>\n        </div>\n        <div class="modal-source" id="modalSource"></div>\n        <div class="modal-description" id="modalDesc"></div>\n        <button id="modalWeekBtn" class="modal-week-btn" onclick="toggleWeek(null,currentRecipeKey)">&#x1F4C5; Add to This Week</button>\n        <div class="modal-rate-row">\n          <span class="rate-label">Your rating:</span>\n          <div class="modal-rate-dots" id="modalRateDots"></div>\n        </div>\n        <div class="modal-columns">\n          <div>\n            <div class="section-label">Ingredients</div>\n            <ul class="ingredients-list" id="modalIngredients"></ul>\n          </div>\n          <div>\n            <div class="section-label">Instructions</div>\n            <ol class="instructions-list" id="modalInstructions"></ol>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <script>\n    let allRecipes = [];\n    let ratings = {};\n    let currentRecipeKey = null;\n    let thisWeek = new Set();\n\n    const RATINGS_KEY = \'mamacita_ratings\';\n\n    const WEEK_KEY = \'mamacita_this_week\';\n\n    function loadThisWeek() {\n      try {\n        const s = JSON.parse(localStorage.getItem(WEEK_KEY) || \'null\');\n        if (s && Array.isArray(s.urls)) return new Set(s.urls);\n        if (Array.isArray(s)) return new Set(s);\n      } catch(e) {}\n      return new Set();\n    }\n\n    function saveThisWeek() {\n      localStorage.setItem(WEEK_KEY, JSON.stringify({ urls: [...thisWeek] }));\n    }\n\n    function toggleWeek(e, key) {\n      if (e) e.stopPropagation();\n      if (thisWeek.has(key)) { thisWeek.delete(key); } else { thisWeek.add(key); }\n      saveThisWeek();\n      applyFilters();\n      renderThisWeek();\n      if (currentRecipeKey === key) renderModalWeekBtn(key);\n    }\n\n    function clearThisWeek() {\n      thisWeek.clear();\n      saveThisWeek();\n      applyFilters();\n      renderThisWeek();\n      if (currentRecipeKey) renderModalWeekBtn(currentRecipeKey);\n    }\n\n    function renderThisWeek() {\n      const section = document.getElementById(\'thisWeekSection\');\n      const grid = document.getElementById(\'thisWeekGrid\');\n      const weekRecipes = allRecipes.filter(r => thisWeek.has(recipeKey(r)));\n      if (!weekRecipes.length) { section.style.display = \'none\'; return; }\n      section.style.display = \'block\';\n      grid.innerHTML = weekRecipes.map(r => buildCard(r)).join(\'\');\n    }\n\n    function renderModalWeekBtn(key) {\n      const btn = document.getElementById(\'modalWeekBtn\');\n      if (!btn) return;\n      const on = thisWeek.has(key);\n      btn.className = \'modal-week-btn\' + (on ? \' on\' : \'\');\n      btn.innerHTML = \'&#x1F4C5; \' + (on ? \'Remove from This Week\' : \'Add to This Week\');\n    }\n\n    function loadRatingsFromStorage() {\n      try { return JSON.parse(localStorage.getItem(RATINGS_KEY) || \'{}\'); } catch(e) { return {}; }\n    }\n\n    function saveRatingsToStorage(r) {\n      localStorage.setItem(RATINGS_KEY, JSON.stringify(r));\n    }\n\n    function recipeKey(r) {\n      return r.url || r.title || \'\';\n    }\n\n    async function loadData() {\n      const res = await fetch(\'/api/recipes\');\n      allRecipes = await res.json();\n      ratings = loadRatingsFromStorage();\n      thisWeek = loadThisWeek();\n      renderThisWeek();\n\n      allRecipes.sort((a, b) => {\n        const aHas = a.ingredients.length + a.instructions.length;\n        const bHas = b.ingredients.length + b.instructions.length;\n        if (aHas !== bHas) return bHas - aHas;\n        return (a.title || \'\').localeCompare(b.title || \'\');\n      });\n\n      applyFilters();\n      updateStats();\n    }\n\n    function updateStats() {\n      const total = allRecipes.length;\n      const rated = Object.keys(ratings).length;\n      document.getElementById(\'stats\').innerHTML =\n        \'<span class="dot"></span> \' + total + \' recipes &nbsp;&middot;&nbsp; \' + rated + \' rated\';\n    }\n\n    const PROTEIN_KEYWORDS = {\n      chicken:    [\'chicken\'],\n      turkey:     [\'turkey\'],\n      beef:       [\'beef\', \'steak\', \'ground beef\', \'pot roast\', \'braised beef\'],\n      salmon:     [\'salmon\', \'tuna\', \'halibut\', \'cod\', \'fish\', \'halloumi\'],\n      shrimp:     [\'shrimp\', \'prawn\'],\n      tofu:       [\'tofu\'],\n      chickpea:   [\'chickpea\', \'black bean\', \'lentil\', \'cannellini\', \'white bean\', \'great northern\', \'adzuki\', \'bean\'],\n    };\n\n    function detectProtein(r) {\n      const text = [r.title || \'\', ...(r.ingredients || [])].join(\' \').toLowerCase();\n      const found = new Set();\n      for (const [type, words] of Object.entries(PROTEIN_KEYWORDS)) {\n        if (words.some(w => text.includes(w))) found.add(type);\n      }\n      const animalProteins = [\'chicken\',\'turkey\',\'beef\',\'salmon\',\'shrimp\'];\n      if (!animalProteins.some(p => found.has(p))) found.add(\'vegetarian\');\n      return found;\n    }\n\n    function applyFilters() {\n      const q = document.getElementById(\'search\').value.toLowerCase().trim();\n      const minRating = parseInt(document.getElementById(\'ratingFilter\').value) || 0;\n      const protein = document.getElementById(\'proteinFilter\').value;\n\n      let filtered = allRecipes.filter(r => {\n        if (minRating > 0) {\n          const score = ratings[recipeKey(r)];\n          if (!score || score < minRating) return false;\n        }\n        if (protein) {\n          if (!detectProtein(r).has(protein)) return false;\n        }\n        if (!q) return true;\n        const haystack = [\n          r.title || \'\',\n          r.description || \'\',\n          ...(r.ingredients || []),\n          ...(r.instructions || []),\n          r.url || \'\',\n        ].join(\' \').toLowerCase();\n        return q.split(\' \').every(w => haystack.includes(w));\n      });\n\n      renderGrid(filtered);\n    }\n\n    function buildCard(r) {\n        const key = recipeKey(r);\n        const score = ratings[key];\n        const tag = r.isManual ? \'manual\' : r.source === \'error\' ? \'error\' : \'\';\n        const tagLabel = r.isManual ? \'Note\' : r.source === \'error\' ? \'Error\' : r.ingredients.length > 0 ? (r.ingredients.length + \' ingr.\') : \'Link only\';\n        const domain = r.url ? (() => { try { return new URL(r.url).hostname.replace(\'www.\',\'\'); } catch(e) { return \'\'; }})() : \'\';\n        const imgHtml = r.image\n          ? \'<img src="\' + esc(r.image) + \'" onerror="this.style.display=\\\'none\\\'" loading="lazy" />\'\n          : \'&#x1F37D;&#xFE0F;\';\n\n        const dots = Array.from({length:10},(_,n)=>{\n          const val = n+1;\n          const active = score && score >= val ? \'active\' : \'\';\n          return \'<div class="rating-dot \' + active + \'" data-val="\' + val + \'" onclick="rateFromCard(event,\\\'\' + esc(key) + \'\\\',\' + val + \')" title="\' + val + \'/10">\' + val + \'</div>\';\n        }).join(\'\');\n\n        return \'<div class="card" onclick="openRecipeByKey(\\\'\' + esc(key) + \'\\\')">\' +\n          \'<div class="card-img">\' + imgHtml + \'</div>\' +\n          \'<div class="card-body">\' +\n            \'<div class="card-title">\' + esc(r.title || r.url || \'Untitled\') + \'</div>\' +\n            \'<div class="card-meta">\' +\n              (domain ? \'<span class="tag">\' + esc(domain) + \'</span>\' : \'\') +\n              \'<span class="tag \' + tag + \'">\' + tagLabel + \'</span>\' +\n            \'</div>\' +\n          \'</div>\' +\n          \'<div class="card-rating">\' +\n            \'<div class="rating-label">\' + (score ? score + \'/10\' : \'Rate\') + \'</div>\' +\n            \'<div class="rating-dots">\' + dots + \'</div>\' +\n            \'<button class="week-btn \' + (thisWeek.has(key) ? \'on\' : \'\') + \'" onclick="toggleWeek(event,\\\'\' + esc(key) + \'\\\')" title="\' + (thisWeek.has(key) ? \'Remove from this week\' : \'Add to this week\') + \'">&#x1F4C5;</button>\' +\n          \'</div>\' +\n        \'</div>\';\n      }\n\n    function renderGrid(recipes) {\n      const grid = document.getElementById(\'grid\');\n      if (!recipes.length) {\n        grid.innerHTML = \'<div class="empty"><div style="font-size:40px;margin-bottom:10px">&#x1F50D;</div><div>No recipes found</div></div>\';\n        return;\n      }\n      grid.innerHTML = recipes.map(r => buildCard(r)).join(\'\');\n    }\n\n    function rateFromCard(e, key, val) {\n      e.stopPropagation();\n      saveRating(key, val);\n    }\n\n    function saveRating(key, val) {\n      const current = ratings[key];\n      const newVal = current === val ? null : val;\n      if (newVal === null) { delete ratings[key]; } else { ratings[key] = newVal; }\n      saveRatingsToStorage(ratings);\n      if (currentRecipeKey === key) renderModalRating(key);\n      applyFilters();\n      updateStats();\n    }\n\n    function openRecipeByKey(key) {\n      const r = allRecipes.find(x => recipeKey(x) === key);\n      if (!r) return;\n      currentRecipeKey = key;\n\n      document.getElementById(\'modalTitle\').textContent = r.title || \'Untitled\';\n\n      const src = document.getElementById(\'modalSource\');\n      const isBlank = !r.ingredients.length && !r.instructions.length;\n      if (r.url) {\n        const btnClass = isBlank ? \'view-recipe-btn\' : \'view-recipe-btn secondary\';\n        const btnLabel = isBlank ? \'&#x1F517; View Full Recipe &#x2192;\' : \'&#x1F517; View on website\';\n        src.innerHTML = (isBlank ? \'<div style="font-size:13px;color:#9ab8d4;margin-bottom:10px">Recipe details not available here &mdash; visit the original site:</div>\' : \'\') +\n          \'<a class="\' + btnClass + \'" href="\' + esc(r.url) + \'" target="_blank" rel="noopener">\' + btnLabel + \'</a>\';\n      } else {\n        src.innerHTML = \'<em style="font-size:12px;color:#9ab8d8">From your Apple Notes</em>\';\n      }\n\n      const desc = document.getElementById(\'modalDesc\');\n      desc.textContent = r.description || \'\';\n      desc.style.display = r.description ? \'block\' : \'none\';\n\n      const hero = document.getElementById(\'modalHero\');\n      hero.innerHTML = r.image\n        ? \'<img src="\' + esc(r.image) + \'" onerror="this.style.display=\\\'none\\\'" />\'\n        : \'&#x1F37D;&#xFE0F;\';\n\n      const ingList = document.getElementById(\'modalIngredients\');\n      ingList.innerHTML = r.ingredients.length\n        ? r.ingredients.map(i => {\n            if (i.startsWith(\'\\u2014\') && i.endsWith(\'\\u2014\')) {\n              return \'<li class="section-header">\' + esc(i.replace(/^\\u2014\\s*|\\s*\\u2014$/g,\'\')) + \'</li>\';\n            }\n            return \'<li>\' + esc(i) + \'</li>\';\n          }).join(\'\')\n        : \'<p class="no-content">No ingredients listed</p>\';\n\n      const insList = document.getElementById(\'modalInstructions\');\n      if (!r.instructions.length) {\n        insList.innerHTML = \'<p class="no-content">No instructions available</p>\';\n      } else {\n        let n = 0;\n        insList.innerHTML = r.instructions.map(step => {\n          if (step.startsWith(\'**\') && step.endsWith(\'**\')) {\n            return \'<li class="step-section">\' + esc(step.replace(/\\*\\*/g,\'\')) + \'</li>\';\n          }\n          n++;\n          return \'<li data-n="\' + n + \'">\' + esc(step) + \'</li>\';\n        }).join(\'\');\n      }\n\n      renderModalRating(key);\n      renderModalWeekBtn(key);\n      document.getElementById(\'overlay\').classList.add(\'open\');\n      document.body.style.overflow = \'hidden\';\n    }\n\n    function renderModalRating(key) {\n      const score = ratings[key];\n      const badge = document.getElementById(\'modalBadge\');\n      const badgeNum = document.getElementById(\'modalBadgeNum\');\n      if (score) {\n        badge.classList.remove(\'unrated\');\n        badgeNum.textContent = score;\n      } else {\n        badge.classList.add(\'unrated\');\n        badgeNum.textContent = \'\\u2014\';\n      }\n      const dotsEl = document.getElementById(\'modalRateDots\');\n      dotsEl.innerHTML = Array.from({length:10},(_,n) => {\n        const val = n+1;\n        const active = score === val ? \'active\' : \'\';\n        return \'<div class="modal-rate-dot \' + active + \'" onclick="saveRating(\\\'\' + esc(key) + \'\\\',\' + val + \')">\' + val + \'</div>\';\n      }).join(\'\');\n    }\n\n    function closeOverlay() {\n      document.getElementById(\'overlay\').classList.remove(\'open\');\n      document.body.style.overflow = \'\';\n      currentRecipeKey = null;\n    }\n\n    function closeModal(e) {\n      if (e.target === document.getElementById(\'overlay\')) closeOverlay();\n    }\n\n    document.addEventListener(\'keydown\', e => { if (e.key === \'Escape\') closeOverlay(); });\n    document.getElementById(\'search\').addEventListener(\'input\', applyFilters);\n\n    async function deleteRecipe() {\n      if (!currentRecipeKey) return;\n      const r = allRecipes.find(x => recipeKey(x) === currentRecipeKey);\n      const name = r ? r.title || currentRecipeKey : currentRecipeKey;\n      if (!confirm(\'Delete "\' + name + \'"? This cannot be undone.\')) return;\n      try {\n        await fetch(\'/api/delete\', { method:\'POST\', headers:{\'Content-Type\':\'application/json\'}, body: JSON.stringify({url: currentRecipeKey}) });\n        closeOverlay();\n        await loadData();\n      } catch(e) { alert(\'Error deleting recipe.\'); }\n    }\n\n    async function addRecipe() {\n      const input = document.getElementById(\'addUrl\');\n      const btn = document.getElementById(\'addBtn\');\n      const status = document.getElementById(\'addStatus\');\n      const url = input.value.trim();\n      if (!url || !url.startsWith(\'http\')) {\n        status.className = \'add-status err\';\n        status.textContent = \'Please paste a valid URL\';\n        return;\n      }\n      btn.disabled = true;\n      btn.textContent = \'Adding...\';\n      status.className = \'add-status\';\n      status.textContent = \'\';\n      try {\n        const res = await fetch(\'/api/add\', { method:\'POST\', headers:{\'Content-Type\':\'application/json\'}, body: JSON.stringify({url}) });\n        const data = await res.json();\n        if (data.status === \'ok\') {\n          status.className = \'add-status ok\';\n          status.textContent = \'\\u2713 Added: \' + data.title;\n          input.value = \'\';\n          await loadData();\n        } else if (data.status === \'exists\') {\n          status.className = \'add-status exists\';\n          status.textContent = \'Already saved: \' + data.title;\n        } else {\n          status.className = \'add-status err\';\n          status.textContent = \'Error: \' + (data.message || \'Could not fetch recipe\');\n        }\n      } catch(e) {\n        status.className = \'add-status err\';\n        status.textContent = \'Network error\';\n      }\n      btn.disabled = false;\n      btn.textContent = \'Add Recipe\';\n      setTimeout(() => { status.textContent = \'\'; status.className = \'add-status\'; }, 5000);\n    }\n\n    function esc(str) {\n      return String(str||\'\').replace(/&/g,\'&amp;\').replace(/</g,\'&lt;\').replace(/>/g,\'&gt;\').replace(/"/g,\'&quot;\').replace(/\'/g,\'&#39;\');\n    }\n\n    loadData();\n  </script>\n</body>\n</html>\n'

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
            recipes = load_recipes()
            self.send_body(json.dumps(recipes), "application/json")
        elif path == "/api/config":
            self.send_body(json.dumps({"syncAvailable": bool(GOOGLE_SHEET_URL)}), "application/json")
        elif path == "/api/debug":
            with _cache_lock:
                mem_count = len(_recipes_mem) if _recipes_mem is not None else "not loaded"
            debug = {
                "GITHUB_TOKEN_SET": bool(GITHUB_TOKEN),
                "GITHUB_REPO": GITHUB_REPO,
                "GOOGLE_SHEET_URL_SET": bool(GOOGLE_SHEET_URL),
                "recipes_in_memory": mem_count,
                "syncing": _syncing,
            }
            try:
                urls = get_sheet_urls()
                debug["sheet_urls_count"] = len(urls)
                debug["sheet_last_url"] = urls[-1] if urls else ""
                with _cache_lock:
                    existing = set(_recipes_mem.keys() if _recipes_mem else [])
                debug["new_urls_on_sheet"] = [u for u in urls if u not in existing]
            except Exception as e:
                debug["sheet_error"] = str(e)
            self.send_body(json.dumps(debug, indent=2), "application/json")
        else:
            self.send_body(HTML)

    def do_POST(self):
        if self.path == "/api/sync":
            result = do_sync()
            self.send_body(json.dumps(result), "application/json")
        elif self.path == "/api/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            url = (body.get("url") or "").strip()
            with _cache_lock:
                if _recipes_mem and url in _recipes_mem:
                    del _recipes_mem[url]
                    print(f"Deleted: {url}")
                    self.send_body(json.dumps({"status": "ok"}), "application/json")
                else:
                    self.send_body(json.dumps({"status": "not_found"}), "application/json")
            return
        elif self.path == "/api/add":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            url = (body.get("url") or "").strip()
            if not url or not url.startswith("http"):
                self.send_body(json.dumps({"status": "error", "message": "Invalid URL"}), "application/json")
                return
            with _cache_lock:
                if _recipes_mem and url in _recipes_mem:
                    r = _recipes_mem[url]
                    self.send_body(json.dumps({"status": "exists", "title": r.get("title", "?")}), "application/json")
                    return
            try:
                recipe = fetch_recipe(url)
                with _cache_lock:
                    if _recipes_mem is not None:
                        _recipes_mem[url] = {**recipe, "url": url}
                print(f"Added via URL box: {recipe.get('title','?')}")
                self.send_body(json.dumps({"status": "ok", "title": recipe.get("title", "Untitled")}), "application/json")
            except Exception as e:
                self.send_body(json.dumps({"status": "error", "message": str(e)}), "application/json")
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
