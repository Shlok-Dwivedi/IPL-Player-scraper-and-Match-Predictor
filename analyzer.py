"""
analyzer.py — NumPy Scientific Computation + Functional Programming
Concepts  : numpy, map / filter / reduce, list comprehensions
"""

import numpy as np
from functools import reduce
from models import Player, XI


def xi_batting_stats(xi: XI) -> dict:
    runs = np.array([p.ipl_runs for p in xi.players], dtype=float)
    avgs = np.array([p.ipl_avg  for p in xi.players], dtype=float)
    srs  = np.array([p.ipl_sr   for p in xi.players], dtype=float)
    r    = runs[runs > 0]; a = avgs[avgs > 0]; s = srs[srs > 0]
    return {
        "total_runs":  int(np.sum(runs)),
        "mean_runs":   round(float(np.mean(r)) if len(r) else 0, 1),
        "median_runs": round(float(np.median(r)) if len(r) else 0, 1),
        "std_runs":    round(float(np.std(r)) if len(r) else 0, 1),
        "max_runs":    int(np.max(runs)),
        "mean_avg":    round(float(np.mean(a)) if len(a) else 0, 1),
        "mean_sr":     round(float(np.mean(s)) if len(s) else 0, 1),
        "total_sixes": int(np.sum([p.ipl_sixes for p in xi.players])),
    }


def xi_bowling_stats(xi: XI) -> dict:
    wkts = np.array([p.ipl_wickets for p in xi.players], dtype=float)
    ecos  = np.array([p.ipl_economy for p in xi.players], dtype=float)
    w = wkts[wkts > 0]; e = ecos[ecos > 0]
    return {
        "total_wickets": int(np.sum(wkts)),
        "mean_wickets":  round(float(np.mean(w)) if len(w) else 0, 1),
        "max_wickets":   int(np.max(wkts)),
        "mean_economy":  round(float(np.mean(e)) if len(e) else 0, 1),
        "best_economy":  round(float(np.min(e)) if len(e) else 0, 1),
        "pace_bowlers":  xi.bowling.pace_count(),
        "spin_bowlers":  xi.bowling.spin_count(),
    }


def xi_fielding_stats(xi: XI) -> dict:
    """NumPy fielding stats across the XI."""
    import numpy as np
    catches   = np.array([p.ipl_catches    for p in xi.players], dtype=float)
    stumpings = np.array([p.ipl_stumpings  for p in xi.players], dtype=float)
    run_outs  = np.array([p.ipl_run_outs   for p in xi.players], dtype=float)
    dismissals= np.array([p.ipl_dismissals for p in xi.players], dtype=float)
    keepers   = [p for p in xi.players if p.is_keeper]
    return {
        "total_catches":    int(np.sum(catches)),
        "total_stumpings":  int(np.sum(stumpings)),
        "total_run_outs":   int(np.sum(run_outs)),
        "total_dismissals": int(np.sum(dismissals)),
        "keeper":           keepers[0].name if keepers else "None",
        "best_fielder":     max(xi.players, key=lambda p: p.ipl_dismissals).name,
    }


def form_trend(xi: XI) -> dict:
    scores = np.array([p.form_score() for p in xi.players])
    avg = float(np.mean(scores))
    return {
        "avg_form":    round(avg, 1),
        "std_form":    round(float(np.std(scores)), 1),
        "hot_players": int(np.sum(scores > 62)),
        "cold_players":int(np.sum(scores < 38)),
        "trend": "Hot" if avg > 62 else ("Cold" if avg < 45 else "Neutral"),
    }


# ── Functional programming ────────────────────────────────────────────────────

def impact_players(xi: XI, threshold: float = 35.0) -> list:
    return list(filter(lambda p: p.overall_impact() > threshold, xi.players))


def player_names(xi: XI) -> list[str]:
    return list(map(lambda p: p.name, xi.players))


def total_sixes(xi: XI) -> int:
    return reduce(lambda acc, p: acc + p.ipl_sixes, xi.players, 0)


def impact_table(xi: XI) -> list[dict]:
    rated = map(lambda p: {
        "name":     p.name,
        "role":     p.batting_role,
        "bowl":     p.bowling_type,
        "batting":  p.batting_impact(),
        "bowling":  p.bowling_impact(),
        "form":     p.form_score(),
        "fielding": p.fielding_impact(),
        "overall":  p.overall_impact(),
        "is_keeper":p.is_keeper,
        "dismissals":p.ipl_dismissals,
    }, xi.players)
    return sorted(rated, key=lambda d: d["overall"], reverse=True)


def batting_order_table(xi: XI) -> list[dict]:
    return [
        {
            "pos":  p.batting_position,
            "name": p.name,
            "role": p.batting_role,
            "hand": "L" if "left" in p.batting_hand.lower() else "R",
            "avg":  p.ipl_avg,
            "sr":   p.ipl_sr,
            "form": p.form_score(),
            "pred": p.predicted_runs(),
        }
        for p in xi.order.order
    ]


def bowling_order_table(xi: XI) -> list[dict]:
    return [
        {
            "name":    d["player"].name,
            "type":    d["type"],
            "overs":   d["overs"],
            "wickets": d["player"].ipl_wickets,
            "economy": d["player"].ipl_economy,
            "best":    d["player"].ipl_best,
            "impact":  d["impact"],
            "pred_w":  d["player"].predicted_wickets(),
        }
        for d in xi.bowling.lineup
    ]


def generate_report(xi1: XI, xi2: XI, result: dict) -> str:
    sep = "=" * 64
    lines = [sep, "  IPL FANTASY XI CLASH — REPORT", f"  {xi1.name}  vs  {xi2.name}", sep, ""]

    for xi in [xi1, xi2]:
        bat  = xi_batting_stats(xi)
        bowl = xi_bowling_stats(xi)
        form = form_trend(xi)

        lines += [
            f"── {xi.name} {'─'*(54-len(xi.name))}",
            f"  Predicted Score : {xi.predicted_batting_score():.0f}",
            f"  Concedes ~       : {xi.predicted_bowling_defense():.0f}",
            f"  Balance Score   : {xi.balance_score()}/100",
            f"  Form Trend      : {form['trend']} (avg {form['avg_form']})",
            f"  Pace / Spin     : {bowl['pace_bowlers']} / {bowl['spin_bowlers']}",
            "", "  Batting Order:",
        ]
        for d in batting_order_table(xi):
            lines.append(
                f"    {d['pos']:>2}. {d['name']:<22} {d['role']:<14}"
                f"  avg={d['avg']:.1f}  sr={d['sr']:.1f}  pred={d['pred']:.0f}r"
            )
        lines += ["", "  Bowling Lineup:"]
        for d in bowling_order_table(xi):
            lines.append(
                f"    {d['name']:<22} {d['type']:<8}  {d['overs']}ov  "
                f"{d['wickets']}w  eco={d['economy']:.1f}  best={d['best']}"
            )
        lines.append("")

    lines += [
        sep, "  PREDICTION", sep,
        f"  {xi1.name:<28}  {result['xi1']['scores']['pred_score']:.0f} runs",
        f"  {xi2.name:<28}  {result['xi2']['scores']['pred_score']:.0f} runs",
        "",
        f"  Winner     : {result['winner']}",
        f"  Confidence : {result['confidence']}%",
        sep,
    ]
    return "\n".join(lines)
