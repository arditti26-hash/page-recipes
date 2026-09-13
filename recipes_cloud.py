#!/usr/bin/env python3
"""US Open 2026 Group Bracket Dashboard — scrapes served.bracket.tennis"""

import json, re, urllib.request, os, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

def _now_et():
    if ZoneInfo:
        return datetime.now(ZoneInfo('America/New_York'))
    return datetime.utcnow() - timedelta(hours=4)

PORT = int(os.environ.get('PORT', 8768))

# ── Edit your group members here ─────────────────────────────────────────────
MEMBERS = [
    'willarditti',
    'jackthesnack21',
    'Wizzy',
    # add more served.bracket.tennis usernames here
]

COLORS = {
    0: {'primary': '#1a3a6e', 'bg': 'rgba(26,58,110,0.10)',   'border': 'rgba(26,58,110,0.22)'},
    1: {'primary': '#c8a020', 'bg': 'rgba(200,160,32,0.12)',  'border': 'rgba(200,160,32,0.28)'},
    2: {'primary': '#1a3a6e', 'bg': 'rgba(26,58,110,0.10)',   'border': 'rgba(26,58,110,0.22)'},
    3: {'primary': '#c8a020', 'bg': 'rgba(200,160,32,0.12)',  'border': 'rgba(200,160,32,0.28)'},
    4: {'primary': '#1a3a6e', 'bg': 'rgba(26,58,110,0.10)',   'border': 'rgba(26,58,110,0.22)'},
    5: {'primary': '#c8a020', 'bg': 'rgba(200,160,32,0.12)',  'border': 'rgba(200,160,32,0.28)'},
}

TOURNAMENT_SLUG = 'us-open-2026'
GROUP_SLUG      = 'serving-hot-takes'

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>US Open 2026</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="shortcut icon" type="image/png" href="/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Playfair+Display:wght@700;900&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --green:   #1a3a6e;
  --green2:  #1e4a8a;
  --green3:  #12285a;
  --purple:  #c8a020;
  --gold:    #c8a020;
  --cream:   #f0f4fa;
  --cream2:  #e4ecf7;
  --berry:   #c0392b;
  --bg:      #f5f2eb;
  --card:    #ffffff;
  --text:    #1a1a1a;
  --muted:   #6b6b6b;
  --border:  #ddd8cc;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  background-image: repeating-linear-gradient(
    180deg,
    rgba(0, 80, 40, 0.022) 0px, rgba(0, 80, 40, 0.022) 24px,
    transparent 24px, transparent 48px
  );
  color: var(--text);
  min-height: 100vh;
}

/* ── TOP NAV BAR ── */
.topbar {
  background: var(--green3);
  color: #fff;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  border-bottom: 3px solid var(--purple);
  position: sticky; top: 0; z-index: 20;
  gap: 8px;
}
.topbar-left { display: flex; align-items: center; gap: 6px; font-size: 0.75rem; font-family: sans-serif; opacity: 0.85; min-width: 0; }
.topbar-left span:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.topbar-flag { font-size: 1rem; flex-shrink: 0; }
.topbar-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.live-badge {
  display: flex; align-items: center; gap: 6px;
  background: rgba(201,169,75,0.15); border: 1px solid rgba(201,169,75,0.4);
  padding: 4px 12px; border-radius: 100px;
  font-size: 11px; font-weight: 700; color: var(--gold); letter-spacing: 1px;
  font-family: sans-serif;
}
.live-dot { width: 6px; height: 6px; background: var(--gold); border-radius: 50%; animation: blink 1.5s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.7)} }

/* ── HERO HEADER ── */
.hero {
  background: linear-gradient(160deg, var(--green3) 0%, var(--green) 55%, var(--green2) 100%);
  color: #fff;
  text-align: center;
  padding: 22px 20px 20px;
  border-bottom: 4px solid var(--gold);
  position: relative;
  overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute; inset: 0;
  background:
    repeating-linear-gradient(
      180deg,
      rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 18px,
      rgba(0,0,0,0.04) 18px, rgba(0,0,0,0.04) 36px
    ),
    radial-gradient(ellipse at 15% 50%, rgba(201,169,75,0.07) 0%, transparent 55%),
    radial-gradient(ellipse at 85% 50%, rgba(75,0,110,0.10) 0%, transparent 55%);
  pointer-events: none;
}
.hero-inner { position: relative; display: flex; align-items: center; justify-content: center; gap: 16px; flex-wrap: wrap; }
.hero-trophy { font-size: 2rem; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.35)); flex-shrink: 0; }
.hero-text { text-align: left; }
.hero-title {
  font-family: 'Playfair Display', 'EB Garamond', Georgia, serif;
  font-size: 1.9rem; font-weight: 900; letter-spacing: 0.02em;
  line-height: 1.1; text-shadow: 0 2px 10px rgba(0,0,0,0.3);
}
.hero-title span { color: var(--gold); }
.hero-subtitle {
  font-family: 'EB Garamond', Georgia, serif;
  font-size: 0.88rem; font-style: italic; opacity: 0.72;
  letter-spacing: 0.06em; margin-top: 2px;
}
.hero-pills { display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.hero-pill {
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.22);
  border-radius: 100px; padding: 4px 12px;
  font-size: 0.73rem; font-family: sans-serif; letter-spacing: 0.03em;
}
.hero-pill.gold { background: rgba(201,169,75,0.18); border-color: rgba(201,169,75,0.45); color: var(--gold); }

/* ── GRASS / STRAWBERRIES & CREAM ACCENT STRIP ── */
.sc-banner {
  background: linear-gradient(90deg, var(--cream) 0%, var(--cream2) 50%, var(--cream) 100%);
  border-bottom: 1px solid #e0d5b0;
  padding: 7px 12px;
  display: flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;
  font-family: 'EB Garamond', Georgia, serif;
  font-size: 0.82rem; color: #5a3e1b; letter-spacing: 0.05em;
  text-align: center;
}
.sc-grass {
  display: flex; gap: 3px; align-items: flex-end;
}
.sc-grass span {
  display: inline-block; width: 3px; border-radius: 2px 2px 0 0;
  background: var(--green2); opacity: 0.7;
}
.sc-grass span:nth-child(1) { height: 10px; }
.sc-grass span:nth-child(2) { height: 14px; }
.sc-grass span:nth-child(3) { height: 9px; }
.sc-grass span:nth-child(4) { height: 13px; }
.sc-grass span:nth-child(5) { height: 11px; }
.sc-banner .berry { color: var(--berry); font-size: 1rem; }

/* ── MAIN ── */
.wrap { max-width: 880px; margin: 0 auto; padding: 28px 20px 60px; }

/* ── STATUS BAR ── */
.status-bar {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.78rem; font-family: sans-serif; color: var(--muted);
  margin-bottom: 24px;
}
.sdot { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); flex-shrink: 0; }

/* ── LEADERBOARD CARD ── */
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; overflow: hidden; margin-bottom: 24px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.07);
}
.card-header {
  padding: 16px 20px 13px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.card-title {
  font-family: 'Playfair Display', 'EB Garamond', Georgia, serif;
  font-size: 1.1rem; font-weight: 700; color: var(--green);
}
.card-sub { font-size: 0.74rem; font-family: sans-serif; color: var(--muted); margin-top: 3px; }

/* ── TABLE ── */
.lb-table { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }
.lb-table th {
  text-align: center; padding: 8px 4px;
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--muted); border-bottom: 2px solid var(--border);
  background: var(--bg); white-space: nowrap; overflow: hidden;
}
.lb-table th:nth-child(1) { width: 28px; text-align: center; }
.lb-table th:nth-child(2) { width: 26%; text-align: left; }
.lb-table th:nth-child(3), .lb-table th:nth-child(4),
.lb-table th:nth-child(5), .lb-table th:nth-child(6) { width: 18.5%; }
.lb-table td {
  padding: 10px 4px; border-bottom: 1px solid var(--border);
  font-size: 0.82rem; vertical-align: middle; text-align: center;
  overflow: hidden;
}
.lb-table td:nth-child(1) { text-align: center; }
.lb-table td:nth-child(2) { text-align: left; overflow: hidden; }
.lb-table tr:last-child td { border-bottom: none; }
.lb-table tr:hover td { background: #f9f6ef; }

.rank-cell { color: var(--muted); font-size: 0.82rem; }
.rank-cell.gold { color: var(--gold); font-size: 1rem; }

/* ── PLAYER ROW STYLING ── */
.player-name {
  font-weight: 700; font-size: 0.95rem;
}
.name-link { text-decoration: none; }
.name-link:hover { text-decoration: underline; }

.score-pill {
  display: inline-block; padding: 3px 7px; border-radius: 14px;
  font-size: 0.78rem; font-weight: 700;
}
.pill-atp      { background: #e8f4ee; color: #1a6b3c; }
.pill-wta      { background: #f3e8f4; color: #6b1a6b; }
.pill-combined { background: #fff3dc; color: #7a5a00; }
.pill-none     { background: #f0f0f0; color: #aaa; }

.bar-wrap { margin-top: 5px; height: 3px; background: #e8e4dc; border-radius: 2px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 2px; transition: width 0.8s ease; }

/* ── SCORING RULES ── */
.rules-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px; padding: 16px;
}
.rule-item {
  background: var(--bg); border-radius: 9px; padding: 11px 12px;
  text-align: center; border: 1px solid var(--border);
}
.rule-round { font-size: 0.68rem; font-family: sans-serif; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
.rule-pts { font-size: 1.4rem; font-weight: 700; color: var(--green); font-family: 'EB Garamond', Georgia, serif; }
.rule-note { font-size: 0.66rem; font-family: sans-serif; color: var(--muted); margin-top: 2px; }
.rules-bonuses { padding: 0 16px 16px; display: flex; flex-wrap: wrap; gap: 8px; }
.bonus-tag {
  background: #fff8e6; border: 1px solid #e8d89a; border-radius: 7px;
  padding: 5px 11px; font-size: 0.77rem; font-family: sans-serif; color: #7a5a00;
}

/* ── EMPTY / ERROR ── */
.info-block {
  text-align: center; padding: 52px 20px; font-family: sans-serif; color: var(--muted);
}
.info-block .icon { font-size: 2.5rem; margin-bottom: 10px; }
.info-block h2 { font-size: 1.1rem; color: var(--green); margin-bottom: 6px; }
.info-block p { font-size: 0.88rem; line-height: 1.55; max-width: 360px; margin: 0 auto; }

.footer {
  text-align: center; font-family: sans-serif; font-size: 0.75rem;
  color: var(--muted); margin-top: 16px;
}

/* ── SETTINGS MODAL ── */
    #modal-overlay {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.45); z-index: 100;
      align-items: center; justify-content: center;
    }
    #modal-overlay.open { display: flex; }
    #modal {
      background: #fff; border-radius: 14px; width: 420px; max-width: 95vw;
      box-shadow: 0 8px 40px rgba(0,0,0,0.2); overflow: hidden;
    }
    .modal-header {
      background: var(--green); color: #fff; padding: 16px 20px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .modal-header h2 { font-size: 1rem; font-family: sans-serif; }
    #modal-close { background: none; border: none; color: #fff; font-size: 1.4rem; cursor: pointer; line-height: 1; }
    .modal-body { padding: 20px; }
    .modal-body label { font-size: 0.8rem; font-family: sans-serif; color: var(--muted); display: block; margin-bottom: 6px; }
    .input-row { display: flex; gap: 8px; margin-bottom: 14px; }
    #username-input {
      flex: 1; border: 1px solid var(--border); border-radius: 7px;
      padding: 8px 12px; font-size: 0.9rem; font-family: sans-serif; outline: none;
    }
    #username-input:focus { border-color: var(--green); }
    #add-btn {
      background: var(--green); color: #fff; border: none; border-radius: 7px;
      padding: 8px 16px; cursor: pointer; font-size: 0.9rem; font-family: sans-serif;
    }
    #members-list { list-style: none; margin-bottom: 16px; max-height: 200px; overflow-y: auto; }
    #members-list li {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 10px; border-radius: 7px; font-family: sans-serif; font-size: 0.88rem;
    }
    #members-list li:nth-child(odd) { background: var(--bg); }
    .remove-btn { background: none; border: none; color: #ef4444; cursor: pointer; font-size: 1rem; padding: 0 4px; }
    .modal-footer { border-top: 1px solid var(--border); padding: 14px 20px; display: flex; gap: 8px; flex-wrap: wrap; }
    #copy-btn, #save-btn {
      flex: 1; padding: 9px; border-radius: 8px; cursor: pointer;
      font-family: sans-serif; font-size: 0.88rem; border: none;
    }
    #copy-btn { background: var(--bg); border: 1px solid var(--border); color: var(--text); }
    #save-btn { background: var(--green); color: #fff; font-weight: 600; }
    .modal-hint { font-size: 0.72rem; font-family: sans-serif; color: var(--muted); width: 100%; text-align: center; }

    /* ── RESPONSIVE ── */
@media (max-width: 560px) {
  header { height: auto; padding: 12px 14px; flex-wrap: wrap; gap: 10px; }
}
</style>
</head>
<body>

<!-- TOP NAV -->
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-flag">🇬🇧</span>
    <span style="display:inline-flex;flex-direction:column;width:22px;height:14px;border-radius:2px;overflow:hidden;flex-shrink:0;box-shadow:0 1px 3px rgba(0,0,0,0.4);">
      <span style="flex:1;background:#1a3a6e;"></span>
      <span style="flex:1;background:#c8a020;"></span>
      <span style="flex:1;background:#1a3a6e;"></span>
      <span style="flex:1;background:#c8a020;"></span>
      <span style="flex:1;background:#1a3a6e;"></span>
    </span>
    <span>US Open 2026</span>
  </div>
  <div class="topbar-right">
    <div class="live-badge"><div class="live-dot"></div>LIVE</div>
    <button onclick="location.reload()" style="background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);color:#fff;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:0.75rem;font-family:sans-serif;white-space:nowrap;">↻ Refresh</button>
    <button onclick="copyInviteLink()" id="invite-btn" style="background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);color:#fff;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:0.75rem;font-family:sans-serif;white-space:nowrap;">🔗 Share</button>
    <button onclick="openModal()" style="background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);color:#fff;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:0.75rem;font-family:sans-serif;white-space:nowrap;">⚙ Group</button>
  </div>
</div>

<!-- HERO -->
<div class="hero">
  <div class="hero-inner">
    <div class="hero-trophy"><img src="data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABGAAD/4QN+aHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjYtYzEzOCA3OS4xNTk4MjQsIDIwMTYvMDkvMTQtMDE6MDk6MDEgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9IjlDMTYzRkE4OUM5NkU0MTQ3QkY2N0MwMDZCQUFGNDEyIiB4bXBNTTpEb2N1bWVudElEPSJ4bXAuZGlkOkZFMUQ0MzExMkFCNzExRTg5MjM2RUE5OEI0MEJFNUE0IiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOkZFMUQ0MzEwMkFCNzExRTg5MjM2RUE5OEI0MEJFNUE0IiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDQyAoTWFjaW50b3NoKSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjc2NTYzNGMxLWYxMzEtNDQ1Yy05MDY2LWI2NzBmZTdkMThkNyIgc3RSZWY6ZG9jdW1lbnRJRD0iYWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOmRhMzRiMzcxLTQxZDYtZTU0ZS05NjYyLWM0NjA2Njg1OTAwMSIvPiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gPD94cGFja2V0IGVuZD0iciI/Pv/uAA5BZG9iZQBkwAAAAAH/2wCEAAQDAwMDAwQDAwQGBAMEBgcFBAQFBwgGBgcGBggKCAkJCQkICgoMDAwMDAoMDA0NDAwRERERERQUFBQUFBQUFBQBBAUFCAcIDwoKDxQODg4UFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFP/AABEIA70GqAMBEQACEQEDEQH/xADGAAEAAQQDAQAAAAAAAAAAAAAAAQIGBwgDBQkEAQEAAQUBAQEAAAAAAAAAAAAAAQIDBAUGBwgJEAEAAQMCBAMFAgsFBAcHBQEAARECAwQFITEGB0ESCFFhcSITgTKRobHB0eFCUiMUFWJykjMWk1RVF0NTY3MkVhiCsoM0JTVF8PGiRCZGEQEAAQMCBAMGBAIJAwQDAQEAARECAyEEMUESBVETBmFxkSIyB4FCUhShM/BicpIjQ1MVFrGCF8HRJDTh8URjJf/aAAwDAQACEQMRAD8A1Pe5OIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH//2Q==" alt="US Open" style="height:70px;width:auto;filter:drop-shadow(0 2px 8px rgba(0,0,0,0.5));border-radius:4px;"></div>
    <div class="hero-text">
      <div class="hero-title">US Open <span>2026</span></div>
      <div class="hero-subtitle">The US Open · Flushing Meadows, New York</div>
    </div>
  </div>
  <div class="hero-pills">
    <span class="hero-pill">🎾 Men's &amp; Women's Draw</span>
    <span class="hero-pill gold">🏅 served.bracket.tennis</span>
  </div>
</div>

<!-- GRASS / S&C STRIP -->
<div class="sc-banner">
  <div class="sc-grass"><span></span><span></span><span></span><span></span><span></span></div>
  <span>🍈</span>
  <span>Page &amp; Will's US Open Challenge</span>
  <span>🍈</span>
  <div class="sc-grass"><span></span><span></span><span></span><span></span><span></span></div>
</div>

<!-- SETTINGS MODAL -->
<div id="modal-overlay" onclick="closeModalOutside(event)">
  <div id="modal">
    <div class="modal-header">
      <h2>⚙ Manage Group Members</h2>
      <button id="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <label>Add a served.bracket.tennis username</label>
      <div class="input-row">
        <input id="username-input" type="text" placeholder="e.g. jackthesnack21"
          onkeydown="if(event.key==='Enter') addMember()" />
        <button id="add-btn" onclick="addMember()">Add</button>
      </div>
      <label>Group members (<span id="member-count">0</span>)</label>
      <ul id="members-list"></ul>
    </div>
    <div class="modal-footer">
      <button id="invite-btn" onclick="copyInviteLink()" style="width:100%;padding:10px;border-radius:8px;cursor:pointer;font-family:sans-serif;font-size:0.9rem;font-weight:600;border:none;background:#4b006e;color:#fff;margin-bottom:8px;">📋 Copy Invite Link</button>
      <button id="save-btn" onclick="saveAndClose()">Save &amp; Refresh</button>
      <div class="modal-hint">Share the invite link — anyone who opens it sees the full group</div>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="status-bar">
    <div class="sdot"></div>
    <span id="status-text">Loading…</span>
  </div>

  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-title">Combined Standings</div>
        <div class="card-sub">ATP + WTA · served.bracket.tennis</div>
      </div>
    </div>
    <div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
    <table class="lb-table" style="min-width:520px;width:100%;table-layout:fixed;">
      <thead>
        <tr>
          <th>#</th>
          <th>Player</th>
          <th>Combined</th>
          <th>Mens</th>
          <th>Womens</th>
          <th>Max Pts</th>
          <th>Global</th>
        </tr>
      </thead>
      <tbody id="lb-body">
        <tr><td colspan="7" style="padding:32px;text-align:center;color:#aaa;font-family:sans-serif">Loading…</td></tr>
      </tbody>
    </table>
    </div>
  </div>

  <!-- TODAY'S MATCHES -->
  <div class="card" id="today-matches-card" style="margin-bottom:24px;">
    <div class="card-header" style="margin-bottom:0;">
      <div>
        <div class="card-title">🎾 Today's Matches</div>
        <div class="card-sub" id="today-matches-sub">US Open · Live &amp; Schedule</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button id="tm-btn-wta" onclick="switchMatchesTour('wta')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #4b006e;background:#4b006e;color:#fff;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Women's
        </button>
        <button id="tm-btn-atp" onclick="switchMatchesTour('atp')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #ddd8cc;background:#fff;color:#00512e;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Men's
        </button>
      </div>
    </div>
    <div id="today-matches-body" style="padding:12px 16px 16px;">
      <div style="text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;padding:24px;">Loading…</div>
    </div>
  </div>

  <!-- AI DAILY SUMMARY -->
  <div class="card" style="margin-bottom:24px;">
    <div class="card-header">
      <div>
        <div class="card-title">🎙 Today at the US Open</div>
        <div class="card-sub" id="summary-updated">Refreshes hourly</div>
      </div>
      <button onclick="loadSummary(true)" style="background:var(--bg);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 12px;cursor:pointer;font-size:0.75rem;font-family:sans-serif;">↻ Refresh</button>
    </div>
    <div id="summary-body" style="padding:14px 20px;font-family:'EB Garamond',Georgia,serif;font-size:0.97rem;line-height:1.6;color:#2a2a2a;">
      <span style="color:#aaa;font-family:sans-serif;font-size:0.85rem;">Loading today's recap…</span>
    </div>
  </div>

  <script>
  (function(){
    window.loadSummary = function(bust) {
      var url = bust ? '/api/summary?bust=' + Date.now() : '/api/summary';
      fetch(url)
        .then(function(r){ return r.json(); })
        .then(function(data){
          var el = document.getElementById('summary-body');
          var upd = document.getElementById('summary-updated');
          if (data.error === 'no_key') {
            el.innerHTML = '<span style="color:#aaa;font-family:sans-serif;font-size:0.82rem;">Add <code style="background:#f0f0f0;padding:1px 5px;border-radius:3px;">ANTHROPIC_API_KEY</code> to Render environment variables to enable AI recaps.</span>';
          } else if (data.error) {
            el.innerHTML = '<span style="color:#aaa;font-family:sans-serif;font-size:0.82rem;">Recap unavailable — ' + data.error + '</span>';
          } else if (data.summary) {
            var text = data.summary;
            var html = text
              .replace(/WOMEN'S:?/g, '<strong style="font-family:sans-serif;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#6b1a6b;">Women\'s</strong><br>')
              .replace(/MEN'S:?/g,   '<strong style="font-family:sans-serif;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#00512e;margin-top:8px;display:block;">Men\'s</strong><br>')
              .replace(/\n/g, '<br>');
            el.innerHTML = html;
            if (data.updated) upd.textContent = 'Updated · ' + data.updated;
          }
        })
        .catch(function(){});
    }
    window.loadSummary(false);
    setInterval(function(){ window.loadSummary(false); }, 60 * 60 * 1000);
  })();
  </script>

  <!-- LIVE BRACKET VISUALIZATION -->
  <div class="card" id="bracket-card" style="margin-bottom:24px;overflow:hidden;">
    <div class="card-header" style="margin-bottom:0;flex-wrap:wrap;gap:10px;">
      <div>
        <div class="card-title">🎾 Live Bracket</div>
        <div class="card-sub">Real-time draw · served.bracket.tennis</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <!-- Player pick filter -->
        <select id="player-pick-select" onchange="switchPickFilter(this.value)"
          style="padding:5px 10px;border-radius:100px;border:2px solid #1a3a6e;background:#fff;color:#1a3a6e;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;outline:none;">
          <option value="">👤 All picks</option>
        </select>
        <button id="btn-atp" onclick="switchBracketTour('atp')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #00512e;background:#00512e;color:#fff;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Men's
        </button>
        <button id="btn-wta" onclick="switchBracketTour('wta')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #ddd8cc;background:#fff;color:#4b006e;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Women's
        </button>
        <a id="bracket-ext-link" href="https://served.bracket.tennis/tournaments/__SLUG__/atp/bracket"
           target="_blank" rel="noopener"
           style="padding:6px 12px;border-radius:100px;border:1px solid #ddd8cc;background:#f9f7f4;color:#6b6b6b;font-size:0.72rem;font-family:sans-serif;text-decoration:none;white-space:nowrap;">
          Full ↗
        </a>
      </div>
    </div>
    <!-- Pick legend (shown only when a player is selected) -->
    <div id="pick-legend" style="display:none;padding:8px 20px 0;font-size:0.72rem;font-family:sans-serif;color:#666;gap:16px;flex-wrap:wrap;">
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#d4f0dc;border:1px solid #9ecfad;vertical-align:middle;margin-right:4px;"></span><span style="color:#00512e;font-weight:700;">Correct pick</span></span>
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#ffe0e0;border:1px solid #e8a0a0;vertical-align:middle;margin-right:4px;"></span><span style="color:#c0392b;font-weight:700;">Eliminated</span></span>
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#fff;border:1px solid #e0dbd0;vertical-align:middle;margin-right:4px;"></span><span style="color:#666;font-weight:700;">Future pick</span></span>
    </div>

    <!-- Single scrollable container: labels + bracket scroll together -->
    <div id="bracket-scroll" style="overflow-x:auto;overflow-y:auto;max-height:520px;background:#fafaf8;-webkit-overflow-scrolling:touch;">
      <div id="bracket-round-labels" style="display:flex;position:sticky;top:0;z-index:5;background:#f0ede6;border-bottom:1px solid #e8e4d8;">
      </div>
      <div id="bracket-body">
        <div style="padding:40px;text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;">Loading bracket…</div>
      </div>
    </div>
  </div>

  <script>
  (function(){
    var _bTour = 'atp';
    var _bCache = {};
    var _bPickUser = '';
    var _bPicksCache = {}; // "user:tour" -> picks dict

    window.switchBracketTour = function(tour) {
      _bTour = tour;
      document.getElementById('btn-atp').style.background = tour === 'atp' ? '#00512e' : '#fff';
      document.getElementById('btn-atp').style.color = tour === 'atp' ? '#fff' : '#00512e';
      document.getElementById('btn-atp').style.borderColor = tour === 'atp' ? '#00512e' : '#ddd8cc';
      document.getElementById('btn-wta').style.background = tour === 'wta' ? '#4b006e' : '#fff';
      document.getElementById('btn-wta').style.color = tour === 'wta' ? '#fff' : '#4b006e';
      document.getElementById('btn-wta').style.borderColor = tour === 'wta' ? '#4b006e' : '#ddd8cc';
      document.getElementById('bracket-ext-link').href =
        'https://served.bracket.tennis/tournaments/__SLUG__/' + tour + '/bracket';
      loadBracket(tour);
    };

    window.switchPickFilter = function(username) {
      _bPickUser = username;
      var legend = document.getElementById('pick-legend');
      legend.style.display = username ? 'flex' : 'none';
      var sub = document.querySelector('#bracket-card .card-sub');
      if (sub) sub.textContent = username
        ? (username + "’s predicted bracket")
        : "Real-time draw · served.bracket.tennis";
      loadBracket(_bTour);
    };

    // Populate player dropdown from current group members
    window._populatePickDropdown = function(members) {
      var sel = document.getElementById('player-pick-select');
      // Keep first "All picks" option, rebuild the rest
      while (sel.options.length > 1) sel.remove(1);
      (members || []).forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        sel.appendChild(opt);
      });
    };

    function fetchPicks(user, tour, callback) {
      var key = user + ':' + tour;
      if (_bPicksCache[key]) { callback(_bPicksCache[key]); return; }
      var membersParam = (window._currentMembers && window._currentMembers.length)
        ? '&members=' + encodeURIComponent(window._currentMembers.join(',')) : '';
      fetch('/api/picks?user=' + encodeURIComponent(user) + '&tour=' + tour + membersParam)
        .then(function(r){ return r.json(); })
        .then(function(data){
          _bPicksCache[key] = data.picks || {};
          callback(_bPicksCache[key]);
        })
        .catch(function(){ callback({}); });
    }

    function loadBracket(tour, bustCache) {
      var body = document.getElementById('bracket-body');
      var labelsEl = document.getElementById('bracket-round-labels');
      if (bustCache) { delete _bCache[tour]; _bPicksCache = {}; }

      function doRender(data) {
        if (_bPickUser) {
          fetchPicks(_bPickUser, tour, function(picks) {
            renderPickBracket(picks, body, labelsEl);
          });
        } else {
          renderBracket(data, body, labelsEl, {});
        }
      }

      if (_bCache[tour]) { doRender(_bCache[tour]); return; }
      var membersParam = (window._currentMembers && window._currentMembers.length)
        ? '&members=' + encodeURIComponent(window._currentMembers.join(',')) : '';
      fetch('/api/bracket?tour=' + tour + membersParam)
        .then(function(r){ return r.json(); })
        .then(function(data){
          _bCache[tour] = data;
          doRender(data);
        })
        .catch(function(e){
          if (!_bCache[tour])
            body.innerHTML = '<div style="padding:40px;text-align:center;color:#c0392b;font-size:0.85rem;font-family:sans-serif;">Could not load bracket.</div>';
        });
    }

    // Re-poll every 45 s to pick up live score/status changes
    setInterval(function(){ loadBracket(_bTour, true); }, 45000);

    var ROUND_LABELS = ['','R1','R2','R3','R4','QF','SF','F'];
    var ROUND_COLORS = {
      1:'#00512e', 2:'#006b3c', 3:'#007a45', 4:'#3a7d2e',
      5:'#7d5a00', 6:'#a0006b', 7:'#4b006e'
    };
    var COL_W = 162;  // px per round column (wider for flag + name)
    var ROW_H = 22;   // px per player row
    var TOTAL_H = 3200; // px — 64 R1 slots × 50px

    // ITF 3-letter → ISO 2-letter
    var ISO2 = {
      'USA':'US','GBR':'GB','ESP':'ES','FRA':'FR','GER':'DE','AUS':'AU',
      'ITA':'IT','SRB':'RS','RUS':'RU','ARG':'AR','CAN':'CA','CHN':'CN',
      'JPN':'JP','BEL':'BE','NED':'NL','SUI':'CH','DEN':'DK','NOR':'NO',
      'SWE':'SE','CZE':'CZ','POL':'PL','HUN':'HU','GRE':'GR','CRO':'HR',
      'BUL':'BG','ROU':'RO','UKR':'UA','KAZ':'KZ','BRA':'BR','CHI':'CL',
      'COL':'CO','MEX':'MX','RSA':'ZA','EGY':'EG','TUN':'TN','MAR':'MA',
      'KOR':'KR','TPE':'TW','IND':'IN','THA':'TH','MAS':'MY','SGP':'SG',
      'NZL':'NZ','AUT':'AT','SVK':'SK','SLO':'SI','FIN':'FI','POR':'PT',
      'MDA':'MD','LTU':'LT','LAT':'LV','EST':'EE','GEO':'GE','ARM':'AM',
      'AZE':'AZ','UZB':'UZ','BAH':'BS','ECU':'EC','PER':'PE','URU':'UY',
      'TUR':'TR','ISR':'IL','QAT':'QA','UAE':'AE','KUW':'KW','BLR':'BY',
      'CYP':'CY','LUX':'LU','MON':'MC','BIH':'BA','MKD':'MK','ALB':'AL',
      'PAK':'PK','VIE':'VN','PHI':'PH','INA':'ID','SRI':'LK','NEP':'NP',
      'CHI':'CL','PAR':'PY','VEN':'VE','BOL':'BO','DOM':'DO','PUR':'PR',
    };

    function countryFlag(code) {
      if (!code) return '';
      var c2 = ISO2[code] || (code.length === 2 ? code : null);
      if (!c2) return '';
      var o = 127397; // 0x1F1E6 - 65
      try {
        return String.fromCodePoint(c2.charCodeAt(0) + o, c2.charCodeAt(1) + o);
      } catch(e) { return ''; }
    }

    function lastName(name) {
      if (!name) return 'TBD';
      var parts = name.trim().split(' ');
      return parts[parts.length - 1];
    }

    function formatSetScore(score) {
      return (typeof score === 'string' && score.length) ? score : null;
    }

    function renderBracket(data, container, labelsEl, picks) {
      picks = picks || {};
      var matches = data.matches || [];
      if (!matches.length) {
        container.innerHTML = '<div style="padding:40px;text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;">No bracket data yet.</div>';
        labelsEl.innerHTML = '';
        return;
      }

      // Build live-player lookup from ESPN overlay
      var liveSet = {};
      (data.live_players || []).forEach(function(n){ liveSet[n] = true; });
      var espnScores = data.espn_scores || {};

      // Group by round, sort by pos
      var rounds = {};
      var maxRound = 0;
      matches.forEach(function(m) {
        if (!rounds[m.round]) rounds[m.round] = [];
        rounds[m.round].push(m);
        if (m.round > maxRound) maxRound = m.round;
      });
      for (var r in rounds) rounds[r].sort(function(a,b){ return a.pos - b.pos; });

      // Build round labels bar (synced scroll with bracket body)
      labelsEl.innerHTML = '';
      labelsEl.style.display = 'flex';
      labelsEl.style.minWidth = (maxRound * (COL_W + 1)) + 'px';
      for (var rn = 1; rn <= maxRound; rn++) {
        var lbl = document.createElement('div');
        lbl.style.cssText = 'width:' + COL_W + 'px;flex-shrink:0;text-align:center;padding:5px 0 6px;font-size:0.7rem;font-weight:700;letter-spacing:1px;font-family:sans-serif;color:' + (ROUND_COLORS[rn] || '#333') + ';border-right:1px solid #e8e4d8;';
        lbl.textContent = ROUND_LABELS[rn] || ('R' + rn);
        labelsEl.appendChild(lbl);
      }

      // Build bracket
      var wrap = document.createElement('div');
      wrap.style.cssText = 'display:flex;height:' + TOTAL_H + 'px;';

      for (var rv = 1; rv <= maxRound; rv++) {
        var rMatches = rounds[rv] || [];
        var col = document.createElement('div');
        col.style.cssText = 'display:flex;flex-direction:column;width:' + COL_W + 'px;flex-shrink:0;border-right:1px solid #e8e4d8;';

        rMatches.forEach(function(m) {
          var isLive = !!m.is_live;
          var isComplete = !!m.winner;

          // Pick overlay for this match
          var pickKey = m.round + ':' + m.pos;
          var matchPick = picks[pickKey] || null; // {player, status}

          var slot = document.createElement('div');
          slot.style.cssText = 'flex:1;display:flex;align-items:center;padding:0 3px;';

          var cardBorder = isLive ? '0 0 0 2px #c0392b'
            : (matchPick ? '0 0 0 2px ' + (matchPick.status === 'correct' ? '#c8a020' : matchPick.status === 'wrong' || matchPick.status === 'eliminated' ? '#c0392b' : '#1a3a6e') : '0 1px 3px rgba(0,0,0,0.08)');
          var card = document.createElement('div');
          card.style.cssText = 'width:100%;border-radius:4px;overflow:hidden;box-shadow:' + cardBorder + ';';

          // For future matches, inject predicted player into first TBD slot
          var displayPlayers = [
            { name: m.p1, rank: m.p1_rank, country: m.p1_country },
            { name: m.p2, rank: m.p2_rank, country: m.p2_country }
          ];
          if (matchPick && matchPick.status === 'future') {
            var tbdIdx = displayPlayers.findIndex(function(p) { return !p.name; });
            if (tbdIdx >= 0) {
              displayPlayers[tbdIdx] = { name: matchPick.player, rank: null, country: null, isPrediction: true };
            }
          }

          displayPlayers.forEach(function(p, pi) {
            var isWinner = isComplete && m.winner === p.name;
            var isLoser  = isComplete && m.winner !== p.name && !!p.name;
            var isTbd    = !p.name;

            // Per-player pick state
            var isPrediction = !!p.isPrediction;
            var isPicked = isPrediction || (matchPick && matchPick.player === p.name);
            var pickStatus = isPicked ? matchPick.status : null;

            // Background/border: pick overlay takes priority over win/loss colouring
            var bgColor, textColor, borderColor, fontWeight;
            if (isPrediction) {
              bgColor = '#eef2fa'; textColor = '#1a3a6e'; borderColor = '#7a9fd4'; fontWeight = '600';
            } else if (isPicked && pickStatus === 'correct') {
              bgColor = '#fffbe6'; textColor = '#7a5c00'; borderColor = '#e6c84a'; fontWeight = '700';
            } else if (isPicked && pickStatus === 'wrong') {
              bgColor = '#fff0f0'; textColor = '#c0392b'; borderColor = '#e8a0a0'; fontWeight = '600';
            } else if (isPicked && pickStatus === 'eliminated') {
              bgColor = '#f5f5f5'; textColor = '#999'; borderColor = '#ccc'; fontWeight = '400';
            } else if (isPicked) { // future
              bgColor = '#eef2fa'; textColor = '#1a3a6e'; borderColor = '#7a9fd4'; fontWeight = '600';
            } else if (isWinner) {
              bgColor = '#d4f0dc'; textColor = '#00512e'; borderColor = '#9ecfad'; fontWeight = '600';
            } else if (isLive) {
              bgColor = '#fff5f5'; textColor = '#1a1a1a'; borderColor = '#e8a0a0'; fontWeight = '400';
            } else if (isTbd) {
              bgColor = '#f5f4f0'; textColor = '#ccc'; borderColor = '#e0dbd0'; fontWeight = '400';
            } else {
              bgColor = '#fff'; textColor = isLoser ? '#999' : '#1a1a1a'; borderColor = '#e0dbd0'; fontWeight = '400';
            }

            var row = document.createElement('div');
            row.style.cssText = [
              'height:' + ROW_H + 'px',
              'line-height:' + ROW_H + 'px',
              'padding:0 5px',
              'font-size:10.5px',
              'font-family:sans-serif',
              'display:flex',
              'align-items:center',
              'justify-content:space-between',
              'border:1px solid ' + borderColor,
              pi === 0 ? 'border-bottom:1px solid ' + borderColor : '',
              'background:' + bgColor,
              'color:' + textColor,
              'font-weight:' + fontWeight,
            ].join(';');

            var flag = p.country ? countryFlag(p.country) : '';
            var seed = (p.rank && p.rank <= 32) ? '[' + p.rank + ']' : '';
            var nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;font-style:' + (isPrediction ? 'italic' : 'normal') + ';';
            nameSpan.textContent = (flag ? flag + ' ' : '') + (seed ? seed + ' ' : '') + lastName(p.name);
            row.appendChild(nameSpan);

            // Pick badge
            if (isPrediction) {
              var badge = document.createElement('span');
              badge.style.cssText = 'flex-shrink:0;font-size:9px;font-weight:700;color:#1a3a6e;margin-left:4px;background:#d0dff5;border-radius:3px;padding:0 3px;';
              badge.textContent = 'PICK';
              row.appendChild(badge);
            } else if (isPicked) {
              var badge = document.createElement('span');
              var badgeIcon = pickStatus === 'correct' ? '✓' : pickStatus === 'wrong' || pickStatus === 'eliminated' ? '✗' : '●';
              var badgeColor = pickStatus === 'correct' ? '#c8a020' : pickStatus === 'wrong' || pickStatus === 'eliminated' ? '#c0392b' : '#1a3a6e';
              badge.style.cssText = 'flex-shrink:0;font-size:10px;font-weight:700;color:' + badgeColor + ';margin-left:4px;';
              badge.textContent = badgeIcon;
              row.appendChild(badge);
            } else if (isLive && pi === 0) {
              var dot = document.createElement('span');
              dot.style.cssText = 'flex-shrink:0;width:6px;height:6px;border-radius:50%;background:#c0392b;margin-left:4px;animation:blink 1.5s ease-in-out infinite;display:inline-block;';
              row.appendChild(dot);
            }

            card.appendChild(row);
          });

          var scoreStr = (isComplete || isLive) ? formatSetScore(m.score) : null;

          if (scoreStr) {
            var scoreRow = document.createElement('div');
            scoreRow.style.cssText = 'padding:2px 6px 3px;font-size:9.5px;font-family:sans-serif;'
              + 'color:' + (isLive ? '#c0392b' : '#888') + ';'
              + 'background:' + (isLive ? '#fff0f0' : '#f7f5f0') + ';'
              + 'border:1px solid ' + (isLive ? '#e8a0a0' : '#e0dbd0') + ';border-top:none;'
              + 'letter-spacing:0.5px;';
            scoreRow.textContent = isLive ? '● ' + scoreStr : scoreStr;
            card.appendChild(scoreRow);
          }

          slot.appendChild(card);
          col.appendChild(slot);
        });

        wrap.appendChild(col);
      }

      container.innerHTML = '';
      container.appendChild(wrap);
    }

    // Static predicted bracket for a selected group member
    function renderPickBracket(picks, container, labelsEl) {
      if (!picks || !Object.keys(picks).length) {
        container.innerHTML = '<div style="padding:40px;text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;">No picks found for this user.</div>';
        labelsEl.innerHTML = '';
        return;
      }

      var maxRound = 7;
      var TOTAL_PH = 3200;
      var PICK_H   = 22;   // single card height
      var PAIR_GAP = 3;    // gap between the two matchup cards

      // Round labels
      labelsEl.innerHTML = '';
      labelsEl.style.display = 'flex';
      labelsEl.style.minWidth = (maxRound * (COL_W + 1)) + 'px';
      for (var rn = 1; rn <= maxRound; rn++) {
        var lbl = document.createElement('div');
        lbl.style.cssText = 'width:' + COL_W + 'px;flex-shrink:0;text-align:center;padding:5px 0 6px;font-size:0.7rem;font-weight:700;letter-spacing:1px;font-family:sans-serif;color:' + (ROUND_COLORS[rn] || '#333') + ';border-right:1px solid #e8e4d8;';
        lbl.textContent = ROUND_LABELS[rn] || ('R' + rn);
        labelsEl.appendChild(lbl);
      }

      var wrap = document.createElement('div');
      wrap.style.cssText = 'display:flex;height:' + TOTAL_PH + 'px;position:relative;';

      // Build set of players already eliminated (wrong pick in any round)
      var eliminatedPlayers = {};
      Object.keys(picks).forEach(function(k) {
        var p = picks[k];
        if (p && p.player && (p.status === 'wrong' || p.status === 'eliminated')) {
          eliminatedPlayers[p.player] = true;
        }
      });

      // Resolve effective status — cascade eliminations forward
      function effectiveStatus(pick) {
        if (!pick) return 'none';
        if (pick.status !== 'future') return pick.status;
        if (pick.player && eliminatedPlayers[pick.player]) return 'eliminated';
        return 'future';
      }

      // Helper: create a single pick card
      function makeCard(playerName, status, isLoser) {
        var bg, color, fw, borderColor, deco;
        if (isLoser) {
          // Other participant in a matchup — dimmed
          bg = '#f5f4f0'; color = '#bbb'; fw = '400'; borderColor = '#e8e4d8'; deco = 'none';
        } else if (!playerName) {
          bg = '#f5f4f0'; color = '#bbb'; fw = '400'; borderColor = '#e8e4d8'; deco = 'none';
        } else if (status === 'correct') {
          bg = '#d4f0dc'; color = '#00512e'; fw = '700'; borderColor = '#9ecfad'; deco = 'none';
        } else if (status === 'wrong' || status === 'eliminated') {
          bg = '#ffe0e0'; color = '#c0392b'; fw = '400'; borderColor = '#e8a0a0'; deco = 'line-through';
        } else {
          bg = '#fff'; color = '#1a1a1a'; fw = '400'; borderColor = '#e0dbd0'; deco = 'none';
        }
        var d = document.createElement('div');
        d.style.cssText = [
          'left:4px','right:4px',
          'height:' + PICK_H + 'px',
          'line-height:' + PICK_H + 'px',
          'padding:0 6px',
          'font-size:10.5px',
          'font-family:sans-serif',
          'font-weight:' + fw,
          'color:' + color,
          'background:' + bg,
          'border:1px solid ' + borderColor,
          'border-radius:4px',
          'white-space:nowrap',
          'overflow:hidden',
          'text-overflow:ellipsis',
          'box-sizing:border-box',
          'text-decoration:' + deco,
          'position:absolute',
        ].join(';');
        d.textContent = playerName ? lastName(playerName) : '—';
        return d;
      }

      for (var rnd = 1; rnd <= maxRound; rnd++) {
        var matchCount = Math.round(64 / Math.pow(2, rnd - 1));
        var slotH = TOTAL_PH / matchCount;

        var col = document.createElement('div');
        col.style.cssText = 'width:' + COL_W + 'px;flex-shrink:0;border-right:1px solid #e8e4d8;position:relative;height:' + TOTAL_PH + 'px;';

        for (var pos = 1; pos <= matchCount; pos++) {
          var centerY = (pos - 0.5) * slotH;
          var winKey = rnd + ':' + pos;
          var winPick = picks[winKey];

          if (rnd === 1) {
            // R1: single card — just show the predicted winner
            var c = makeCard(winPick ? winPick.player : null, effectiveStatus(winPick), false);
            c.style.top = Math.round(centerY - PICK_H / 2) + 'px';
            col.appendChild(c);
          } else {
            // R2+: show both participants (from previous round picks) + highlight winner
            var p1Key = (rnd - 1) + ':' + (2 * pos - 1);
            var p2Key = (rnd - 1) + ':' + (2 * pos);
            var p1Pick = picks[p1Key];
            var p2Pick = picks[p2Key];

            var p1Name = p1Pick ? p1Pick.player : null;
            var p2Name = p2Pick ? p2Pick.player : null;
            var winName = winPick ? winPick.player : null;

            // Determine which participant is the predicted winner
            var p1IsWinner = winName && p1Name && (winName === p1Name);
            var p2IsWinner = winName && p2Name && (winName === p2Name);

            // Top card = p1, bottom card = p2
            var pairH = PICK_H * 2 + PAIR_GAP;
            var topY   = Math.round(centerY - pairH / 2);
            var botY   = topY + PICK_H + PAIR_GAP;

            // isLoser (gray/dim) only applies if the player is a genuine "predicted loser" here
            // — NOT if they were already eliminated in a prior round (those must stay red).
            var p1Eliminated = p1Name && eliminatedPlayers[p1Name];
            var p2Eliminated = p2Name && eliminatedPlayers[p2Name];

            var c1 = makeCard(p1Name,
              p1IsWinner ? effectiveStatus(winPick) : effectiveStatus(p1Pick),
              !p1IsWinner && winName !== null && !p1Eliminated
            );
            c1.style.top = topY + 'px';

            var c2 = makeCard(p2Name,
              p2IsWinner ? effectiveStatus(winPick) : effectiveStatus(p2Pick),
              !p2IsWinner && winName !== null && !p2Eliminated
            );
            c2.style.top = botY + 'px';

            col.appendChild(c1);
            col.appendChild(c2);

            // Bracket connector line between the two cards
            var line = document.createElement('div');
            var lineTop = topY + PICK_H;
            line.style.cssText = 'position:absolute;left:4px;right:4px;top:' + lineTop + 'px;height:' + PAIR_GAP + 'px;border-left:1px solid #d0ccc0;border-right:1px solid #d0ccc0;';
            col.appendChild(line);
          }
        }

        wrap.appendChild(col);
      }

      container.innerHTML = '';
      container.appendChild(wrap);
    }

    // Load ATP bracket on page load (after a short delay so scores load first)
    setTimeout(function(){ loadBracket('atp'); }, 800);
  })();
  </script>

  <script>
  // TODAY'S MATCHES
  (function() {
    var ROUND_NAMES = ['','R1','R2','R3','R4','QF','SF','F'];
    var membersParam = (window._currentMembers && window._currentMembers.length)
      ? '?members=' + encodeURIComponent(window._currentMembers.join(',')) : '';

    // Map 3-letter IOC country codes → 2-letter ISO (for flag emoji)
    var CC = {
      ARG:'AR',ARM:'AM',AUS:'AU',AUT:'AT',AZE:'AZ',BEL:'BE',BIH:'BA',BLR:'BY',BOL:'BO',BRA:'BR',
      BUL:'BG',CAN:'CA',CHI:'CL',CHN:'CN',COL:'CO',CRO:'HR',CZE:'CZ',DEN:'DK',ECU:'EC',EGY:'EG',
      ESP:'ES',EST:'EE',FIN:'FI',FRA:'FR',GBR:'GB',GEO:'GE',GER:'DE',GRE:'GR',HKG:'HK',HUN:'HU',
      INA:'ID',IND:'IN',IRI:'IR',ISR:'IL',ITA:'IT',JPN:'JP',KAZ:'KZ',KOR:'KR',LAT:'LV',LTU:'LT',
      MAS:'MY',MDA:'MD',MEX:'MX',MKD:'MK',MAR:'MA',NED:'NL',NOR:'NO',NZL:'NZ',PAR:'PY',PER:'PE',
      PHI:'PH',POL:'PL',POR:'PT',QAT:'QA',ROU:'RO',RSA:'ZA',RUS:'RU',SGP:'SG',SLO:'SI',
      SRB:'RS',SUI:'CH',SVK:'SK',SWE:'SE',THA:'TH',TPE:'TW',TUN:'TN',UAE:'AE',UKR:'UA',
      URU:'UY',USA:'US',UZB:'UZ',VEN:'VE',VIE:'VN'
    };
    function flagOf(code) {
      if (!code) return '';
      var iso = CC[code.toUpperCase()] || (code.length === 2 ? code.toUpperCase() : null);
      if (!iso) return '';
      return iso.toUpperCase().replace(/./g, function(c) {
        return String.fromCodePoint(c.charCodeAt(0) + 127397);
      }) + ' ';
    }
    function fmtName(full) {
      if (!full) return 'TBD';
      var parts = full.trim().split(/\s+/);
      if (parts.length === 1) return full;
      return parts[0][0] + '. ' + parts.slice(1).join(' ');
    }

    var _tmAtp = [];
    var _tmWta = [];
    var _tmIsEspn = false;
    var _tmTour = 'wta';  // default to women's on open

    window.switchMatchesTour = function(tour) {
      _tmTour = tour;
      document.getElementById('tm-btn-atp').style.cssText =
        'padding:6px 16px;border-radius:100px;border:2px solid ' + (tour==='atp'?'#00512e':'#ddd8cc') +
        ';background:' + (tour==='atp'?'#00512e':'#fff') +
        ';color:' + (tour==='atp'?'#fff':'#00512e') +
        ';font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;';
      document.getElementById('tm-btn-wta').style.cssText =
        'padding:6px 16px;border-radius:100px;border:2px solid ' + (tour==='wta'?'#4b006e':'#ddd8cc') +
        ';background:' + (tour==='wta'?'#4b006e':'#fff') +
        ';color:' + (tour==='wta'?'#fff':'#4b006e') +
        ';font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;';
      _renderActiveTour();
    };

    // matchRow and buildSection live in outer scope so _renderActiveTour can call them
    function matchRow(m, state, espnCtx) {
      var p1 = fmtName(m.p1);
      var p2 = fmtName(m.p2);
      var p1f = flagOf(m.p1_country);
      var p2f = flagOf(m.p2_country);
      var seed1 = (m.p1_rank && m.p1_rank <= 32) ? ' <span style="color:#bbb;font-size:0.68rem;">[' + m.p1_rank + ']</span>' : '';
      var seed2 = (m.p2_rank && m.p2_rank <= 32) ? ' <span style="color:#bbb;font-size:0.68rem;">[' + m.p2_rank + ']</span>' : '';
      var rowBg = state === 'live' ? 'rgba(192,57,43,0.04)' : '';

      var dot;
      if (state === 'live') {
        dot = '<span style="width:8px;height:8px;border-radius:50%;background:#c0392b;display:inline-block;flex-shrink:0;animation:blink 1.5s ease-in-out infinite;"></span>';
      } else if (state === 'done') {
        dot = '<span style="color:#00512e;font-size:0.82rem;line-height:1;flex-shrink:0;">&#10003;</span>';
      } else {
        dot = '<span style="width:8px;height:8px;border-radius:50%;border:1.5px solid #ccc;display:inline-block;flex-shrink:0;"></span>';
      }

      var right;
      if (m.score) {
        right = '<span style="color:' + (state==='live'?'#c0392b':'#555') + ';font-size:0.75rem;white-space:nowrap;">' + m.score + '</span>';
      } else if (state === 'upcoming' && m.scheduled_time) {
        right = '<span style="color:#888;font-size:0.72rem;white-space:nowrap;">' + m.scheduled_time + '</span>';
      } else {
        right = '<span style="color:#ccc;font-size:0.75rem;">—</span>';
      }

      var p1w = m.winner && (m.winner === m.p1 || (espnCtx && m.p1 && m.winner.indexOf(m.p1.split('. ')[1] || m.p1) !== -1));
      var p2w = m.winner && (m.winner === m.p2 || (espnCtx && m.p2 && m.winner.indexOf(m.p2.split('. ')[1] || m.p2) !== -1));
      var p1style = p1w ? 'font-weight:700;color:#1a1a1a;' : (m.winner ? 'color:#aaa;' : 'color:#1a1a1a;');
      var p2style = p2w ? 'font-weight:700;color:#1a1a1a;' : (m.winner ? 'color:#aaa;' : 'color:#1a1a1a;');

      var players = '<div style="' + p1style + 'font-size:0.82rem;line-height:1.4;">' + p1f + p1 + seed1 + '</div>'
        + '<div style="' + p2style + 'font-size:0.82rem;line-height:1.4;">' + p2f + p2 + seed2 + '</div>';

      return '<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #f0ede6;background:' + rowBg + ';">'
        + '<div style="display:flex;align-items:center;justify-content:center;width:14px;flex-shrink:0;">' + dot + '</div>'
        + '<div style="flex:1;min-width:0;font-family:sans-serif;">' + players + '</div>'
        + '<div style="flex-shrink:0;text-align:right;">' + right + '</div>'
        + '</div>';
    }

    function buildSection(matches, espnCtx) {
      if (!matches || !matches.length) return '<div style="text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;padding:20px;">No matches today.</div>';
      var live, done, upcoming;
      if (espnCtx) {
        live     = matches.filter(function(m){ return m.status === 'live'; });
        done     = matches.filter(function(m){ return m.status === 'final'; });
        upcoming = matches.filter(function(m){ return m.status === 'upcoming'; });
      } else {
        live     = matches.filter(function(m){ return m.is_live; });
        done     = matches.filter(function(m){ return m.winner && !m.is_live && m.completed_today; });
        upcoming = matches.filter(function(m){ return !m.winner && !m.is_live; });
      }
      // Sort upcoming: TBD goes last, others by time string
      upcoming.sort(function(a, b) {
        var at = a.scheduled_time || '', bt = b.scheduled_time || '';
        var aLast = !at || at === 'TBD';
        var bLast = !bt || bt === 'TBD';
        if (aLast && !bLast) return 1;
        if (!aLast && bLast) return -1;
        return at.localeCompare(bt);
      });
      var rows = '';
      live.forEach(function(m)    { rows += matchRow(m, 'live', espnCtx);     });
      done.forEach(function(m)    { rows += matchRow(m, 'done', espnCtx);     });
      upcoming.forEach(function(m){ rows += matchRow(m, 'upcoming', espnCtx); });
      return rows || '<div style="text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;padding:20px;">No matches today.</div>';
    }

    function _renderActiveTour() {
      var matches = _tmTour === 'atp' ? _tmAtp : _tmWta;
      document.getElementById('today-matches-body').innerHTML =
        '<div style="padding:0 0 4px;">' + buildSection(matches, _tmIsEspn) + '</div>';
    }

    function renderMatches(atpData, wtaData, isEspn) {
      var sub = document.getElementById('today-matches-sub');

      function getActiveRound(matches) {
        var minPending = 99;
        matches.forEach(function(m) {
          if (!m.winner || m.is_live) { if (m.round < minPending) minPending = m.round; }
        });
        return minPending === 99 ? 1 : minPending;
      }

      _tmIsEspn = isEspn;
      if (isEspn) {
        _tmAtp = atpData;
        _tmWta = wtaData;
        sub.textContent = "US Open \xb7 Today";
      } else {
        var atpRound = getActiveRound(atpData);
        var wtaRound = getActiveRound(wtaData);
        sub.textContent = "Men's " + (ROUND_NAMES[atpRound]||'') + " \xb7 Women's " + (ROUND_NAMES[wtaRound]||'');
        function matchesForRound(matches, rnd) {
          return matches.filter(function(m){ return m.round === rnd; }).sort(function(a,b){ return a.pos - b.pos; });
        }
        _tmAtp = matchesForRound(atpData, atpRound);
        _tmWta = matchesForRound(wtaData, wtaRound);
      }

      _renderActiveTour();
    }

    function loadTodayMatches() {
      var mp = (window._currentMembers && window._currentMembers.length)
        ? '?members=' + encodeURIComponent(window._currentMembers.join(',')) : '';

      // Try ESPN first (has today-only data + match times), fall back to bracket data
      Promise.all([
        fetch('/api/today_matches?tour=atp').then(function(r){ return r.json(); }),
        fetch('/api/today_matches?tour=wta').then(function(r){ return r.json(); })
      ]).then(function(results) {
        var atpMs = results[0].matches || [];
        var wtaMs = results[1].matches || [];
        // If ESPN returned data, use it; otherwise fall back to bracket
        if (atpMs.length > 0 || wtaMs.length > 0) {
          renderMatches(atpMs, wtaMs, true);
        } else {
          return loadTodayMatchesFallback(mp);
        }
      }).catch(function() {
        loadTodayMatchesFallback(mp);
      });
    }

    function loadTodayMatchesFallback(mp) {
      Promise.all([
        fetch('/api/bracket?tour=atp' + (mp ? '&' + mp.slice(1) : '')).then(function(r){ return r.json(); }),
        fetch('/api/bracket?tour=wta' + (mp ? '&' + mp.slice(1) : '')).then(function(r){ return r.json(); })
      ]).then(function(results) {
        renderMatches(results[0].matches || [], results[1].matches || [], false);
      }).catch(function() {
        document.getElementById('today-matches-body').innerHTML =
          '<div style="text-align:center;color:#aaa;font-size:0.85rem;padding:20px;font-family:sans-serif;">Could not load match data.</div>';
      });
    }

    loadTodayMatches();
    setInterval(loadTodayMatches, 60000);
  })();
  </script>

  <!-- DRAFTKINGS ODDS -->
  <div class="card" style="margin-bottom:24px;">
    <div class="card-header" style="margin-bottom:0;">
      <div>
        <div class="card-title">📊 US Open Odds</div>
        <div class="card-sub">Outright winner · DraftKings · updated September 3</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button id="odds-btn-atp" onclick="switchOddsTour('atp')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #00512e;background:#00512e;color:#fff;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Men's
        </button>
        <button id="odds-btn-wta" onclick="switchOddsTour('wta')"
          style="padding:6px 16px;border-radius:100px;border:2px solid #ddd8cc;background:#fff;color:#4b006e;font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;">
          Women's
        </button>
      </div>
    </div>
    <div id="odds-body" style="padding:16px 0 4px;">
      <div style="text-align:center;color:#aaa;font-size:0.85rem;font-family:sans-serif;padding:20px;">Loading odds…</div>
    </div>
    <div style="padding:8px 20px 14px;font-size:0.7rem;font-family:sans-serif;color:#aaa;text-align:right;">
      Odds via DraftKings · must be 21+ · gambling problem? call 1-800-522-4700
    </div>
  </div>

  <script>
  (function(){
    var _oddsTour = 'atp';
    var _oddsData = null;

    window.switchOddsTour = function(tour) {
      _oddsTour = tour;
      document.getElementById('odds-btn-atp').style.cssText =
        'padding:6px 16px;border-radius:100px;border:2px solid ' + (tour==='atp'?'#00512e':'#ddd8cc') +
        ';background:' + (tour==='atp'?'#00512e':'#fff') +
        ';color:' + (tour==='atp'?'#fff':'#00512e') +
        ';font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;';
      document.getElementById('odds-btn-wta').style.cssText =
        'padding:6px 16px;border-radius:100px;border:2px solid ' + (tour==='wta'?'#4b006e':'#ddd8cc') +
        ';background:' + (tour==='wta'?'#4b006e':'#fff') +
        ';color:' + (tour==='wta'?'#fff':'#4b006e') +
        ';font-size:0.78rem;font-weight:700;cursor:pointer;font-family:sans-serif;letter-spacing:0.5px;';
      if (_oddsData) renderOdds(_oddsData);
    };

    function renderOdds(data) {
      var el = document.getElementById('odds-body');
      var list = (data[_oddsTour] || []);

      if (data.error === 'no_key') {
        el.innerHTML = '<div style="padding:20px 24px;font-family:sans-serif;font-size:0.82rem;color:#555;line-height:1.6;">'
          + '<strong style="color:#00512e;">Set up live odds in 2 steps:</strong><br>'
          + '1. Get a free API key at <strong>the-odds-api.com</strong> (500 free requests/month)<br>'
          + '2. Add <code style="background:#f0f0f0;padding:1px 5px;border-radius:3px;">ODDS_API_KEY=your_key</code> as an environment variable on Render'
          + '</div>';
        return;
      }
      if (data.error && !list.length) {
        el.innerHTML = '<div style="text-align:center;color:#aaa;font-size:0.82rem;font-family:sans-serif;padding:20px 16px;">'
          + 'Odds unavailable — ' + data.error + '</div>';
        return;
      }
      if (!list.length) {
        el.innerHTML = '<div style="text-align:center;color:#aaa;font-size:0.82rem;font-family:sans-serif;padding:20px;">No ' + (_oddsTour==='atp'?"Men's":"Women's") + ' odds available yet.</div>';
        return;
      }

      var rows = list.map(function(item, i) {
        var odds = item[0], name = item[1];
        var pos = odds && odds[0] === '+';
        var fav = odds && odds[0] === '-';
        var oddsColor = pos ? '#00512e' : fav ? '#c0392b' : '#333';
        var oddsBg    = pos ? 'rgba(0,81,46,0.07)' : fav ? 'rgba(192,57,43,0.07)' : '#f9f7f4';
        return '<div style="display:flex;align-items:center;padding:9px 20px;border-bottom:1px solid #f0ece0;gap:12px;">'
          + '<div style="width:22px;text-align:center;font-size:0.75rem;font-weight:700;color:#aaa;font-family:sans-serif;flex-shrink:0;">' + (i+1) + '</div>'
          + '<div style="flex:1;font-size:0.88rem;font-family:\'EB Garamond\',Georgia,serif;color:#1a1a1a;">' + name + '</div>'
          + '<div style="font-size:0.9rem;font-weight:700;font-family:sans-serif;color:' + oddsColor + ';background:' + oddsBg + ';padding:3px 10px;border-radius:100px;letter-spacing:0.3px;flex-shrink:0;">' + odds + '</div>'
          + '</div>';
      }).join('');

      el.innerHTML = rows;
    }

    function loadOdds() {
      fetch('/api/odds')
        .then(function(r){ return r.json(); })
        .then(function(data){
          _oddsData = data;
          renderOdds(data);
        })
        .catch(function(){
          document.getElementById('odds-body').innerHTML =
            '<div style="text-align:center;color:#aaa;font-size:0.82rem;font-family:sans-serif;padding:20px;">Could not reach DraftKings.</div>';
        });
    }

    loadOdds();
    setInterval(loadOdds, 5 * 60 * 1000);
  })();
  </script>

  <!-- SCORING RULES -->
  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-title">🏆 Scoring Rules</div>
        <div class="card-sub">Points per correct pick · served.bracket.tennis · The Championships 2026</div>
      </div>
    </div>
    <div class="rules-grid">
      <div class="rule-item"><div class="rule-round">Round 1</div><div class="rule-pts">10</div><div class="rule-note">64 matches</div></div>
      <div class="rule-item"><div class="rule-round">Round 2</div><div class="rule-pts">20</div><div class="rule-note">32 matches</div></div>
      <div class="rule-item"><div class="rule-round">Round 3</div><div class="rule-pts">30</div><div class="rule-note">16 matches</div></div>
      <div class="rule-item"><div class="rule-round">Round 4</div><div class="rule-pts">40</div><div class="rule-note">8 matches</div></div>
      <div class="rule-item"><div class="rule-round">Quarters</div><div class="rule-pts">60</div><div class="rule-note">4 matches</div></div>
      <div class="rule-item"><div class="rule-round">Semis</div><div class="rule-pts">80</div><div class="rule-note">2 matches</div></div>
      <div class="rule-item"><div class="rule-round">Final</div><div class="rule-pts">100</div><div class="rule-note">1 match</div></div>
    </div>
    <div class="rules-bonuses">
      <div class="bonus-tag">🎾 Points apply to both Men's &amp; Women's draws</div>
      <div class="bonus-tag">🏆 Unseeded upset: correct pick = double points</div>
      <div class="bonus-tag">📊 Seed gap bonus: +1 pt per seed difference on correct upset pick</div>
      <div class="bonus-tag">🔢 Tiebreaker: closest guess to total games in men's final</div>
    </div>
  </div>

  <div class="footer" id="footer"></div>
</div>

<script>
const COLORS = __COLORS_JSON__;
const SLUG   = '__SLUG__';
let allData = null;
let members = [];

// ── MEMBER STORAGE ────────────────────────────────────────────────────────────
function loadMembers() {
  // Check ?m= query param first — survives iMessage/SMS link sharing unlike #hash
  const params = new URLSearchParams(location.search);
  const fromParam = params.get('m');
  if (fromParam) {
    const fromUrl = fromParam.split(',').map(s => s.trim()).filter(Boolean);
    if (fromUrl.length > 0) {
      localStorage.setItem('wim_members', JSON.stringify(fromUrl));
      return fromUrl;
    }
  }
  // Fall back to localStorage (returning visitor)
  try { return JSON.parse(localStorage.getItem('wim_members') || '[]'); }
  catch(e) { return []; }
}

function saveMembers() {
  localStorage.setItem('wim_members', JSON.stringify(members));
  const param = members.map(encodeURIComponent).join(',');
  const newUrl = location.origin + location.pathname + '?m=' + param;
  history.replaceState(null, '', newUrl);
}

// ── DATA FETCH ────────────────────────────────────────────────────────────────
async function loadData() {
  if (members.length === 0) {
    showEmpty();
    return;
  }
  document.getElementById('status-text').textContent = 'Fetching scores…';
  try {
    const params = encodeURIComponent(members.join(','));
    window._currentMembers = members;
    const res = await fetch('/api/data?members=' + params);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    allData = await res.json();
    render();
    if (window._populatePickDropdown) window._populatePickDropdown(members);
    document.getElementById('footer').innerHTML = '🍈 &nbsp;US Open 2026 · Flushing Meadows · New York · Scores from served.bracket.tennis · Updated: ' + allData.updated + '<br><span style="font-size:0.72rem;color:#bbb;letter-spacing:0.04em;">Designed by Will</span>';
  } catch(e) {
    document.getElementById('status-text').textContent = 'Error loading data — ' + e.message;
  }
}

// ── RENDER ────────────────────────────────────────────────────────────────────
function render() {
  if (!allData) return;
  const players = allData.players;

  const sorted = [...players].sort((a, b) => (b.combined ?? -1) - (a.combined ?? -1));
  const maxScore = sorted.reduce((m, p) => Math.max(m, p.combined ?? 0), 1);
  const tbody = document.getElementById('lb-body');

  tbody.innerHTML = sorted.map((p, i) => {
    const rank  = i + 1;
    const c     = COLORS[String(i % 2)] || COLORS['0'];
    const pct   = p.combined != null ? Math.round((p.combined / maxScore) * 100) : 0;
    const bracketUrl = `https://served.bracket.tennis/tournaments/${SLUG}/combined/brackets/${encodeURIComponent(p.username)}`;
    const atpPill  = p.atp  != null ? `<span class="score-pill pill-atp">${p.atp.toLocaleString()}</span>`  : `<span class="score-pill pill-none">–</span>`;
    const wtaPill  = p.wta  != null ? `<span class="score-pill pill-wta">${p.wta.toLocaleString()}</span>`  : `<span class="score-pill pill-none">–</span>`;
    const combPill = p.combined != null ? `<span class="score-pill pill-combined">${p.combined.toLocaleString()}</span>` : `<span class="score-pill pill-none">–</span>`;
    const maxPill  = p.max_combined != null
      ? `<span style="font-size:0.78rem;color:#7d5a00;font-family:sans-serif;font-weight:600;">▲ ${p.max_combined.toLocaleString()}</span>`
      : `<span class="score-pill pill-none">–</span>`;
    const globalPill = p.global_rank != null
      ? `<span style="font-size:0.78rem;color:#4b006e;font-family:sans-serif;font-weight:700;">#${p.global_rank.toLocaleString()}</span>`
      : `<span class="score-pill pill-none">–</span>`;
    return `<tr>
      <td class="rank-cell ${rank<=3?'gold':''}">${rank<=3?['🥇','🥈','🥉'][rank-1]:rank}</td>
      <td style="overflow:hidden;">
        <div class="player-name" style="white-space:nowrap;"><a class="name-link" href="${bracketUrl}" target="_blank" rel="noopener" style="color:${c.primary}">${esc(p.username)}</a></div>
        <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%;background:${c.primary}"></div></div>
      </td>
      <td style="text-align:center;">${combPill}</td><td style="text-align:center;">${atpPill}</td><td style="text-align:center;">${wtaPill}</td><td style="text-align:center;">${maxPill}</td><td style="text-align:center;">${globalPill}</td>
    </tr>`;
  }).join('');

  document.getElementById('status-text').textContent = `Live · last updated ${allData.updated}`;
}

// ── EMPTY STATE ───────────────────────────────────────────────────────────────
function showEmpty() {
  document.getElementById('lb-body').innerHTML = `<tr><td colspan="6" style="padding:48px;text-align:center;font-family:sans-serif;color:#aaa;">
    <div style="font-size:2rem;margin-bottom:10px">👥</div>
    <div style="font-size:1rem;color:#006b3c;font-weight:600;margin-bottom:6px">Set up your group</div>
    <div style="font-size:0.85rem;margin-bottom:16px">Click <strong>⚙ Group</strong> in the header to add your served.bracket.tennis usernames.</div>
  </td></tr>`;
  document.getElementById('status-text').textContent = 'No group members added yet';
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function openModal() {
  renderMembersList();
  document.getElementById('modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('username-input').focus(), 100);
}
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }
function closeModalOutside(e) { if (e.target === document.getElementById('modal-overlay')) closeModal(); }

function addMember() {
  const input = document.getElementById('username-input');
  const val = input.value.trim();
  if (!val) return;
  if (!members.find(m => m.toLowerCase() === val.toLowerCase())) members.push(val);
  input.value = '';
  renderMembersList();
}

function removeMember(idx) { members.splice(idx, 1); renderMembersList(); }

function renderMembersList() {
  const ul = document.getElementById('members-list');
  ul.innerHTML = '';
  document.getElementById('member-count').textContent = members.length;
  members.forEach((m, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<span>${esc(m)}</span><button class="remove-btn" onclick="removeMember(${i})">✕</button>`;
    ul.appendChild(li);
  });
}

function saveAndClose() {
  saveMembers();
  closeModal();
  loadData();
}

async function copyInviteLink() {
  saveMembers();
  const link = location.origin + location.pathname + '?m=' + members.map(encodeURIComponent).join(',');
  try {
    await navigator.clipboard.writeText(link);
    const btn = document.getElementById('invite-btn');
    btn.textContent = '✓ Copied!';
    setTimeout(() => btn.textContent = '📋 Copy Invite Link', 2000);
  } catch(e) { prompt('Copy this link:', link); }
}

// ── UTILS ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── INIT ──────────────────────────────────────────────────────────────────────
members = loadMembers();
renderMembersList();
loadData();
setInterval(loadData, 5 * 60 * 1000);
</script>
</body>
</html>"""


# ── HTML template injection ────────────────────────────────────────────────────

def build_html():
    colors_for_js = {str(k): v for k, v in COLORS.items()}
    html = HTML.replace('__COLORS_JSON__', json.dumps(colors_for_js))
    html = html.replace('__SLUG__', TOURNAMENT_SLUG)
    return html


# ── Scoring engine — served.bracket.tennis turbo-stream decoder ──────────────

ROUND_POINTS = {1: 10, 2: 20, 3: 30, 4: 40, 5: 60, 6: 80, 7: 100}


def _fetch_bracket_html(username, tour):
    url = f'https://served.bracket.tennis/tournaments/{TOURNAMENT_SLUG}/{tour}/brackets/{username}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html',
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')


def _parse_flat_array(html):
    """Extract and parse the React Router turbo-stream flat array from the page script."""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    big = max(scripts, key=len) if scripts else ''
    m = re.search(r'streamController\.enqueue\("(.*?)"\)', big, re.S)
    if not m:
        return None
    encoded = m.group(1)
    # Decode the JavaScript string: \\ → \, \" → "  then strip stray literal newlines
    arr_str = (encoded
               .replace('\\\\', '\x00BS\x00')
               .replace('\\"', '"')               .replace('\x00BS\x00', '\\')               .replace('\n', '')               .replace('\r', ''))
    if arr_str.endswith('\\n'):
        arr_str = arr_str[:-2]
    try:
        return json.loads(arr_str)
    except Exception:
        return None


def _ts_val(flat, ref):
    """Resolve a turbo-stream integer reference to its value."""
    if not isinstance(ref, int) or ref < 0 or ref >= len(flat):
        return None
    item = flat[ref]
    if isinstance(item, dict):
        return _ts_obj(flat, item)
    return item


def _ts_obj(flat, obj):
    """Decode a turbo-stream object {"_N":M, ...} into a plain Python dict."""
    result = {}
    for k, v in obj.items():
        key_idx = int(k[1:])
        key = flat[key_idx] if 0 <= key_idx < len(flat) else None
        val = _ts_val(flat, v) if isinstance(v, int) else v
        if key is not None:
            result[key] = val
    return result


def _parse_match_scores(scores_str, p1_name, p2_name, winner_name, is_live):
    """
    Parse served.bracket.tennis scores string into a display string.
    Format: '[[p1_g, p1_tb, p1_g2, p1_tb2, ...], [p2_g, p2_tb, ...]]'
    Each pair is (games_won, tiebreak_score) per set.
    Returns e.g. '6-3  6-4  7-6(3)' or '*4-6  6-3  *6-6' when live.
    """
    if not scores_str:
        return None
    try:
        arr = json.loads(scores_str)
        if not isinstance(arr, list) or len(arr) < 2:
            return None
        p1_arr, p2_arr = arr[0], arr[1]
        n = min(len(p1_arr), len(p2_arr)) // 2
        if n == 0:
            return None

        # Show from winner's perspective; if no winner yet show from p1's view
        flip = (winner_name and winner_name == p2_name)

        parts = []
        for i in range(n):
            idx  = i * 2
            g1   = p1_arr[idx];   tb1 = p1_arr[idx+1] if idx+1 < len(p1_arr) else None
            g2   = p2_arr[idx];   tb2 = p2_arr[idx+1] if idx+1 < len(p2_arr) else None
            if g1 is None or g2 is None:
                continue
            if g1 == 0 and g2 == 0:
                continue  # skip empty/abandoned set entries
            wg, lg, wtb, ltb = (g2, g1, tb2, tb1) if flip else (g1, g2, tb1, tb2)

            last_set = (i == n - 1)
            if is_live and last_set:
                # In-progress set: just show games, no tiebreak detail
                parts.append(f'*{wg}-{lg}')
            elif ltb is not None:
                parts.append(f'{wg}-{lg}({int(ltb)})')
            else:
                parts.append(f'{wg}-{lg}')

        return '  '.join(parts) if parts else None
    except Exception:
        return None


def _extract_bracket_data(flat):
    """
    Decode the flat turbo-stream array to produce:
      r1_draw:       {slot(1-128): (player_name, ranking)}
      match_results: {(round, pos): {winner, wr, lr}}

    R1 match at position k maps to draw slots 2k-1 (top) and 2k (bottom).
    Seeding proxy: ATP/WTA ranking (top 32 are seeded at the US Open).
    """
    matches_refs = None
    for i, item in enumerate(flat):
        if (item == 'matches'
                and i + 1 < len(flat)
                and isinstance(flat[i + 1], list)
                and len(flat[i + 1]) > 50):
            matches_refs = flat[i + 1]
            break
    if not matches_refs:
        return {}, {}, []

    r1_draw = {}
    match_results = {}
    all_matches = []

    for ref in matches_refs:
        raw = flat[ref]
        if not isinstance(raw, dict):
            continue
        m = _ts_obj(flat, raw)
        rnd = m.get('roundNumber')
        pos = m.get('position')
        if not rnd or not pos:
            continue

        p1 = m.get('player1') or {}
        p2 = m.get('player2') or {}
        winner = m.get('winner') or {}

        if rnd == 1:
            s1 = (pos - 1) * 2 + 1
            s2 = (pos - 1) * 2 + 2
            if p1.get('name'):
                r1_draw[s1] = (p1['name'], p1.get('ranking') or 999)
            if p2.get('name'):
                r1_draw[s2] = (p2['name'], p2.get('ranking') or 999)

        if winner.get('name'):
            wname = winner['name']
            lname = p2.get('name') if p1.get('name') == wname else p1.get('name')
            r1 = p1.get('ranking') or 999
            r2 = p2.get('ranking') or 999
            wr = r1 if p1.get('name') == wname else r2
            lr = r2 if p1.get('name') == wname else r1
            match_results[(rnd, pos)] = {'winner': wname, 'loser': lname, 'wr': wr, 'lr': lr}

        def _ctry(pobj):
            c = pobj.get('country')
            if isinstance(c, dict):
                return (c.get('code') or c.get('abbreviation') or '').upper()
            return (c or '').upper()

        p1_name     = p1.get('name') or None
        p2_name     = p2.get('name') or None
        winner_name = winner.get('name') or None
        has_started = bool(m.get('has_started'))
        is_live     = has_started and not winner_name and (p1_name or p2_name)

        # scores field: '[[p1_g,p1_tb,p1_g2,p1_tb2,...],[p2_g,p2_tb,...]]'
        score = _parse_match_scores(
            m.get('scores'), p1_name, p2_name, winner_name, bool(is_live)
        )

        all_matches.append({
            'round': rnd,
            'pos': pos,
            'p1': p1_name,
            'p2': p2_name,
            'p1_rank': p1.get('ranking') or 999,
            'p2_rank': p2.get('ranking') or 999,
            'p1_country': _ctry(p1),
            'p2_country': _ctry(p2),
            'winner': winner_name,
            'score': score,
            'is_live': bool(is_live),
        })

    return r1_draw, match_results, all_matches


def _extract_picks(html):
    """
    Extract user picks from bracket page HTML via the turbo-stream flat array.
    The flat array contains 'picks' followed immediately by the picks JSON string.
    Returns {(round, match_pos): draw_slot} or {}.
    """
    flat = _parse_flat_array(html)
    if flat:
        for i, item in enumerate(flat):
            if item == 'picks' and i + 1 < len(flat):
                raw = flat[i + 1]
                if isinstance(raw, str) and raw.startswith('{'):
                    try:
                        data = json.loads(raw)
                        picks = {}
                        for key, val in data.items():
                            if ':' in str(key):
                                parts = key.split(':')
                                try:
                                    picks[(int(parts[0]), int(parts[1]))] = int(val)
                                except (ValueError, TypeError):
                                    pass
                        if picks:
                            return picks
                    except Exception:
                        pass
    return {}


def _calculate_score(picks, r1_draw, match_results):
    """
    Calculate a user's total bracket score.

    picks:         {(round, match_pos): draw_slot}
    r1_draw:       {draw_slot: (player_name, ranking)}
    match_results: {(round, match_pos): {winner, wr, lr}}

    Points per correct pick:
      base:           ROUND_POINTS[round]
      unseeded upset: x2  (winner_rank > 32, loser_rank <= 32)
      seeded upset:   +gap  (both seeded, winner_rank > loser_rank)
    """
    total = 0
    for (rnd, mpos), slot in picks.items():
        if not (1 <= rnd <= 7):
            continue
        result = match_results.get((rnd, mpos))
        if not result:
            continue
        if slot not in r1_draw:
            continue
        player_name, _ = r1_draw[slot]
        if result['winner'] != player_name:
            continue

        base = ROUND_POINTS[rnd]
        wr, lr = result['wr'], result['lr']
        winner_seeded = wr <= 32
        loser_seeded  = lr <= 32

        if not winner_seeded and loser_seeded:
            pts = base * 2
        elif winner_seeded and loser_seeded and wr > lr:
            pts = base + (wr - lr)
        else:
            pts = base

        total += pts
    return total


def _calculate_max_score(picks, r1_draw, match_results):
    """Max possible score = current correct picks + base points for future picks
    where the picked player hasn't been eliminated yet."""
    current = _calculate_score(picks, r1_draw, match_results)
    eliminated = {r['loser'] for r in match_results.values() if r.get('loser')}
    future = 0
    for (rnd, mpos), slot in picks.items():
        if not (1 <= rnd <= 7):
            continue
        if match_results.get((rnd, mpos)):
            continue  # completed match already in current score
        if slot not in r1_draw:
            continue
        player_name, _ = r1_draw[slot]
        if player_name not in eliminated:
            future += ROUND_POINTS[rnd]
    return current + future


# ── ESPN live-match overlay ───────────────────────────────────────────────────

_espn_live_cache    = {}   # tour -> {'live': set_of_names, 'scores': {name: score_str}}
_espn_live_cache_ts = {}

def _espn_parse_events(data, live, scores):
    """
    Parse ESPN scoreboard JSON, populating:
      live   — set of full names currently playing
      scores — {full_name: score_str, last_name: score_str} for completed/live matches
    """
    for event in data.get('events', []):
        for comp in event.get('competitions', []):
            stype     = (comp.get('status') or {}).get('type') or {}
            state     = stype.get('name', '')
            completed = stype.get('completed', False)

            competitors = comp.get('competitors', [])

            # Collect names + per-player linescores
            players = []
            for c in competitors:
                name = (c.get('athlete') or {}).get('fullName', '') or \
                       (c.get('athlete') or {}).get('displayName', '')
                ls   = c.get('linescores') or []
                players.append({'name': name, 'ls': ls})

            names = [p['name'] for p in players if p['name']]

            if state == 'STATUS_IN_PROGRESS' and not completed:
                for name in names:
                    live.add(name)

            # --- Build set-score string ---
            score_str = None

            # Format 1: competition-level linescores with displayValue ("6-3")
            comp_ls = comp.get('linescores') or []
            if comp_ls:
                parts = [s.get('displayValue', '') for s in comp_ls if s.get('displayValue')]
                if parts:
                    score_str = '  '.join(parts)

            # Format 2: per-competitor linescores (zip games per set)
            if not score_str and len(players) == 2:
                ls0 = [l.get('value') for l in players[0]['ls'] if l.get('value') is not None]
                ls1 = [l.get('value') for l in players[1]['ls'] if l.get('value') is not None]
                if ls0 and ls1 and len(ls0) == len(ls1):
                    score_str = '  '.join(f'{int(a)}-{int(b)}' for a, b in zip(ls0, ls1))

            if score_str and names:
                for name in names:
                    scores[name] = score_str
                    last = name.strip().split()[-1] if name.strip() else ''
                    if last:
                        scores[last] = score_str


def _fetch_espn_live(tour):
    """
    Returns {'live': {player_name, ...}, 'scores': {name: score_str}}
    Fetches today + past 5 days so recently-completed match scores are included.
    Cached 45 seconds.
    """
    now = time.time()
    if tour in _espn_live_cache and now - _espn_live_cache_ts.get(tour, 0) < 45:
        return _espn_live_cache[tour]

    slug  = 'atp' if tour == 'atp' else 'wta'
    live  = set()
    scores = {}

    today = datetime.now()
    for delta in range(6):  # today + 5 previous days
        date_str = (today - timedelta(days=delta)).strftime('%Y%m%d')
        # Try multiple ESPN endpoints — Grand Slams may not appear under atp/wta slug
        endpoints = [
            f'https://site.api.espn.com/apis/site/v2/sports/tennis/{slug}/scoreboard?dates={date_str}',
            f'https://site.api.espn.com/apis/site/v2/sports/tennis/scoreboard?dates={date_str}',
        ]
        for url in endpoints:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read().decode())
                _espn_parse_events(data, live, scores)
            except Exception:
                continue

    result = {'live': live, 'scores': scores}
    _espn_live_cache[tour]    = result
    _espn_live_cache_ts[tour] = now
    return result


_espn_today_cache    = {}   # tour -> list[match_dict]
_espn_today_cache_ts = {}
_usopen_sched_cache    = {}  # tour -> {frozenset({last1,last2}): time_str}
_usopen_sched_cache_ts = {}


def _fetch_usopen_schedule(tour):
    """
    Fetch today's US Open schedule from usopen.org feeds.
    Returns dict keyed by frozenset of player last names → scheduled time string.
    Also keyed by frozenset of full names for broader matching.
    """
    now = time.time()
    if tour in _usopen_sched_cache and now - _usopen_sched_cache_ts.get(tour, 0) < 120:
        return _usopen_sched_cache[tour]

    result = {}
    try:
        event_code = 'MS' if tour == 'atp' else 'WS'
        days_url = 'https://www.usopen.org/en_US/scores/feeds/2026/schedule/scheduleDays.json'
        req = urllib.request.Request(days_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            days_data = json.loads(r.read().decode())

        feed_url = None
        for day in days_data.get('eventDays', []):
            if day.get('currentDay'):
                feed_url = day.get('feedUrl')
                break

        if not feed_url:
            _usopen_sched_cache[tour] = result
            _usopen_sched_cache_ts[tour] = now
            return result

        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            sched = json.loads(r.read().decode())

        for court in sched.get('courts', []):
            court_time = court.get('time', '')
            for match in court.get('matches', []):
                if match.get('eventCode') != event_code:
                    continue
                t = match.get('notBefore') or court_time or 'TBD'
                if t and t != 'TBD' and 'ET' not in t:
                    t = t + ' ET'
                t1 = (match.get('team1') or [{}])[0]
                t2 = (match.get('team2') or [{}])[0]
                last1 = (t1.get('lastNameA') or '').strip()
                last2 = (t2.get('lastNameA') or '').strip()
                first1 = (t1.get('firstNameA') or '').strip()
                first2 = (t2.get('firstNameA') or '').strip()
                full1 = f'{first1} {last1}'.strip()
                full2 = f'{first2} {last2}'.strip()
                if last1 and last2:
                    key_last = frozenset([last1.lower(), last2.lower()])
                    key_full = frozenset([full1.lower(), full2.lower()])
                    result[key_last] = t
                    result[key_full] = t
    except Exception:
        pass

    _usopen_sched_cache[tour] = result
    _usopen_sched_cache_ts[tour] = now
    return result

def _fetch_espn_today_matches(tour):
    """
    Fetch today's US Open singles matches from ESPN API.
    Returns list of dicts: {p1, p2, p1_country, p2_country, winner, score, is_live,
                            scheduled_time, status}
    status: 'live' | 'final' | 'upcoming'
    Falls back to [] on any error (caller uses bracket data instead).
    """
    now = time.time()
    if tour in _espn_today_cache and now - _espn_today_cache_ts.get(tour, 0) < 45:
        return _espn_today_cache[tour]

    # Use ET date — server may be UTC, so a naive datetime.now() can be a day off after midnight ET
    today_str = _now_et().strftime('%Y%m%d')
    is_men = (tour == 'atp')
    slug = 'atp' if is_men else 'wta'
    endpoints = [
        f'https://site.api.espn.com/apis/site/v2/sports/tennis/usopen/scoreboard?dates={today_str}&limit=100',
        f'https://site.api.espn.com/apis/site/v2/sports/tennis/{slug}/scoreboard?dates={today_str}&limit=100',
        f'https://site.api.espn.com/apis/site/v2/sports/tennis/scoreboard?dates={today_str}&limit=100',
    ]

    seen_pairs = set()  # deduplicate across endpoints
    matches = []
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
            for event in data.get('events', []):
                name_lower = (event.get('name') or '').lower()
                # Skip doubles
                if 'double' in name_lower:
                    continue
                # Filter by tour using event name keywords
                # "Men's" → atp, "Women's" → wta; if neither keyword, include for both
                has_mens   = "men's" in name_lower and "women's" not in name_lower
                has_womens = "women's" in name_lower
                if has_mens and not is_men:
                    continue
                if has_womens and is_men:
                    continue
                for comp in event.get('competitions', []):
                    stype     = (comp.get('status') or {}).get('type') or {}
                    state     = stype.get('name', '')
                    completed = stype.get('completed', False)
                    detail    = stype.get('shortDetail') or stype.get('detail') or ''

                    competitors = comp.get('competitors', [])
                    if len(competitors) < 2:
                        continue

                    def _parse_competitor(c):
                        ath = c.get('athlete') or {}
                        name = ath.get('fullName') or ath.get('displayName') or ''
                        # 3-letter country code from multiple possible fields
                        ctry = ''
                        flag = ath.get('flag') or {}
                        if not ctry:
                            ctry = (ath.get('countryAbbreviation') or
                                    ath.get('shortCountryAbbreviation') or '')
                        if not ctry:
                            for f in [ath.get('country') or {}, flag]:
                                if isinstance(f, dict):
                                    ctry = (f.get('abbreviation') or f.get('code') or '')
                                    if ctry:
                                        break
                        winner_flag = c.get('winner', False)
                        return name, ctry.upper()[:3], winner_flag

                    p1_name, p1_ctry, p1_won = _parse_competitor(competitors[0])
                    p2_name, p2_ctry, p2_won = _parse_competitor(competitors[1])

                    # Score string from linescores
                    score_str = None
                    comp_ls = comp.get('linescores') or []
                    if comp_ls:
                        parts = [s.get('displayValue', '') for s in comp_ls if s.get('displayValue')]
                        if parts:
                            score_str = ' '.join(parts)
                    if not score_str and len(competitors) == 2:
                        ls0 = [l.get('value') for l in (competitors[0].get('linescores') or []) if l.get('value') is not None]
                        ls1 = [l.get('value') for l in (competitors[1].get('linescores') or []) if l.get('value') is not None]
                        if ls0 and ls1 and len(ls0) == len(ls1):
                            score_str = ' '.join(f'{int(a)}-{int(b)}' for a, b in zip(ls0, ls1))

                    if state == 'STATUS_IN_PROGRESS' and not completed:
                        status = 'live'
                    elif completed or state == 'STATUS_FINAL':
                        status = 'final'
                    else:
                        status = 'upcoming'

                    winner_name = ''
                    if status == 'final':
                        if p1_won:
                            winner_name = p1_name
                        elif p2_won:
                            winner_name = p2_name

                    # For upcoming matches: verify the match is actually scheduled for TODAY ET.
                    # ESPN sometimes returns multi-day lookahead; filter those out.
                    scheduled_time = ''
                    if status == 'upcoming':
                        iso = comp.get('date') or event.get('date') or ''
                        skip_match = False
                        if iso:
                            try:
                                from datetime import timezone
                                dt_utc = datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
                                try:
                                    from zoneinfo import ZoneInfo as _ZI2
                                    dt_et = dt_utc.astimezone(_ZI2('America/New_York'))
                                except Exception:
                                    dt_et = dt_utc - timedelta(hours=4)
                                # Skip if not today ET
                                if dt_et.strftime('%Y%m%d') != today_str:
                                    skip_match = True
                                else:
                                    # Only show time if it's not midnight (date-only placeholder)
                                    if dt_et.hour != 0 or dt_et.minute != 0:
                                        hr = dt_et.hour % 12 or 12
                                        ampm = 'AM' if dt_et.hour < 12 else 'PM'
                                        scheduled_time = f'{hr}:{dt_et.minute:02d} {ampm} ET'
                            except Exception:
                                pass  # can't parse date — include match with no time
                        if skip_match:
                            continue
                        if not scheduled_time:
                            # Try ESPN status text fields for a readable time
                            comp_status = comp.get('status') or {}
                            for candidate in [
                                detail,
                                stype.get('displayClock', ''),
                                comp_status.get('displayClock', ''),
                                (comp_status.get('type') or {}).get('altDetail', ''),
                            ]:
                                if candidate and any(ch.isdigit() for ch in candidate):
                                    scheduled_time = candidate
                                    break
                        if not scheduled_time:
                            scheduled_time = 'TBD'

                    pair = tuple(sorted([p1_name or '', p2_name or '']))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    matches.append({
                        'p1': p1_name,
                        'p2': p2_name,
                        'p1_country': p1_ctry,
                        'p2_country': p2_ctry,
                        'winner': winner_name,
                        'score': score_str or '',
                        'is_live': status == 'live',
                        'scheduled_time': scheduled_time,
                        'status': status,
                    })
        except Exception:
            continue

    _espn_today_cache[tour]    = matches
    _espn_today_cache_ts[tour] = now
    return matches


# ── US Open daily schedule (all times already ET) ───────────────────────────
_WIMBLEDON_SCHEDULE = """
US Open 2026 daily schedule (all times Eastern / ET — the tournament is in New York):
- Outside courts (Courts 4–17): play begins at 11:00 AM ET
- Arthur Ashe Stadium: day session first match at 12:00 PM ET; evening session at 7:00 PM ET
- Louis Armstrong Stadium: day session first match at 12:00 PM ET; evening session at 7:00 PM ET
- Grandstand: day session first match at 11:00 AM ET

High-profile matches (top seeds, QF/SF/Final) are on Arthur Ashe or Louis Armstrong starting at 12:00 PM ET day session or 7:00 PM ET evening session.
Outside-court matches for lower seeds typically begin at 11:00 AM ET.
All times are already ET — no conversion needed.
"""

# ── US Open odds (sourced 2026-09-04) ────────────────────────────────────────
# Update these manually when odds change

_STATIC_ODDS = {
    'atp': [
        ('-165',  'Carlos Alcaraz'),
        ('+330',  'Alexander Zverev'),
        ('+1300', 'Ben Shelton'),
        ('+2200', 'Frances Tiafoe'),
        ('+2200', 'Daniil Medvedev'),
        ('+2800', 'Learner Tien'),
        ('+5000', 'Alex Michelsen'),
        ('+6000', 'Alexander Blockx'),
        ('+7000', 'Francisco Cerundolo'),
        ('+7000', 'Karen Khachanov'),
        ('+8000', 'Stefanos Tsitsipas'),
        ('+15000','Botic Van De Zandschulp'),
        ('+15000','Arthur Gea'),
        ('+15000','Luciano Darderi'),
    ],
    'wta': [
        ('+220',  'Aryna Sabalenka'),
        ('+450',  'Coco Gauff'),
        ('+550',  'Iga Swiatek'),
        ('+850',  'Jessica Pegula'),
        ('+900',  'Mirra Andreeva'),
        ('+1100', 'Elena Rybakina'),
        ('+1500', 'Linda Noskova'),
        ('+1800', 'Naomi Osaka'),
        ('+3000', 'Iva Jovic'),
        ('+5000', 'Qinwen Zheng'),
        ('+6000', 'Sorana Cirstea'),
        ('+6000', 'Anastasia Potapova'),
        ('+8000', 'Emma Navarro'),
        ('+10000','Anna Kalinskaya'),
    ],
}


# ── AI daily summary ─────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ODDS_UPDATE_TOKEN = os.environ.get('ODDS_UPDATE_TOKEN', '')

# Live odds override — populated by /api/update-odds, falls back to _STATIC_ODDS
_live_odds = {}
_live_odds_updated = ''

_summary_cache    = {}
_summary_cache_ts = 0


def _fetch_news_text(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode('utf-8', errors='replace')
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:3000]
    except Exception:
        return ''


def _fetch_usopen_news():
    """Try multiple sources for US Open headlines."""
    for url in [
        'https://www.bbc.com/sport/tennis/us-open',
        'https://www.bbc.co.uk/sport/tennis',
        'https://www.espn.com/tennis/',
    ]:
        text = _fetch_news_text(url)
        if text:
            return text
    return ''


def _fetch_today_espn_scores():
    """Fetch today's completed US Open match results from ESPN groupings structure."""
    lines = []
    today_et   = _now_et()
    today_date = today_et.strftime('%Y-%m-%d')
    today_str  = today_et.strftime('%Y%m%d')
    seen = set()

    for slug in ('atp', 'wta'):
        url = f'https://site.api.espn.com/apis/site/v2/sports/tennis/{slug}/scoreboard?dates={today_str}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
            for event in data.get('events', []):
                for grouping in event.get('groupings', []):
                    for comp in grouping.get('competitions', []):
                        # Filter to today's matches only
                        comp_date = comp.get('date', '')[:10]
                        if comp_date != today_date:
                            continue
                        if not comp.get('status', {}).get('type', {}).get('completed'):
                            continue
                        # Result is in notes[0].text e.g. "Sinner (ITA) bt Kecmanovic (SRB) 4-6 6-3..."
                        note = ''
                        for n in comp.get('notes', []):
                            if n.get('type') == 'event':
                                note = n.get('text', '')
                                break
                        if note and note not in seen:
                            seen.add(note)
                            lines.append(note)
        except Exception:
            continue
    return lines


def _build_results_text():
    """Build completed results and upcoming matches from bracket data, split by tour."""
    atp_done, wta_done = [], []
    atp_upcoming, wta_upcoming = [], []
    round_names = {1:'R1',2:'R2',3:'R3',4:'R4',5:'QF',6:'SF',7:'Final'}
    for tour, done_bucket, upcoming_bucket in [('atp', atp_done, atp_upcoming), ('wta', wta_done, wta_upcoming)]:
        try:
            _, results, all_matches = _get_tournament_data(tour, MEMBERS)
            score_lookup = {}
            for m in all_matches:
                if m.get('winner') and m.get('score'):
                    score_lookup[(m['round'], m['pos'])] = m['score']
            for (rnd, pos), r in sorted(results.items()):
                rname  = round_names.get(rnd, f'R{rnd}')
                winner = r.get('winner', '?')
                loser  = r.get('loser', '?')
                score  = score_lookup.get((rnd, pos), '')
                line   = f"{rname}: {winner} def. {loser}"
                if score:
                    line += f" ({score})"
                done_bucket.append(line)
            completed_keys = set(results.keys())
            for m in all_matches:
                key = (m['round'], m['pos'])
                if key in completed_keys:
                    continue
                if m.get('is_live'):
                    continue
                p1, p2 = m.get('p1'), m.get('p2')
                if p1 and p2:
                    rname = round_names.get(m['round'], f"R{m['round']}")
                    upcoming_bucket.append(f"{rname}: {p1} vs {p2}")
        except Exception:
            pass

    # Completed results: ESPN first (date-filtered), fall back to full bracket results
    today_lines = _fetch_today_espn_scores()
    if today_lines:
        today_section = "Today's completed matches:\n" + '\n'.join(today_lines[:20])
    else:
        bracket_lines = atp_done + wta_done
        if bracket_lines:
            today_section = "Completed matches so far this tournament:\n" + '\n'.join(bracket_lines[:30])
        else:
            today_section = "Completed matches: none confirmed yet"

    atp_ahead = "Men's upcoming (bracket):\n" + '\n'.join(atp_upcoming[:15]) if atp_upcoming else "Men's upcoming: none scheduled yet"
    wta_ahead = "Women's upcoming (bracket):\n" + '\n'.join(wta_upcoming[:15]) if wta_upcoming else "Women's upcoming: none scheduled yet"

    return today_section + '\n\n' + wta_ahead + '\n\n' + atp_ahead


def _fetch_ai_summary():
    """
    Call Claude Haiku to write a short US Open daily wrap.
    Cached 1 hour. Returns {'summary': str, 'updated': str, 'error': str|None}
    """
    global _summary_cache, _summary_cache_ts
    now = time.time()
    # Invalidate cache if it's from a previous calendar day (ET) or older than 30 min
    cache_date = datetime.fromtimestamp(_summary_cache_ts, tz=ZoneInfo('America/New_York')).strftime('%Y-%m-%d') if (_summary_cache_ts and ZoneInfo) else (datetime.utcfromtimestamp(_summary_cache_ts) - timedelta(hours=4)).strftime('%Y-%m-%d') if _summary_cache_ts else ''
    today_date = _now_et().strftime('%Y-%m-%d')
    if _summary_cache and now - _summary_cache_ts < 1800 and cache_date == today_date:
        return _summary_cache

    if not ANTHROPIC_API_KEY:
        result = {'summary': '', 'updated': '', 'error': 'no_key'}
        _summary_cache = result
        _summary_cache_ts = now
        return result

    results_text = _build_results_text()
    news_text    = _fetch_usopen_news()
    today        = _now_et().strftime('%B %d, %Y')

    now_et      = _now_et()
    hour_et     = now_et.hour
    today_date  = now_et.strftime('%B %d, %Y')
    tomorrow_et = now_et + timedelta(days=1)
    tomorrow_date = tomorrow_et.strftime('%B %d, %Y')

    if hour_et < 18:
        lookahead_label = "upcoming"
        day_context = (
            f"It is currently {now_et.strftime('%I:%M %p ET')} on {today_date}. "
            "For the looking-ahead sentences: pick the two most compelling upcoming matches from the data. "
            "If the news context explicitly confirms a match is today, say 'today' and include the ET time. "
            "If you are not certain, just say 'in their upcoming match' — never guess a day or time. "
            "Always write the looking-ahead sentences regardless — never refuse or ask for more info."
        )
    else:
        lookahead_label = "upcoming"
        day_context = (
            f"It is currently {now_et.strftime('%I:%M %p ET')} on {today_date} — past 6 PM ET so today's play is done. "
            "For the looking-ahead sentences: pick the two most compelling upcoming matches from the data. "
            "If the news context explicitly confirms a match is tomorrow, say 'tomorrow' and include the ET time. "
            "If you are not certain, just say 'in their upcoming match' — never guess a day or time. "
            "Never say 'tonight'. Always write the looking-ahead sentences regardless — never refuse or ask for more info."
        )

    prompt = (
        f"You are a tennis writer for a US Open bracket challenge group. Today is {today_date}, {now_et.strftime('%I:%M %p ET')} ET. "
        f"{day_context}\n\n"
        f"Write a punchy daily update for this group of friends watching the draw unfold. "
        f"Format it exactly like this — start immediately with WOMEN'S, no preamble:\n\n"
        f"WOMEN'S\n"
        f"<2-3 sharp sentences. If matches appear in 'Today's completed matches' data, recap the best story — score, what it means for the draw. "
        f"Then tease the most compelling upcoming match and why it matters.>\n\n"
        f"MEN'S\n"
        f"<Same structure.>\n\n"
        f"STRICT ACCURACY RULES — violating these is worse than a shorter update:\n"
        f"- ONLY state results (winners, losers, scores, round status) that appear WORD FOR WORD in the Tournament data below.\n"
        f"- Do NOT invent or infer scores, match details, or round completions from the news context. News may be outdated or wrong.\n"
        f"- Do NOT say a round is 'complete' or 'wrapped up' unless every match in that round appears in the completed data.\n"
        f"- If today's completed match data is thin or absent for a tour, skip the recap and go straight to upcoming matches.\n"
        f"- Never fabricate a match that isn't in the data. Never add set scores you don't see.\n"
        f"- Never say 'I don't have' or explain gaps — just skip to what you do know.\n\n"
        f"Voice rules:\n"
        f"- Write like a knowledgeable friend texting the group. Short punchy sentences.\n"
        f"- Mention seeds in brackets [3] when relevant.\n"
        f"- Call upsets upsets. Call dominant wins dominant.\n"
        f"- Times in ET only if explicitly in the data. Otherwise 'later today' or 'up next'.\n"
        f"- No asterisks, no Markdown bold, no bullet points. Plain text only.\n\n"
        f"Tournament data (source of truth — only use facts from here):\n{results_text}\n\n"
        f"News context (background flavor only — never cite specific results from here):\n{news_text[:2000]}"
    )

    try:
        payload = json.dumps({
            'model': 'claude-sonnet-4-5',
            'max_tokens': 600,
            'messages': [{'role': 'user', 'content': prompt}],
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        summary = data['content'][0]['text'].strip()
        result  = {'summary': summary, 'updated': _now_et().strftime('%b %d · %I:%M %p ET'), 'error': None}
    except Exception as e:
        result = {'summary': '', 'updated': '', 'error': str(e)}

    _summary_cache    = result
    _summary_cache_ts = now
    return result


def _fetch_dk_odds():
    # Use live odds pushed by scheduled agent if available
    if _live_odds.get('atp') or _live_odds.get('wta'):
        return {'atp': _live_odds.get('atp', []), 'wta': _live_odds.get('wta', []), 'error': None, 'updated': _live_odds_updated}
    # Fall back to hardcoded odds
    return {'atp': _STATIC_ODDS['atp'], 'wta': _STATIC_ODDS['wta'], 'error': None}


# ── Global leaderboard rank ───────────────────────────────────────────────────

_global_rank_cache    = {}
_global_rank_cache_ts = 0


def _fetch_global_ranks():
    """
    Scrape served.bracket.tennis global combined leaderboard.
    Returns {username_lower: rank} cached 10 minutes.
    """
    global _global_rank_cache, _global_rank_cache_ts
    now = time.time()
    if _global_rank_cache and now - _global_rank_cache_ts < 600:
        return _global_rank_cache
    try:
        url = f'https://served.bracket.tennis/tournaments/{TOURNAMENT_SLUG}/leaderboard'
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html',
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='replace')
        flat = _parse_flat_array(html)
        ranks = {}
        if flat:
            # Find leaderboard entries: look for username strings near rank numbers
            for i, item in enumerate(flat):
                if isinstance(item, str) and item == 'rank':
                    # Look nearby for username and rank value
                    pass
            # Fallback: regex scrape usernames in order from HTML
            entries = re.findall(r'/tournaments/[^/]+/combined/brackets/([^"\'<>\s/]+)', html)
            seen = []
            for e in entries:
                if e not in seen:
                    seen.append(e)
            for idx, username in enumerate(seen):
                ranks[username.lower()] = idx + 1
        _global_rank_cache = ranks
        _global_rank_cache_ts = now
    except Exception:
        pass
    return _global_rank_cache


# ── Group score scraper — pulls exact scores from served.bracket.tennis ───────

_group_scores_cache    = {}   # cache_key -> {username: scores}
_group_scores_cache_ts = {}   # cache_key -> timestamp


def _fetch_tour_score(username, tour):
    """
    Fetch a user's ATP or WTA bracket page and return their score as an int,
    or None on failure.

    The score lives in the turbo-stream flat array as:
      ..., 'score', <int>, 'lastHash', ...
    Served sometimes omits the integer on a cached render, so retry up to 3×.
    """
    url = f'https://served.bracket.tennis/tournaments/{TOURNAMENT_SLUG}/{tour}/brackets/{username}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html',
        'Cache-Control': 'no-cache',
    }
    saw_score_field = False
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode('utf-8', errors='replace')
            flat = _parse_flat_array(html)
            if not flat:
                continue
            for i, item in enumerate(flat):
                if item == 'score' and i + 1 < len(flat):
                    nxt = flat[i + 1]
                    # Inline score: ['score', <int>, 'lastHash', ...]
                    if isinstance(nxt, int) and nxt >= 0 and i + 2 < len(flat) and flat[i + 2] == 'lastHash':
                        return nxt
                    # Referenced score: score value stored elsewhere via userPrediction dict
                    # Dict key '_<i>' points to flat[ref] which holds the actual int
                    if nxt == 'lastHash':
                        saw_score_field = True
                        ref_key = f'_{i}'
                        for el in flat:
                            if isinstance(el, dict) and ref_key in el:
                                ref = el[ref_key]
                                if isinstance(ref, int) and 0 <= ref < len(flat):
                                    val = flat[ref]
                                    if isinstance(val, int) and val >= 0:
                                        return val
                        break
        except Exception:
            pass
    # After all retries: score field present but always empty → genuine 0
    return 0 if saw_score_field else None


def _scrape_group_scores(members=None):
    """
    Fetch each member's ATP and WTA bracket pages from served.bracket.tennis,
    extract the rendered score ("NNN pts"), and return:
      {username_lower: {'atp': int|None, 'wta': int|None, 'combined': int|None}}
    Cached 5 minutes per unique member list.
    """
    global _group_scores_cache, _group_scores_cache_ts
    if members is None:
        members = MEMBERS
    now = time.time()
    cache_key = ','.join(sorted(m.lower() for m in members))
    cached = _group_scores_cache.get(cache_key)
    if cached and now - _group_scores_cache_ts.get(cache_key, 0) < 300:
        return cached

    out = {}
    for member in members:
        atp = _fetch_tour_score(member, 'atp')
        wta = _fetch_tour_score(member, 'wta')
        combined = None
        if atp is not None and wta is not None:
            combined = atp + wta
        elif atp is not None:
            combined = atp
        elif wta is not None:
            combined = wta
        out[member.lower()] = {'atp': atp, 'wta': wta, 'combined': combined}

    if out:
        _group_scores_cache[cache_key]    = out
        _group_scores_cache_ts[cache_key] = now

    return out


# Tournament data cache: shared draw+results across all users per request
_tourney_cache    = {}
_tourney_cache_ts = {}
_pre_existing_completed = set()   # matches already done at server start — not "today"
_startup_snapshot_done  = set()   # which tours have been snapshotted


def _get_tournament_data(tour, members):
    """
    Return (r1_draw, match_results) for the given tour, cached 3 minutes.
    Fetches the first available member's bracket page to decode the draw.
    """
    now = time.time()
    if tour in _tourney_cache and now - _tourney_cache_ts.get(tour, 0) < 180:
        return _tourney_cache[tour]

    for username in members:
        try:
            html = _fetch_bracket_html(username, tour)
            flat = _parse_flat_array(html)
            if flat:
                r1_draw, match_results, all_matches = _extract_bracket_data(flat)
                if r1_draw:
                    _tourney_cache[tour] = (r1_draw, match_results, all_matches)
                    _tourney_cache_ts[tour] = now
                    return r1_draw, match_results, all_matches
        except Exception:
            continue

    return {}, {}, []


def get_data(members=None):
    if members is None:
        members = MEMBERS
    if not members:
        return {'players': [], 'updated': _now_et().strftime('%b %d, %Y · %I:%M:%S %p ET')}

    # Pull exact scores from served.bracket.tennis
    group_scores = _scrape_group_scores(members)

    # Shared draw + results needed for max-score calculation
    atp_draw, atp_results, _ = _get_tournament_data('atp', members)
    wta_draw, wta_results, _ = _get_tournament_data('wta', members)

    players = []
    for i, member in enumerate(members):
        s = group_scores.get(member.lower(), {})
        atp_score = s.get('atp')
        wta_score = s.get('wta')
        combined  = s.get('combined')

        if combined is None:
            if atp_score is not None and wta_score is not None:
                combined = atp_score + wta_score
            elif atp_score is not None:
                combined = atp_score
            elif wta_score is not None:
                combined = wta_score

        # Max score: calculated locally from picks + remaining bracket
        atp_max = wta_max = None
        try:
            html = _fetch_bracket_html(member, 'atp')
            picks = _extract_picks(html)
            if picks and atp_draw:
                atp_max = _calculate_max_score(picks, atp_draw, atp_results)
        except Exception:
            pass
        try:
            html = _fetch_bracket_html(member, 'wta')
            picks = _extract_picks(html)
            if picks and wta_draw:
                wta_max = _calculate_max_score(picks, wta_draw, wta_results)
        except Exception:
            pass

        max_combined = None
        if atp_max is not None and wta_max is not None:
            max_combined = atp_max + wta_max
        elif atp_max is not None:
            max_combined = atp_max
        elif wta_max is not None:
            max_combined = wta_max

        players.append({
            'username':     member,
            'atp':          atp_score,
            'wta':          wta_score,
            'combined':     combined,
            'max_combined': max_combined,
            'color_idx':    i % len(COLORS),
        })

    players.sort(key=lambda p: (-(p['combined'] or -1), -(p['atp'] or -1)))

    global_ranks = _fetch_global_ranks()
    for p in players:
        p['global_rank'] = global_ranks.get(p['username'].lower())

    return {
        'players': players,
        'updated': _now_et().strftime('%b %d, %Y · %I:%M:%S %p ET'),
    }


# ── HTTP Server ───────────────────────────────────────────────────────────────

BUILT_HTML = build_html().encode('utf-8')

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def send_body(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/favicon.svg', '/favicon.ico', '/favicon.png'):
            import base64
            png_b64 = (
                'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAABLElEQVR4nO3VUQ7DIAwD'
                '0J5r9//ZNXaRTvuYNNGhBpTEDthSPwvxA4njUBRonq/HiZ4hPGeTT+ne1wY9+3T+lb'
                'kr30P4/ofudBtrkVmA3w/d9RKv8uUQZof3QoBBeAzuBZAOkVGeFsF74Ij1lilPhRA1'
                'aOS6S5SHI0QPmLF++dOH3QKW04fdgq0B2MqnImQNlA1gRhDAzgDM5VMQBLAzQPYgKI'
                'AuggAKlPfaXwACEIAASr4AnvvrBghAAAIQQMWXwGNfAfSyA0C3vAAEwI8QXl4AAhhD'
                'qARgLs+KkFpeAAMI7ADT5ZluAeT0mW4B5PRZEODlrQhMAO7lUQhU5S0IaIDw8pkItO'
                'XvILIBIMXbeCNY/kd3vsQLoWT5NhEA6E7TGUFog549PKVPdoW8AVlDXWOLYr6lAAAA'
                'AElFTkSuQmCC'
            )
            data = base64.b64decode(png_b64)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith('/api/data'):
            try:
                members = None
                if '?' in self.path:
                    qs = self.path.split('?', 1)[1]
                    for part in qs.split('&'):
                        if part.startswith('members='):
                            val = urllib.request.unquote(part[8:])
                            members = [m.strip() for m in val.split(',') if m.strip()]
                data = get_data(members)
                body = json.dumps(data).encode()
                self.send_body(body, 'application/json')
            except Exception as e:
                self.send_body(str(e).encode(), 'text/plain', 500)
        elif self.path.startswith('/api/picks'):
            try:
                user = ''
                tour = 'atp'
                members = None
                if '?' in self.path:
                    qs = self.path.split('?', 1)[1]
                    for part in qs.split('&'):
                        if part.startswith('user='):
                            user = urllib.request.unquote(part[5:]).strip()
                        elif part.startswith('tour='):
                            tour = part[5:].lower()
                        elif part.startswith('members='):
                            val = urllib.request.unquote(part[8:])
                            members = [m.strip() for m in val.split(',') if m.strip()]
                members = members or MEMBERS
                r1_draw, match_results, _ = _get_tournament_data(tour, members)
                html = _fetch_bracket_html(user, tour)
                raw_picks = _extract_picks(html)
                eliminated = {r['loser'] for r in match_results.values() if r.get('loser')}
                named = {}
                for (rnd, mpos), slot in raw_picks.items():
                    if slot not in r1_draw:
                        continue
                    player_name, _ = r1_draw[slot]
                    result = match_results.get((rnd, mpos))
                    if result:
                        status = 'correct' if result.get('winner') == player_name else 'wrong'
                    elif player_name in eliminated:
                        status = 'eliminated'
                    else:
                        status = 'future'
                    named[f'{rnd}:{mpos}'] = {'player': player_name, 'status': status}
                self.send_body(json.dumps({'picks': named}).encode(), 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'picks': {}}).encode(), 'application/json')
        elif self.path.startswith('/api/debug_espn'):
            try:
                today_str = _now_et().strftime('%Y%m%d')
                results = {}
                for label, url in [
                    ('usopen', f'https://site.api.espn.com/apis/site/v2/sports/tennis/usopen/scoreboard?dates={today_str}&limit=100'),
                    ('atp',    f'https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates={today_str}&limit=100'),
                    ('wta',    f'https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates={today_str}&limit=100'),
                    ('generic',f'https://site.api.espn.com/apis/site/v2/sports/tennis/scoreboard?dates={today_str}&limit=100'),
                ]:
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=8) as r:
                            raw = json.loads(r.read().decode())
                        matches = []
                        for ev in raw.get('events', []):
                            for comp in ev.get('competitions', []):
                                st = (comp.get('status') or {}).get('type', {})
                                comps = comp.get('competitors', [])
                                p1 = comps[0].get('athlete',{}).get('displayName','?') if comps else '?'
                                p2 = comps[1].get('athlete',{}).get('displayName','?') if len(comps)>1 else '?'
                                matches.append({
                                    'match': f'{p1} vs {p2}',
                                    'event_name': ev.get('name',''),
                                    'comp_date': comp.get('date',''),
                                    'status': st.get('name',''),
                                    'completed': st.get('completed'),
                                    'detail': st.get('shortDetail',''),
                                })
                        results[label] = {'count': len(matches), 'matches': matches}
                    except Exception as e:
                        results[label] = {'error': str(e)}
                self.send_body(json.dumps({'today_et': today_str, 'endpoints': results}, indent=2).encode(), 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'error': str(e)}).encode(), 'application/json')
        elif self.path.startswith('/api/debug_today'):
            try:
                tour = 'atp'
                if 'tour=wta' in self.path:
                    tour = 'wta'
                parsed = _fetch_espn_today_matches(tour)
                self.send_body(json.dumps({'tour': tour, 'count': len(parsed), 'matches': parsed}, indent=2).encode(), 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'error': str(e)}).encode(), 'application/json')
        elif self.path.startswith('/api/today_matches'):
            try:
                tour = 'atp'
                if '?' in self.path:
                    for part in self.path.split('?', 1)[1].split('&'):
                        if part.startswith('tour='):
                            tour = part[5:].lower()

                # Hybrid approach:
                #   Bracket  → live + completed (reliable, no date ambiguity)
                #   ESPN     → upcoming only, date-filtered to today ET (drops completed, but we don't need that)
                matches = []
                seen_pairs = set()

                # --- BRACKET: live + completed from active round ---
                try:
                    _, results_map, all_matches = _get_tournament_data(tour, MEMBERS)
                    score_lookup = {(m['round'], m['pos']): m.get('score','')
                                    for m in all_matches if m.get('winner') and m.get('score')}
                    incomplete_rounds = {m.get('round',0) for m in all_matches
                                         if not m.get('winner') or m.get('is_live')}
                    completed_rounds  = {m.get('round',0) for m in all_matches
                                         if m.get('winner') and not m.get('is_live')}
                    active_round = min(incomplete_rounds) if incomplete_rounds else (max(completed_rounds) if completed_rounds else 0)
                    espn_live   = _fetch_espn_live(tour)
                    espn_scores = espn_live.get('scores', {})
                    usopen_sched = _fetch_usopen_schedule(tour)

                    for m in all_matches:
                        if m.get('round') != active_round:
                            continue
                        p1 = m.get('p1','')
                        p2 = m.get('p2','')
                        if not p1 or not p2:
                            continue
                        pair = tuple(sorted([p1, p2]))
                        p1_rank = m.get('p1_rank', 999)
                        p2_rank = m.get('p2_rank', 999)
                        if m.get('is_live'):
                            # Use bracket's own score field — served.bracket shows live scores
                            # and the name already matches exactly. No ESPN name-matching needed.
                            score = m.get('score','') or score_lookup.get((m['round'], m['pos']),'')
                            matches.append({'p1':p1,'p2':p2,'p1_country':m.get('p1_country',''),'p2_country':m.get('p2_country',''),
                                            'p1_rank':p1_rank,'p2_rank':p2_rank,
                                            'winner':'','score':score,'is_live':True,'scheduled_time':'','status':'live'})
                            seen_pairs.add(pair)
                        elif m.get('winner'):
                            matches.append({'p1':p1,'p2':p2,'p1_country':m.get('p1_country',''),'p2_country':m.get('p2_country',''),
                                            'p1_rank':p1_rank,'p2_rank':p2_rank,
                                            'winner':m.get('winner',''),'score':score_lookup.get((m['round'],m['pos']),''),
                                            'is_live':False,'scheduled_time':'','status':'final'})
                            seen_pairs.add(pair)
                except Exception:
                    pass

                # --- ESPN: upcoming only, today ET date-filtered ---
                espn_upcoming_count = 0
                try:
                    espn_all = _fetch_espn_today_matches(tour)
                    for m in espn_all:
                        if m.get('status') != 'upcoming':
                            continue
                        pair = tuple(sorted([m.get('p1',''), m.get('p2','')]))
                        if pair not in seen_pairs:
                            matches.append(m)
                            seen_pairs.add(pair)
                            espn_upcoming_count += 1
                except Exception:
                    pass

                # Fallback: if ESPN gave no upcoming, use incomplete bracket matches
                # from the active round (matches without a winner and not live)
                if espn_upcoming_count == 0:
                    for m in all_matches:
                        if m.get('round') != active_round:
                            continue
                        p1 = m.get('p1','')
                        p2 = m.get('p2','')
                        if not p1 or not p2:
                            continue
                        if m.get('winner') or m.get('is_live'):
                            continue  # skip completed and live — only want not-started
                        pair = tuple(sorted([p1, p2]))
                        if pair not in seen_pairs:
                            # Look up scheduled time from US Open schedule feed
                            p1_last = p1.strip().split()[-1] if p1.strip() else ''
                            p2_last = p2.strip().split()[-1] if p2.strip() else ''
                            sched_key_last = frozenset([p1_last.lower(), p2_last.lower()])
                            sched_key_full = frozenset([p1.lower(), p2.lower()])
                            sched_time = (usopen_sched.get(sched_key_full)
                                          or usopen_sched.get(sched_key_last)
                                          or 'TBD')
                            matches.append({'p1':p1,'p2':p2,'p1_country':m.get('p1_country',''),'p2_country':m.get('p2_country',''),
                                            'p1_rank':m.get('p1_rank',999),'p2_rank':m.get('p2_rank',999),
                                            'winner':'','score':'','is_live':False,'scheduled_time':sched_time,'status':'upcoming'})
                            seen_pairs.add(pair)

                # Also patch in US Open times for any ESPN upcoming matches missing a time
                for m in matches:
                    if m.get('status') == 'upcoming' and not m.get('scheduled_time') or m.get('scheduled_time') == 'TBD':
                        p1_last = (m.get('p1','') or '').strip().split()[-1] if m.get('p1','').strip() else ''
                        p2_last = (m.get('p2','') or '').strip().split()[-1] if m.get('p2','').strip() else ''
                        sched_key_last = frozenset([p1_last.lower(), p2_last.lower()])
                        sched_key_full = frozenset([(m.get('p1','') or '').lower(), (m.get('p2','') or '').lower()])
                        t = usopen_sched.get(sched_key_full) or usopen_sched.get(sched_key_last)
                        if t:
                            m['scheduled_time'] = t

                self.send_body(json.dumps({'matches': matches, 'source': 'hybrid'}).encode(), 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'matches': [], 'source': 'error', 'error': str(e)}).encode(), 'application/json')
        elif self.path.startswith('/api/bracket'):
            try:
                tour = 'atp'
                members = None
                if '?' in self.path:
                    qs = self.path.split('?', 1)[1]
                    for part in qs.split('&'):
                        if part.startswith('tour='):
                            tour = part[5:].lower()
                        elif part.startswith('members='):
                            val = urllib.request.unquote(part[8:])
                            members = [m.strip() for m in val.split(',') if m.strip()]
                members = members or MEMBERS
                _, _, all_matches = _get_tournament_data(tour, members)
                espn = _fetch_espn_live(tour)
                # Startup snapshot: first call per tour marks all already-completed matches
                # as pre-existing (not today). Only matches that complete *after* server
                # start are tagged completed_today=True.
                if tour not in _startup_snapshot_done:
                    for m in all_matches:
                        if m.get('winner') and not m.get('is_live'):
                            _pre_existing_completed.add((tour, m.get('round'), m.get('pos')))
                    _startup_snapshot_done.add(tour)
                for m in all_matches:
                    key = (tour, m.get('round'), m.get('pos'))
                    if m.get('winner') and not m.get('is_live'):
                        m['completed_today'] = key not in _pre_existing_completed
                    else:
                        m['completed_today'] = False
                body = json.dumps({
                    'tour': tour,
                    'matches': all_matches,
                    'live_players': list(espn['live']),
                    'espn_scores': espn['scores'],
                }).encode()
                self.send_body(body, 'application/json')
            except Exception as e:
                self.send_body(str(e).encode(), 'text/plain', 500)
        elif self.path.startswith('/api/summary'):
            try:
                if 'bust=' in self.path:
                    global _summary_cache, _summary_cache_ts
                    _summary_cache = {}
                    _summary_cache_ts = 0
                body = json.dumps(_fetch_ai_summary()).encode()
                self.send_body(body, 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'summary':'','updated':'','error':str(e)}).encode(), 'application/json')
        elif self.path.startswith('/api/odds/sports'):
            # Debug: show all tennis sports The Odds API returns for this key
            try:
                if not ODDS_API_KEY:
                    body = json.dumps({'error': 'no key'}).encode()
                else:
                    sports = _odds_api_get(f'/sports?apiKey={ODDS_API_KEY}&all=true')
                    tennis = [s for s in sports if 'tennis' in (s.get('key','') + s.get('title','')).lower()]
                    body = json.dumps(tennis, indent=2).encode()
                self.send_body(body, 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'error': str(e)}).encode(), 'application/json')
        elif self.path.startswith('/api/odds'):
            try:
                body = json.dumps(_fetch_dk_odds()).encode()
                self.send_body(body, 'application/json')
            except Exception as e:
                self.send_body(json.dumps({'atp':[],'wta':[],'error':str(e)}).encode(), 'application/json')
        else:
            self.send_body(BUILT_HTML, 'text/html; charset=utf-8')

    def do_POST(self):
        global _live_odds, _live_odds_updated
        if self.path == '/api/update-odds':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body   = json.loads(self.rfile.read(length).decode())
                token  = self.headers.get('X-Update-Token', '')
                if ODDS_UPDATE_TOKEN and token != ODDS_UPDATE_TOKEN:
                    self.send_response(401)
                    self.end_headers()
                    return
                mens   = [(item['odds_american'], item['player']) for item in body.get('mens', [])[:10]]
                womens = [(item['odds_american'], item['player']) for item in body.get('womens', [])[:10]]
                if mens or womens:
                    _live_odds = {'atp': mens, 'wta': womens}
                    _live_odds_updated = body.get('updated', _now_et().strftime('%B %d, %Y'))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress server log noise


if __name__ == '__main__':
    print(f'🎾 US Open 2026 Bracket Dashboard')
    print(f'   Running at http://localhost:{PORT}')
    print(f'   Tracking {len(MEMBERS)} players: {", ".join(MEMBERS)}')
    print(f'   Refreshes every 5 minutes from served.bracket.tennis')
    print(f'   Press Ctrl+C to stop\n')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
