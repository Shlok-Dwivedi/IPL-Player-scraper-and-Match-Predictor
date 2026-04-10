"""
app.py — Flask API server for IPL Fantasy XI Clash GUI
Run: python app.py
Then open: http://localhost:5000

Endpoints:
  POST /api/load-player     { "input": "virat-kohli-253802" }
  POST /api/analyze         { "xi1": { "name": ..., "players": [...] },
                              "xi2": { "name": ..., "players": [...] } }
  GET  /api/search-player   ?q=virat
"""

import os, sys, json, traceback, glob, atexit
from flask import Flask, request, jsonify, send_from_directory

# Add parent dir to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # ensure cwd = project folder

def _clear_cache():
    """Delete all cached player CSV files when app shuts down."""
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    files = glob.glob(os.path.join(cache_dir, "*.csv"))
    for f in files:
        try:
            os.remove(f)
        except:
            pass
    if files:
        print(f"\n  Cache cleared ({len(files)} files removed)")

atexit.register(_clear_cache)

from scraper import scrape_player, resolve_player_id
from models  import Player, XI, Clash, BattingOrder, BowlingLineup
from models  import PlayerNotFoundError, ScrapeError, InvalidXIError
from analyzer import (xi_batting_stats, xi_bowling_stats, xi_fielding_stats,
                      form_trend, impact_table, batting_order_table, bowling_order_table)

app = Flask(__name__, static_folder=".", static_url_path="")

# ── CORS for local dev ─────────────────────────────────────────────────────────
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route("/", methods=["OPTIONS"])
@app.route("/api/<path:path>", methods=["OPTIONS"])
def options(_=None):
    return "", 204


# ── Helpers ────────────────────────────────────────────────────────────────────

def player_to_json(p: Player) -> dict:
    """Serialize a Player object to a JSON-safe dict for the frontend."""
    return {
        "name":           p.name,
        "cricinfo_id":    p.cricinfo_id,
        "batting_hand":   p.batting_hand,
        "bowling_style":  p.bowling_style,
        "bowling_type":   p.bowling_type,
        "batting_role":   p.batting_role,
        "ipl_matches":    p.ipl_matches,
        "ipl_innings":    p.ipl_innings,
        "ipl_runs":       p.ipl_runs,
        "ipl_highest":    p.ipl_highest,
        "ipl_avg":        p.ipl_avg,
        "ipl_sr":         p.ipl_sr,
        "ipl_fifties":    p.ipl_fifties,
        "ipl_hundreds":   p.ipl_hundreds,
        "ipl_fours":      p.ipl_fours,
        "ipl_sixes":      p.ipl_sixes,
        "ipl_not_outs":   p.ipl_not_outs,
        "ipl_overs":      p.ipl_overs,
        "ipl_wickets":    p.ipl_wickets,
        "ipl_bowl_avg":   p.ipl_bowl_avg,
        "ipl_economy":    p.ipl_economy,
        "ipl_best":       p.ipl_best,
        "recent_scores":  p.recent_scores,
        "batting_impact": p.batting_impact(),
        "bowling_impact": p.bowling_impact(),
        "form_score":     p.form_score(),
        "overall_impact": p.overall_impact(),
        "predicted_runs":    p.predicted_runs(),
        "predicted_wickets": p.predicted_wickets(),
        "ipl_catches":       p.ipl_catches,
        "ipl_stumpings":     p.ipl_stumpings,
        "ipl_run_outs":      p.ipl_run_outs,
        "ipl_dismissals":    p.ipl_dismissals,
        "is_keeper":         p.is_keeper,
        "fielding_impact":   p.fielding_impact(),
    }


def xi_to_json(xi: XI) -> dict:
    """Full XI serialization for the frontend."""
    bat  = xi_batting_stats(xi)
    bowl = xi_bowling_stats(xi)
    form = form_trend(xi)

    batting_order = []
    for p in xi.order.order:
        pd = player_to_json(p)
        pd["batting_position"] = p.batting_position
        pd["batting_overs_quota"] = p.bowling_overs_quota
        batting_order.append(pd)

    bowling_lineup = []
    for d in xi.bowling.lineup:
        p = d["player"]
        bowling_lineup.append({
            **player_to_json(p),
            "overs_quota": d["overs"],
            "is_main_bowler": p.is_main_bowler,
            "bowl_type": d["type"],
            "bowling_impact": d["impact"],
        })

    return {
        "name":             xi.name,
        "players":          [player_to_json(p) for p in xi.players],
        "batting_order":    batting_order,
        "bowling_lineup":   bowling_lineup,
        "predicted_score":  xi.predicted_batting_score(),
        "pred_conceded":    xi.predicted_bowling_defense(),
        "batting_impact":   xi.team_batting_impact(),
        "bowling_impact":   xi.team_bowling_impact(),
        "form":             xi.team_form(),
        "balance_score":    xi.balance_score(),
        "pace_count":       xi.bowling.pace_count(),
        "spin_count":       xi.bowling.spin_count(),
        "allrounders":      [p.name for p in xi.allrounders()],
        "batting_stats":    bat,
        "bowling_stats":    bowl,
        "form_trend":       form,
        "impact_table":     impact_table(xi),
        "fielding_stats":   xi_fielding_stats(xi),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    _clear_cache()
    return send_from_directory(".", "index.html")


@app.route("/api/search-player", methods=["GET"])
def search_player():
    """Quick search — resolve player name/slug to ID + basic info."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "No query"}), 400
    try:
        name, pid = resolve_player_id(q)
        return jsonify({"name": name, "id": pid, "found": True})
    except PlayerNotFoundError as e:
        return jsonify({"found": False, "error": str(e)}), 404


@app.route("/api/load-player", methods=["POST"])
def load_player():
    """
    Load a single player's stats (scrape or cache).
    Body: { "input": "virat-kohli-253802", "force": false }
    """
    data  = request.get_json() or {}
    raw   = data.get("input", "").strip()
    force = data.get("force", False)

    if not raw:
        return jsonify({"error": "No player input provided"}), 400

    try:
        player = scrape_player(raw, force=force)
        return jsonify({"success": True, "player": player_to_json(player)})
    except PlayerNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except ScrapeError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Full XI vs XI analysis.
    Body: {
      "xi1": { "name": "Team A", "players": ["virat-kohli-253802", ...] },
      "xi2": { "name": "Team B", "players": [...] },
      "force": false
    }
    """
    data  = request.get_json() or {}
    force = data.get("force", False)

    xi1_data = data.get("xi1", {})
    xi2_data = data.get("xi2", {})

    if not xi1_data or not xi2_data:
        return jsonify({"error": "Both xi1 and xi2 are required"}), 400

    errors = []
    players1, players2 = [], []

    for raw in xi1_data.get("players", []):
        try:
            players1.append(scrape_player(raw, force=force))
        except (PlayerNotFoundError, ScrapeError) as e:
            errors.append({"input": raw, "error": str(e)})

    for raw in xi2_data.get("players", []):
        try:
            players2.append(scrape_player(raw, force=force))
        except (PlayerNotFoundError, ScrapeError) as e:
            errors.append({"input": raw, "error": str(e)})

    if len(players1) != 11 or len(players2) != 11:
        return jsonify({
            "success": False,
            "error": f"Need 11 players each. Got {len(players1)} and {len(players2)}.",
            "player_errors": errors,
        }), 422

    try:
        xi1   = XI(xi1_data.get("name", "Team A"), players1)
        xi2   = XI(xi2_data.get("name", "Team B"), players2)
        clash = Clash(xi1, xi2)
        result = clash.predict()

        return jsonify({
            "success": True,
            "xi1":     xi_to_json(xi1),
            "xi2":     xi_to_json(xi2),
            "result":  result,
            "errors":  errors,
        })
    except InvalidXIError as e:
        return jsonify({"success": False, "error": str(e)}), 422
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("\n  IPL Fantasy XI Clash — Web UI")
    print("  Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)