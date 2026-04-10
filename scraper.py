"""
scraper.py — IPL Fantasy XI Clash Analyzer

Data pipeline (3-layer):
  Layer 1: Cricsheet.org — downloads ball-by-ball IPL CSV data,
            computes career batting/bowling stats using pandas + BeautifulSoup
            (REAL scraping — downloads zip, parses CSV, aggregates stats)

  Layer 2: ESPNCricinfo/Cricbuzz — direct profile scrape with BeautifulSoup
            (fallback if player not found in Cricsheet)

  Layer 3: CSV cache — saves scraped data locally to avoid re-scraping

Concepts demonstrated:
  - Web scraping (HTTP download + zip extraction + CSV parsing)
  - BeautifulSoup HTML parsing
  - File handling (CSV cache, zip extraction)
  - OOP (Player, XI, Clash classes)
"""

import os, sys, re, csv, json, time
import requests
from curl_cffi.requests import Session as CurlSession
from bs4 import BeautifulSoup

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
IDS_PATH  = os.path.join(BASE_DIR, "data", "player_ids.json")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(IDS_PATH), exist_ok=True)

sys.path.insert(0, BASE_DIR)
from models import Player, ScrapeError, PlayerNotFoundError

# ── Cricsheet scraper (Layer 1) ────────────────────────────────────────────────
try:
    from cricket_player_scraper import CricketPlayerScraper
    _cricsheet = CricketPlayerScraper()
    _cricsheet_available = True
except ImportError:
    _cricsheet_available = False

# ── RapidAPI + Cricbuzz (Layer 2) ──────────────────────────────────────────────
RAPIDAPI_KEY  = "a4378e1240msh25c5223e50a7129p1b0222jsn01742c6c8001"
RAPIDAPI_HOST = "unofficial-cricbuzz.p.rapidapi.com"
RAPIDAPI_HEADERS = {
    "x-rapidapi-key":  RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
}

_cb_session = None
CB_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.cricbuzz.com/",
}
DELAY = 1.0

def _get_cb_session():
    global _cb_session
    if _cb_session is None:
        _cb_session = CurlSession(impersonate="chrome124")
    return _cb_session


# ── Player ID database ─────────────────────────────────────────────────────────
def _load_ids() -> dict:
    if not os.path.exists(IDS_PATH):
        return {}
    with open(IDS_PATH) as f:
        raw = json.load(f)
    NAV = {"profile","overview","batting","bowling","fielding","stats","cricket",
           "news","videos","photos","more","career","matches","series","squad"}
    return {k: v for k, v in raw.items()
            if not any(w in NAV for w in k.split())
            and k.replace(" ","").replace("-","").replace("'","").replace(".","").isalpha()}


def resolve_player_id(raw: str) -> tuple:
    """Resolve raw input → (display_name, espn_id, record_name)."""
    raw = raw.strip()
    if raw.isdigit():
        return (f"Player #{raw}", int(raw), None)
    slug = raw.split("/")[-1].split("?")[0]
    m = re.search(r'-(\d{4,8})$', slug)
    if m:
        pid  = int(m.group(1))
        name = re.sub(r'-\d+$', '', slug).replace("-", " ").title()
        return (name, pid, None)
    ids  = _load_ids()
    key  = " ".join(raw.lower().strip().split())
    if key in ids:
        val = ids[key]
        if isinstance(val, list):
            return (raw.title(), val[1], val[0])
        return (raw.title(), val, None)
    words = key.split()
    if len(words) < 2:
        raise PlayerNotFoundError(f"'{raw}' is too short. Please enter both First and Last name (e.g., 'Virat Kohli').")

    for matches in [
        [(k,v) for k,v in ids.items() if all(w in k.split() for w in words)],
        [(k,v) for k,v in ids.items() if all(w in k for w in words)],
    ]:
        if len(matches) == 1:
            m_key, m_val = matches[0]
            if isinstance(m_val, list):
                return (m_key.title(), m_val[1], m_val[0])
            return (m_key.title(), m_val, None)
        if len(matches) > 1:
            best = min(matches, key=lambda x: (abs(len(x[0])-len(key)), len(x[0])))
            if isinstance(best[1], list):
                return (best[0].title(), best[1][1], best[1][0])
            return (best[0].title(), best[1], None)
    raise PlayerNotFoundError(raw)


# ── Layer 1: Cricsheet stats ───────────────────────────────────────────────────
def _cricsheet_stats(name: str, record_name: str = None) -> dict:
    """
    Download ball-by-ball IPL data from cricsheet.org and compute
    career batting + bowling stats using pandas aggregation.

    If record_name is provided (from the JSON database), it uses that directly.
    Otherwise, it searches using heuristics.
    """
    if not _cricsheet_available:
        return {}

    try:
        # If record_name is pre-resolved in the JSON database, use it directly
        if record_name:
            cs_name = _cricsheet.search_player(record_name)
        else:
            # Cricsheet uses short names: "V Kohli", "RG Sharma", "JJ Bumrah"
            # Try multiple formats to find the right player
            parts = name.split()
            candidates = [name]  # full name first
            if len(parts) >= 2:
                # 1. Try common Initial + Last Name (e.g. "V Kohli")
                candidates += [
                    f"{parts[0][0]} {parts[-1]}",   
                    f"{parts[0][:2]} {parts[-1]}",  
                ]
                
                # 2. Handle concatenated first names (e.g. "Suryakumar" -> "SA Yadav")
                if len(parts[0]) > 6:
                    candidates.append(f"{parts[0][0]}A {parts[-1]}") 
                    candidates.append(f"{parts[0][0]}K {parts[-1]}") 

                # 3. Two initials if middle name exists (e.g. "MS Dhoni")
                if len(parts) >= 3:
                    candidates.append(f"{parts[0][0]}{parts[1][0]} {parts[-1]}")
                
                # 4. Surname as a last resort
                candidates.append(parts[-1])

            cs_name = None
            for candidate in candidates:
                cs_name = _cricsheet.search_player(candidate)
                if cs_name:
                    break

        if not cs_name:
            return {}

        # Get year-by-year stats
        bat_df  = _cricsheet.get_batting_stats(player_name=cs_name, tournament='IPL')
        bowl_df = _cricsheet.get_bowling_stats(player_name=cs_name, tournament='IPL')

        stats = {}

        # Aggregate batting across all years
        if not bat_df.empty:
            runs      = int(bat_df['Runs'].sum())
            matches   = int(bat_df['Mat'].sum())
            innings   = int(bat_df['Inns'].sum())
            dismissed = int(bat_df['Dismissed'].sum())
            balls     = int(bat_df['Balls'].sum())
            fours     = int(bat_df['4s'].sum())
            sixes     = int(bat_df['6s'].sum())
            fifties   = int(bat_df['50s'].sum())
            hundreds  = int(bat_df['100s'].sum())

            avg = round(runs / dismissed, 2) if dismissed > 0 else 0.0
            sr  = round(runs / balls * 100, 2) if balls > 0 else 0.0

            # Highest score from year-by-year data isn't available directly
            # Use recent form: last 5 innings scores
            stats.update({
                "ipl_matches":  matches,
                "ipl_innings":  innings,
                "ipl_runs":     runs,
                "ipl_avg":      avg,
                "ipl_sr":       sr,
                "ipl_fours":    fours,
                "ipl_sixes":    sixes,
                "ipl_fifties":  fifties,
                "ipl_hundreds": hundreds,
                "ipl_not_outs": innings - dismissed,
            })

        # Aggregate bowling across all years
        if not bowl_df.empty:
            overs   = round(float(bowl_df['Overs'].sum()), 1)
            wickets = int(bowl_df['Wkts'].sum())
            runs_c  = int(bowl_df['Runs'].sum())

            bowl_avg = round(runs_c / wickets, 2) if wickets > 0 else 0.0
            economy  = round(runs_c / float(overs), 2) if overs > 0 else 0.0
            sr_bowl  = round(float(bowl_df['Balls'].sum()) / wickets, 2) if wickets > 0 else 0.0

            stats.update({
                "ipl_overs":    overs,
                "ipl_wickets":  wickets,
                "ipl_bowl_avg": bowl_avg,
                "ipl_economy":  economy,
                "ipl_sr_bowl":  sr_bowl,
            })

        return stats

    except Exception as e:
        print(f"\n    [Cricsheet error: {e}]", end="")
        return {}


# ── Layer 2: RapidAPI search + Cricbuzz HTML scrape ────────────────────────────
def _get_cricbuzz_id(name: str) -> tuple:
    """Search RapidAPI → return (cricbuzz_id, cricbuzz_name)."""
    try:
        r = requests.get(
            f"https://{RAPIDAPI_HOST}/players/search",
            headers=RAPIDAPI_HEADERS,
            params={"plrN": name},
            timeout=10,
        )
        if r.status_code == 200:
            players = r.json().get("player", [])
            if players:
                for p in players:
                    if p["name"].lower() == name.lower():
                        return p["id"], p["name"]
                return players[0]["id"], players[0]["name"]
    except Exception as e:
        print(f"\n    [Search error: {e}]", end="")
    return None, None


def _scrape_cricbuzz(cb_id: str, cb_name: str) -> dict:
    """
    Scrape player profile from cricbuzz.com using BeautifulSoup.
    Parses the batting/bowling HTML tables and bio section.
    """
    slug = cb_name.lower().replace(" ", "-")
    url  = f"https://www.cricbuzz.com/profiles/{cb_id}/{slug}"

    try:
        time.sleep(DELAY)
        r = _get_cb_session().get(url, headers=CB_HEADERS, timeout=20)
        if r.status_code != 200:
            return {}
    except Exception as e:
        return {}

    soup   = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 3:
        return {}

    def parse_table(table):
        rows    = table.find_all("tr")
        if not rows: return {}
        headers = [td.get_text(strip=True) for td in rows[0].find_all(["td","th"])]
        out = {}
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) == len(headers):
                out[cells[0]] = dict(zip(headers[1:], cells[1:]))
        return out

    def get(d, stat, fmt, cast=float, default=0):
        try:
            v = d.get(stat, {}).get(fmt, "")
            if not v or str(v).strip() in ("-","--","","0/0"): return default
            return cast(str(v).replace("*","").strip())
        except: return default

    bat_raw  = parse_table(tables[2])
    bowl_raw = parse_table(tables[3]) if len(tables) > 3 else {}

    bat_fmt  = "IPL" if get(bat_raw,  "Runs",    "IPL", int) > 0 else "T20"
    bowl_fmt = "IPL" if get(bowl_raw, "Wickets", "IPL", int) > 0 else "T20"

    batting = {
        "ipl_matches":  get(bat_raw, "Matches", bat_fmt, int),
        "ipl_innings":  get(bat_raw, "Innings", bat_fmt, int),
        "ipl_runs":     get(bat_raw, "Runs",    bat_fmt, int),
        "ipl_highest":  get(bat_raw, "Highest", bat_fmt, int),
        "ipl_avg":      get(bat_raw, "Average", bat_fmt, float),
        "ipl_sr":       get(bat_raw, "SR",      bat_fmt, float),
        "ipl_not_outs": get(bat_raw, "Not Out", bat_fmt, int),
        "ipl_fours":    get(bat_raw, "Fours",   bat_fmt, int),
        "ipl_sixes":    get(bat_raw, "Sixes",   bat_fmt, int),
        "ipl_fifties":  get(bat_raw, "50s",     bat_fmt, int),
        "ipl_hundreds": get(bat_raw, "100s",    bat_fmt, int),
        "ipl_ducks":    get(bat_raw, "Ducks",   bat_fmt, int),
    }
    balls = get(bowl_raw, "Balls", bowl_fmt, int)
    bowling = {
        "ipl_overs":    round(balls / 6, 1),
        "ipl_wickets":  get(bowl_raw, "Wickets", bowl_fmt, int),
        "ipl_bowl_avg": get(bowl_raw, "Avg",     bowl_fmt, float),
        "ipl_economy":  get(bowl_raw, "Eco",     bowl_fmt, float),
        "ipl_sr_bowl":  get(bowl_raw, "SR",      bowl_fmt, float),
        "ipl_best":     bowl_raw.get("BBI", {}).get(bowl_fmt, "0/0") or "0/0",
    }

    # Parse batting/bowling style from bio
    bat_hand = bowl_style = ""
    for tag in soup.find_all(["span","div","p","b","li"]):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) > 80: continue
        tl = text.lower()
        if not bat_hand:
            if "right" in tl and "bat" in tl: bat_hand = "Right-hand bat"
            elif "left" in tl and "bat" in tl: bat_hand = "Left-hand bat"
        if not bowl_style:
            if any(k in tl for k in ["right-arm","left-arm","offbreak","legbreak","orthodox","googly","chinaman"]):
                bowl_style = text[:50].strip()

    return {**batting, **bowling,
            "batting_hand": bat_hand, "bowling_style": bowl_style}


# ── Cache ──────────────────────────────────────────────────────────────────────
FIELDS = [
    "name","cricinfo_id","cricbuzz_id",
    "ipl_matches","ipl_innings","ipl_runs","ipl_highest","ipl_avg","ipl_sr",
    "ipl_not_outs","ipl_fours","ipl_sixes","ipl_fifties","ipl_hundreds","ipl_ducks",
    "ipl_overs","ipl_wickets","ipl_bowl_avg","ipl_economy","ipl_sr_bowl","ipl_best",
    "batting_hand","bowling_style","recent_scores",
]

def _cache_path(pid: int) -> str:
    return os.path.join(CACHE_DIR, f"{pid}.csv")

def _save(player: Player):
    with open(_cache_path(player.cricinfo_id), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({
            "name":          player.name,
            "cricinfo_id":   player.cricinfo_id,
            "cricbuzz_id":   getattr(player, "cricbuzz_id", ""),
            "ipl_matches":   player.ipl_matches,
            "ipl_innings":   player.ipl_innings,
            "ipl_runs":      player.ipl_runs,
            "ipl_highest":   player.ipl_highest,
            "ipl_avg":       player.ipl_avg,
            "ipl_sr":        player.ipl_sr,
            "ipl_not_outs":  player.ipl_not_outs,
            "ipl_fours":     player.ipl_fours,
            "ipl_sixes":     player.ipl_sixes,
            "ipl_fifties":   player.ipl_fifties,
            "ipl_hundreds":  player.ipl_hundreds,
            "ipl_ducks":     player.ipl_ducks,
            "ipl_overs":     player.ipl_overs,
            "ipl_wickets":   player.ipl_wickets,
            "ipl_bowl_avg":  player.ipl_bowl_avg,
            "ipl_economy":   player.ipl_economy,
            "ipl_sr_bowl":   player.ipl_sr_bowl,
            "ipl_best":      player.ipl_best,
            "batting_hand":  player.batting_hand,
            "bowling_style": player.bowling_style,
            "recent_scores": json.dumps(player.recent_scores),
        })

def _load(name: str, pid: int):
    path = _cache_path(pid)
    if not os.path.exists(path): return None
    try:
        with open(path, newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f), None)
        if not row: return None
        p = Player(row["name"], int(row["cricinfo_id"]))
        p.cricbuzz_id   = row.get("cricbuzz_id", "")
        p.ipl_matches   = int(row["ipl_matches"])
        p.ipl_innings   = int(row["ipl_innings"])
        p.ipl_runs      = int(row["ipl_runs"])
        p.ipl_highest   = int(row["ipl_highest"])
        p.ipl_avg       = float(row["ipl_avg"])
        p.ipl_sr        = float(row["ipl_sr"])
        p.ipl_not_outs  = int(row["ipl_not_outs"])
        p.ipl_fours     = int(row["ipl_fours"])
        p.ipl_sixes     = int(row["ipl_sixes"])
        p.ipl_fifties   = int(row["ipl_fifties"])
        p.ipl_hundreds  = int(row["ipl_hundreds"])
        p.ipl_ducks     = int(row.get("ipl_ducks", 0))
        p.ipl_overs     = float(row["ipl_overs"])
        p.ipl_wickets   = int(row["ipl_wickets"])
        p.ipl_bowl_avg  = float(row["ipl_bowl_avg"])
        p.ipl_economy   = float(row["ipl_economy"])
        p.ipl_sr_bowl   = float(row["ipl_sr_bowl"])
        p.ipl_best      = row["ipl_best"]
        p.batting_hand  = row["batting_hand"]
        p.bowling_style = row["bowling_style"]
        p.recent_scores = json.loads(row.get("recent_scores", "[]"))
        p.detect_roles()
        return p
    except: return None


# ── Main public API ────────────────────────────────────────────────────────────
def scrape_player(raw_input: str, force: bool = False) -> Player:
    """
    Full 3-layer scraping pipeline:
      1. Check CSV cache
      2. Try Cricsheet (ball-by-ball data → pandas aggregation)
      3. Fallback: RapidAPI search → Cricbuzz HTML scrape
    """
    name, pid, record_name = resolve_player_id(raw_input)
    print(f"  ► {name:<28} (ID:{pid})", end="  ", flush=True)

    if not force:
        cached = _load(name, pid)
        if cached:
            print(f"cache ✓  [{cached.ipl_runs}r / {cached.ipl_wickets}w / {cached.batting_role}]")
            return cached

    player = Player(name, pid)
    player.record_name = record_name

    # ── Layer 1: Cricsheet ─────────────────────────────────────────────────
    print("cricsheet...", end="  ", flush=True)
    cs_stats = _cricsheet_stats(name, record_name)

    # Validate cricsheet data — sanity check the stats make sense
    cs_runs    = cs_stats.get("ipl_runs", 0)
    cs_avg     = cs_stats.get("ipl_avg", 0.0)
    cs_sr      = cs_stats.get("ipl_sr", 0.0)
    cs_matches = cs_stats.get("ipl_matches", 0)
    cs_innings = cs_stats.get("ipl_innings", 0)

    # Flag as suspicious if stats look like a wrong player was matched:
    # - avg < 10 with 5+ innings (most batters avg 15+)
    # - SR < 80 with 5+ innings (IPL is high-octane, rarely below 90)
    # - very few runs despite many innings (wrong player)
    cs_suspicious = (
        cs_innings >= 5 and (
            cs_avg < 10 or
            (cs_sr > 0 and cs_sr < 80) or
            (cs_innings >= 10 and cs_runs < 100)
        )
    )

    if (cs_runs > 0 or cs_stats.get("ipl_wickets", 0) > 0) and not cs_suspicious:
        for key, val in cs_stats.items():
            if hasattr(player, key):
                setattr(player, key, val)
        print(f"cricsheet ✓", end="  ", flush=True)
        # Also get bio + highest from Cricbuzz
        cb_id, cb_name = _get_cricbuzz_id(name)
        if cb_id:
            player.cricbuzz_id = cb_id
            cb_stats = _scrape_cricbuzz(cb_id, cb_name)
            # Only take bio fields + highest from Cricbuzz
            for field in ["batting_hand", "bowling_style", "ipl_highest", "ipl_best"]:
                if cb_stats.get(field):
                    setattr(player, field, cb_stats[field])

    else:
        if cs_suspicious:
            print(f"cricsheet mismatch (avg={cs_avg:.1f}/mat={cs_matches})...", end="  ", flush=True)
        # ── Layer 2: Cricbuzz fallback ─────────────────────────────────────
        print(f"cricbuzz...", end="  ", flush=True)
        cb_id, cb_name = _get_cricbuzz_id(name)
        if not cb_id:
            parts = name.split()
            if len(parts) > 1:
                cb_id, cb_name = _get_cricbuzz_id(parts[-1])

        if cb_id:
            player.cricbuzz_id = cb_id
            cb_stats = _scrape_cricbuzz(cb_id, cb_name)
            for key, val in cb_stats.items():
                if hasattr(player, key):
                    setattr(player, key, val)

    player.detect_roles()
    _save(player)
    print(f"done ✓  [{player.ipl_runs}r / {player.ipl_wickets}w / {player.batting_role} / {player.bowling_type}]")
    return player


def scrape_xi(inputs: list, team_name: str, force: bool = False) -> list:
    print(f"\n  Loading {team_name}...")
    players = []
    for raw in inputs:
        try:
            players.append(scrape_player(raw, force=force))
        except PlayerNotFoundError as e:
            print(f"\n  ✗ {e}")
        except Exception as e:
            print(f"\n  ✗ Error: {e}")
    return players