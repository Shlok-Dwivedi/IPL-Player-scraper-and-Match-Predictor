"""
build_player_db.py — Builds COMPLETE database of every player who ever played IPL.

Uses curl_cffi to bypass ESPNCricinfo's TLS bot detection.

Run once: python build_player_db.py
Output:   data/player_ids.json
Time:     ~8-12 minutes
"""

import re, json, time, os, sys

# Use curl_cffi for TLS browser impersonation
try:
    from curl_cffi.requests import Session
    session = Session(impersonate="chrome124")
    print("Using curl_cffi (Chrome impersonation)")
except ImportError:
    import requests
    session = requests.Session()
    print("WARNING: curl_cffi not found, falling back to requests (may be blocked)")
    print("Install with: pip install curl_cffi")

from bs4 import BeautifulSoup

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "player_ids.json")
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espncricinfo.com/",
}
DELAY = 1.5

IPL_SERIES = [
    ("indian-premier-league-2008-313494",      313494),
    ("indian-premier-league-2009-374163",       374163),
    ("indian-premier-league-2010-418064",       418064),
    ("indian-premier-league-2011-466304",       466304),
    ("dlf-indian-premier-league-2012-520932",   520932),
    ("pepsi-indian-premier-league-2013-586733", 586733),
    ("pepsi-indian-premier-league-2014-695871", 695871),
    ("pepsi-indian-premier-league-2015-791129", 791129),
    ("ipl-2016-968923",                         968923),
    ("ipl-2017-1078425",                       1078425),
    ("ipl-2018-1131611",                       1131611),
    ("ipl-2019-1165643",                       1165643),
    ("ipl-2020-21-1210595",                    1210595),
    ("ipl-2021-1249214",                       1249214),
    ("ipl-2022-1298423",                       1298423),
    ("ipl-2023-1345038",                       1345038),
    ("indian-premier-league-2024-1410320",     1410320),
    ("ipl-2025-1449924",                       1449924),
    ("indian-premier-league-2026-1512140",     1512140),
]

STAT_URLS = [
    ("Batting",      "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11&type=batting&template=results&orderby=runs&page={p}"),
    ("Bowling",      "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11&type=bowling&template=results&orderby=wickets&page={p}"),
    ("Fielding",     "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11&type=fielding&template=results&orderby=dismissals&page={p}"),
    ("All-rounders", "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11&type=allround&template=results&orderby=runs&page={p}"),
]

NAV_WORDS = {"profile","overview","batting","bowling","fielding","stats","cricket",
             "news","videos","photos","more","career","matches","series","squad",
             "team","records","schedule","scorecard","ipl","t20","odi","test",
             "home","login","register","search","about","contact","privacy"}


def fetch(url):
    try:
        time.sleep(DELAY)
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and len(r.text) > 500:
            return BeautifulSoup(r.text, "html.parser")
        print(f" [HTTP {r.status_code}]", end="")
    except Exception as e:
        print(f" [ERR: {str(e)[:40]}]", end="")
    return None


def extract(soup) -> dict:
    players = {}
    if not soup:
        return players
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        m = re.search(r'/cricketers/([a-z][a-z0-9\-]+?)-(\d{4,8})(?:/|$)', href)
        if not m:
            continue
        pid = int(m.group(2))
        if pid < 1000:
            continue
        name = m.group(1).replace("-", " ").title()
        key  = name.lower()
        words = key.split()
        if not (1 <= len(words) <= 5):
            continue
        if any(w in NAV_WORDS for w in words):
            continue
        if not key.replace(" ","").replace("-","").replace("'","").replace(".","").isalpha():
            continue
        players[key] = pid
    return players


def scrape_season(slug, sid):
    year = re.search(r'(\d{4})', slug)
    year = year.group(1) if year else "?"
    print(f"\n  IPL {year}: ", end="", flush=True)

    all_p = {}
    soup = fetch(f"https://www.espncricinfo.com/series/{slug}/squads")
    if not soup:
        print("failed")
        return all_p

    all_p.update(extract(soup))

    # Find individual team squad links on the page
    team_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "series-squads" in href:
            full = f"https://www.espncricinfo.com{href}" if href.startswith("/") else href
            if full not in team_links:
                team_links.append(full)

    print(f"{len(all_p)} + {len(team_links)} teams...", end=" ", flush=True)

    for link in team_links:
        tsoup = fetch(link)
        if tsoup:
            all_p.update(extract(tsoup))

    print(f"→ {len(all_p)}")
    return all_p


def scrape_statsguru(url_tmpl, name, max_pages=50):
    all_p = {}
    print(f"\n  {name}: ", end="", flush=True)
    for page in range(1, max_pages + 1):
        soup = fetch(url_tmpl.format(p=page))
        if not soup:
            break
        p = extract(soup)
        if not p:
            break
        all_p.update(p)
        print(f"p{page}({len(all_p)})", end=" ", flush=True)
        if len(p) < 5:
            break
    print()
    return all_p


def main():
    print("=" * 60)
    print("  IPL COMPLETE PLAYER DATABASE BUILDER")
    print("=" * 60)

    existing = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            existing = json.load(f)
    print(f"Existing entries: {len(existing)}")

    all_players = dict(existing)

    # Phase 1: Squad pages
    print("\n── Phase 1: Squad pages (18 IPL seasons) ──────────────────")
    for slug, sid in IPL_SERIES:
        players = scrape_season(slug, sid)
        before = len(all_players)
        for n, p in players.items():
            if n not in all_players:
                all_players[n] = [None, p]
            elif not isinstance(all_players[n], list):
                all_players[n] = [None, p]
        print(f"    +{len(all_players)-before} new (running total: {len(all_players)})")

    # Phase 2: Statsguru
    print("\n── Phase 2: Statsguru records ──────────────────────────────")
    for name, url_tmpl in STAT_URLS:
        players = scrape_statsguru(url_tmpl, name, max_pages=30)
        before = len(all_players)
        # Update carefully: only add if name is new, or if the new one is more direct
        # Since extract() returns {'name': pid}, we wrap it in [None, pid]
        for n, p in players.items():
            if n not in all_players:
                all_players[n] = [None, p]
            elif not isinstance(all_players[n], list):
                all_players[n] = [None, p]
        print(f"    +{len(all_players)-before} new from {name}")

    # Phase 3: 2026 Newbie Sweep (Specific season filter)
    print("\n── Phase 3: 2026 Season Sweep ─────────────────────────────")
    spec_urls = [
        ("2026 Batting", "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11;template=results;type=batting;season=2026;page={p}"),
        ("2026 Bowling", "https://stats.espncricinfo.com/ci/engine/stats/index.html?class=11;template=results;type=bowling;season=2026;page={p}"),
    ]
    for name, url_tmpl in spec_urls:
        players = scrape_statsguru(url_tmpl, name, max_pages=10)
        before = len(all_players)
        for n, p in players.items():
            if n not in all_players:
                all_players[n] = [None, p]
        print(f"    +{len(all_players)-before} new from {name}")

    # Clean
    cleaned = {}
    for name, val in all_players.items():
        # Handle both old format (pid) and new format ([record_name, pid])
        if isinstance(val, list):
            rec_name, pid = val
        else:
            rec_name, pid = None, val

        if not isinstance(pid, int) or pid < 1000:
            continue
        words = name.split()
        if not (1 <= len(words) <= 5):
            continue
        if any(w in NAV_WORDS for w in words):
            continue
        if not name.replace(" ","").replace("-","").replace("'","").replace(".","").isalpha():
            continue
        cleaned[name] = [rec_name, pid]

    sorted_players = dict(sorted(cleaned.items()))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(sorted_players, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! {len(sorted_players)} total players saved to {OUTPUT}")


if __name__ == "__main__":
    main()
