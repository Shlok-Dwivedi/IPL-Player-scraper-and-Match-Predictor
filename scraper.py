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
import zipfile
import pandas as pd

class CricketPlayerScraper:
    def __init__(self, data_dir="cricsheet_data"):
        self.data_dir = os.path.join(BASE_DIR, data_dir)
        self.zip_path = os.path.join(self.data_dir, "ipl_male_csv2.zip")
        self.url = "https://cricsheet.org/downloads/ipl_male_csv2.zip"
        os.makedirs(self.data_dir, exist_ok=True)
        self._initialized = False
        self.player_map = {} # Maps record_name to list of match_ids

    def _ensure_data(self):
        if not os.path.exists(self.zip_path) or os.path.getsize(self.zip_path) < 1000000:
            print("  [Downloading Cricsheet DB (once)...]", end=" ", flush=True)
            try:
                r = requests.get(self.url, timeout=60)
                with open(self.zip_path, 'wb') as f:
                    f.write(r.content)
                print("done]")
            except Exception as e:
                print(f"failed: {e}]")
                return False

        if not self._initialized:
            try:
                # Load README or a file to check if it's a valid zip
                with zipfile.ZipFile(self.zip_path, 'r') as z:
                    # Index the players (Mapping player names to match IDs)
                    # To keep it fast, we only do this once
                    print("  [Indexing Cricsheet DB...]", end=" ", flush=True)
                    info_files = [f for f in z.namelist() if f.endswith('_info.csv')]
                    for f in info_files:
                        match_id = f.split('_')[0]
                        with z.open(f) as csvf:
                            content = csvf.read().decode('utf-8')
                            if 'player,' in content:
                                for line in content.splitlines():
                                    if line.startswith('info,player,'):
                                        parts = line.split(',')
                                        if len(parts) >= 4:
                                            p_name = parts[3].strip('"')
                                            if p_name not in self.player_map:
                                                self.player_map[p_name] = []
                                            self.player_map[p_name].append(match_id)
                    print("done]")
                self._initialized = True
            except Exception as e:
                print(f"Index failed: {e}")
                return False
        return True

    def search_player(self, candidate, record_name=None):
        self._ensure_data()
        
        # 1. Direct record_name check
        if record_name and record_name in self.player_map:
            return record_name
            
        # 2. Direct candidate check
        if candidate in self.player_map:
            return candidate
            
        # 3. Fuzzy match
        for p in self.player_map:
            if candidate.lower() in p.lower():
                return p
        return None

    def get_batting_stats(self, player_name, tournament='IPL'):
        if not self._ensure_data() or player_name not in self.player_map:
            return pd.DataFrame()
        
        match_ids = self.player_map[player_name]
        runs, balls, fours, sixes, matches, innings = 0, 0, 0, 0, len(match_ids), 0
        dismissed = 0
        
        with zipfile.ZipFile(self.zip_path, 'r') as z:
            for mid in match_ids:
                f = f"{mid}.csv"
                if f not in z.namelist(): continue
                df = pd.read_csv(z.open(f))
                # Cricsheet CSV2 columns: match_id, season, start_date, venue, innings, ball, batting_team, bowling_team, striker, non_striker, bowler, runs_off_bat, extras, wides, noballs, byes, legbyes, penalty, wicket_type, player_dismissed
                p_df = df[df['striker'] == player_name]
                if not p_df.empty:
                    innings += 1
                    runs += p_df['runs_off_bat'].sum()
                    balls += len(p_df[p_df['wides'].isna()])
                    fours += len(p_df[p_df['runs_off_bat'] == 4])
                    sixes += len(p_df[p_df['runs_off_bat'] == 6])
                    dismissed += len(df[df['player_dismissed'] == player_name])
                    
        return pd.DataFrame([{
            'Mat': matches, 'Inns': innings, 'Runs': runs, 'Balls': balls, 
            'Dismissed': dismissed, '4s': fours, '6s': sixes, '50s': 0, '100s': 0
        }])

    def get_bowling_stats(self, player_name, tournament='IPL'):
        if not self._ensure_data() or player_name not in self.player_map:
            return pd.DataFrame()

        match_ids = self.player_map[player_name]
        wkts, runs_c, balls = 0, 0, 0
        
        with zipfile.ZipFile(self.zip_path, 'r') as z:
            for mid in match_ids:
                f = f"{mid}.csv"
                if f not in z.namelist(): continue
                df = pd.read_csv(z.open(f))
                p_df = df[df['bowler'] == player_name]
                if not p_df.empty:
                    runs_c += p_df['runs_off_bat'].sum() + p_df['wides'].fillna(0).sum() + p_df['noballs'].fillna(0).sum()
                    balls += len(p_df[p_df['wides'].isna() & p_df['noballs'].isna()])
                    # Wickets (excluding run outs, retired hurt, etc)
                    valid_wkts = ['bowled', 'caught', 'caught and bowled', 'lbw', 'stumped', 'hit wicket']
                    wkts += len(p_df[p_df['wicket_type'].isin(valid_wkts)])

        return pd.DataFrame([{
            'Wkts': wkts, 'Runs': runs_c, 'Balls': balls, 'Overs': round(balls/6, 1)
        }])

_cricsheet = CricketPlayerScraper()
_cricsheet_available = True

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
            cs_name = _cricsheet.search_player(name, record_name=record_name)
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



# ── Layer 2: Statsguru/Cricinfo (ID-based) ───────────────────────────────────
def _scrape_statsguru(pid: int) -> dict:
    """
    Scrape IPL career stats directly from ESPNCricinfo Statsguru.
    trophy=117 ensures we only get Indian Premier League data.
    """
    url = f"https://stats.espncricinfo.com/ci/engine/player/{pid}.html?class=6;template=results;type=allround;trophy=117"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return {}
        
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table", class_="engineTable")
        if len(tables) < 3: return {}

        stats = {}
        target_table = tables[2]
        
        # 1. Map headers to indices
        header_row = target_table.find("thead")
        if not header_row: header_row = target_table.find("tr", class_="head")
        if not header_row: header_row = target_table.find("tr") # First row fallback
        
        cols = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        idx = {name: i for i, name in enumerate(cols)}
        
        # 2. Extract from 'filtered' row
        for row in target_table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) > 0 and cells[0].lower() == "filtered":
                def get_val(key, default=0):
                    i = idx.get(key)
                    if i is not None and i < len(cells):
                        raw = cells[i].replace("*","").replace("-","0")
                        try: return float(raw) if "." in raw else int(raw)
                        except: pass
                    return default

                stats.update({
                    "ipl_matches": int(get_val("Mat")),
                    "ipl_runs":    int(get_val("Runs")),
                    "ipl_wickets": int(get_val("Wkts")),
                    "ipl_highest": int(get_val("HS")),
                })
                # Check for SR in this table (Allround view might have it)
                sr = get_val("SR")
                if sr > 0: stats["ipl_sr"] = sr
                break
        
        if not stats: return {}

        # 3. Batting view for Innings/SR if missing
        if "ipl_sr" not in stats or stats.get("ipl_innings", 0) == 0:
            bat_url = f"https://stats.espncricinfo.com/ci/engine/player/{pid}.html?class=6;template=results;type=batting;trophy=117"
            br = requests.get(bat_url, headers=headers, timeout=10)
            if br.status_code == 200:
                bsoup = BeautifulSoup(br.text, "html.parser")
                btable = bsoup.find_all("table", class_="engineTable")[2]
                bhead = btable.find("tr", class_="head") or btable.find("tr")
                bcols = [th.get_text(strip=True) for th in bhead.find_all(["th", "td"])]
                bidx = {name: i for i, name in enumerate(bcols)}
                
                for brow in btable.find_all("tr"):
                    bcells = [td.get_text(strip=True) for td in brow.find_all(["td","th"])]
                    if len(bcells) > 0 and bcells[0].lower() == "filtered":
                        def get_bval(key, default=0):
                            i = bidx.get(key)
                            if i is not None and i < len(bcells):
                                raw = bcells[i].replace("-","0")
                                try: return float(raw) if "." in raw else int(raw)
                                except: pass
                            return default
                        
                        stats.update({
                            "ipl_innings":  int(get_bval("Inns")),
                            "ipl_sr":       float(get_bval("SR")),
                            "ipl_not_outs": int(get_bval("NO")),
                            "ipl_avg":      float(get_bval("Ave")),
                            "ipl_fifties":  int(get_bval("50")),
                            "ipl_hundreds": int(get_bval("100")),
                            "ipl_fours":    int(get_bval("4s")),
                            "ipl_sixes":    int(get_bval("6s")),
                            "ipl_ducks":    int(get_bval("0")),
                        })
                        break
        
        return stats
    except Exception as e:
        print(f" [Statsguru error: {e}]", end="")
        return {}


# ── Layer 3: Cricbuzz fallback logic ───────────────────────────────────────────
def _get_cricbuzz_id_ddg(name: str) -> tuple:
    """Fallback search using DuckDuckGo if Google blocks us."""
    try:
        url = f"https://duckduckgo.com/html/?q=cricbuzz+player+profile+{name.replace(' ','+')}"
        r = _get_cb_session().get(url, headers=CB_HEADERS, timeout=10)
        
        # Pattern 1: Direct link
        m = re.search(r'cricbuzz\.com/profiles/(\d+)/([^&"\' >]+)', r.text)
        if m:
            return m.group(1), m.group(2).replace("-", " ").title()
            
        # Pattern 2: Result in redirect param
        m = re.search(r'profiles(?:/|%2F)(\d+)(?:/|%2F)([^&"\' >%]+)', r.text)
        if m:
            return m.group(1), m.group(2).replace("-", " ").replace("%2D", " ").title()
            
    except Exception as e:
        print(f" [DDG error: {e}]", end="")
    return None, None

def _get_cricbuzz_id(name: str) -> tuple:
    """Search Cricbuzz via multiple engines to find profile ID."""
    # Try Google first
    cb_id, cb_name = None, None
    try:
        url = f"https://www.google.com/search?q=cricbuzz+player+profile+{name.replace(' ','+')}"
        r = _get_cb_session().get(url, headers=CB_HEADERS, timeout=10)
        m = re.search(r'cricbuzz\.com/profiles/(\d+)/([^&"\' >]+)', r.text)
        if m:
            cb_id, cb_name = m.group(1), m.group(2).replace("-", " ").title()
        else:
            m = re.search(r'profiles(?:/|%2F)(\d+)(?:/|%2F)([^&"\' >%]+)', r.text)
            if m:
                cb_id, cb_name = m.group(1), m.group(2).replace("-", " ").replace("%2D", " ").title()
    except:
        pass

    # Fallback to DuckDuckGo if Google failed or blocked us
    if not cb_id:
        cb_id, cb_name = _get_cricbuzz_id_ddg(name)
        
    return cb_id, cb_name


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

    bat_raw = {}
    for table in tables:
        if "Batting" in table.get_text():
            bat_raw = parse_table(table)
            break
            
    bowl_raw = {}
    for table in tables:
        if "Bowling" in table.get_text():
            bowl_raw = parse_table(table)
            break

    def determine_fmt(data):
        if "IPL" in data: return "IPL"
        if "T20" in data: return "T20"
        return next(iter(data.keys())) if data else "IPL"

    bat_fmt  = determine_fmt(bat_raw)
    bowl_fmt = determine_fmt(bowl_raw)

    batting = {
        "ipl_matches":  get(bat_raw, "Mat", bat_fmt, int),
        "ipl_innings":  get(bat_raw, "Inns", bat_fmt, int),
        "ipl_runs":     get(bat_raw, "Runs",    bat_fmt, int),
        "ipl_highest":  get(bat_raw, "HS", bat_fmt, int),
        "ipl_avg":      get(bat_raw, "Avg", bat_fmt, float),
        "ipl_sr":       get(bat_raw, "SR",      bat_fmt, float),
        "ipl_not_outs": get(bat_raw, "NO", bat_fmt, int),
        "ipl_fours":    get(bat_raw, "4s",   bat_fmt, int),
        "ipl_sixes":    get(bat_raw, "6s",   bat_fmt, int),
        "ipl_fifties":  get(bat_raw, "50s",     bat_fmt, int),
        "ipl_hundreds": get(bat_raw, "100s",    bat_fmt, int),
        "ipl_ducks":    get(bat_raw, "Ducks",   bat_fmt, int),
    }
    balls = get(bowl_raw, "Balls", bowl_fmt, int)
    bowling = {
        "ipl_overs":    get(bowl_raw, "Overs", bowl_fmt, float),
        "ipl_wickets":  get(bowl_raw, "Wkts", bowl_fmt, int),
        "ipl_bowl_avg": get(bowl_raw, "Avg",     bowl_fmt, float),
        "ipl_economy":  get(bowl_raw, "Econ",     bowl_fmt, float),
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
# ── Main public API ────────────────────────────────────────────────────────────
FORCE_FALLBACK = ["RG Sharma", "SA Yadav", "Rohit Sharma", "Suryakumar Yadav"]  # Known Cricsheet name collisions

def scrape_player(raw_input: str, force: bool = False) -> Player:
    """
    Full 3-layer scraping pipeline:
      1. Check CSV cache
      2. Try Cricsheet (ball-by-ball data → pandas aggregation)
      3. Fallback: RapidAPI search → Cricbuzz HTML scrape
    """
    name, pid, record_name = resolve_player_id(raw_input)
    print(f"  > {name:<28} (ID:{pid})", end="  ", flush=True)

    if not force:
        cached = _load(name, pid)
        if cached:
            print(f"cache [v]  [{cached.ipl_runs}r / {cached.ipl_wickets}w / {cached.batting_role}]")
            return cached

    player = Player(name, pid)
    player.record_name = record_name

    # ── Layer 1: Cricsheet ─────────────────────────────────────────────────
    # Skip Cricsheet if name is a known duplicate or suspicious
    skip_cricsheet = (record_name in FORCE_FALLBACK) or (name in FORCE_FALLBACK)
    
    cs_stats = {}
    if not skip_cricsheet:
        print("cricsheet...", end="  ", flush=True)
        cs_stats = _cricsheet_stats(name, record_name)

    # Validate cricsheet data — sanity check the stats make sense
    cs_runs    = cs_stats.get("ipl_runs", 0)
    cs_avg     = cs_stats.get("ipl_avg", 0.0)
    cs_sr      = cs_stats.get("ipl_sr", 0.0)
    cs_matches = cs_stats.get("ipl_matches", 0)
    cs_innings = cs_stats.get("ipl_innings", 0)

    # Flag as suspicious if stats look like a wrong player was matched:
    is_bowler = cs_stats.get("ipl_wickets", 0) > 10
    
    cs_suspicious = (
        not is_bowler and cs_innings >= 5 and (
            cs_avg < 12 or
            (cs_sr > 0 and cs_sr < 95) or
            (cs_innings >= 10 and cs_runs < 150)
        )
    )

    # If it's a known risky name or suspicious stats, force Layer 2
    if not skip_cricsheet and (cs_runs > 0 or cs_stats.get("ipl_wickets", 0) > 0) and not cs_suspicious:
        for key, val in cs_stats.items():
            if hasattr(player, key):
                setattr(player, key, val)
        print(f"cricsheet [v]", end="  ", flush=True)
    else:
        if skip_cricsheet:
            print(f"skipping cricsheet (risky name)...", end="  ", flush=True)
        elif cs_suspicious:
            print(f"cricsheet mismatch (stats look off)...", end="  ", flush=True)
        
        # ── Layer 2: Statsguru/Cricinfo Fallback ───────────────────────────
        print(f"statsguru...", end="  ", flush=True)
        sg_stats = _scrape_statsguru(pid)
        if sg_stats:
            for key, val in sg_stats.items():
                if hasattr(player, key):
                    setattr(player, key, val)
            print(f"statsguru [v]", end="  ", flush=True)
        else:
            # ── Layer 3: Cricbuzz fallback ─────────────────────────────────────
            print(f"cricbuzz...", end="  ", flush=True)
            cb_id, cb_name = _get_cricbuzz_id(name)
            if not cb_id:
                cb_id, cb_name = _get_cricbuzz_id(name + " ipl")

            if cb_id:
                player.cricbuzz_id = cb_id
                cb_stats = _scrape_cricbuzz(cb_id, cb_name)
                for key, val in cb_stats.items():
                    if hasattr(player, key):
                        setattr(player, key, val)
                print(f"cricbuzz [v]", end="  ", flush=True)

    player.detect_roles()
    _save(player)
    print(f"done [v]  [{player.ipl_runs}r / {player.ipl_wickets}w / {player.batting_role}]")
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