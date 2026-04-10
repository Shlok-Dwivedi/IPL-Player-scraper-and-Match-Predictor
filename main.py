"""
main.py — IPL Fantasy XI Clash Analyzer
Entry point — interactive CLI or --demo mode.

Usage:
  python main.py              # interactive
  python main.py --demo       # hardcoded demo XIs
  python main.py --offline    # use cached CSVs, no scraping
"""

import os, sys, argparse
from models import XI, Clash, InvalidXIError, PlayerNotFoundError
from scraper import scrape_xi
from analyzer import generate_report, xi_batting_stats, xi_bowling_stats, form_trend
from visualizer import generate_all_charts

REPORT_PATH = os.path.join(os.path.dirname(__file__), "data", "report.txt")

DEMO_A = [
    "virat-kohli-253802", "rohit-sharma-34102", "kl-rahul-422108",
    "suryakumar-yadav-446507", "hardik-pandya-625383", "ravindra-jadeja-234675",
    "ms-dhoni-28081", "axar-patel-554694", "jasprit-bumrah-625371",
    "yuzvendra-chahal-559235", "deepak-chahar-661540",
]
DEMO_B = [
    "yashasvi-jaiswal-1207652", "jos-buttler-308967", "sanju-samson-442710",
    "riyan-parag-1207690", "shimron-hetmyer-719671", "andre-russell-300797",
    "rashid-khan-793463", "sunil-narine-321777", "trent-boult-327065",
    "avesh-khan-1131538", "kuldeep-yadav-594284",
]


def banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║     🏏  IPL FANTASY XI CLASH ANALYZER  🏏               ║
║     Enter any 11 players — batting order + bowling       ║
║     lineup auto-arranged from real IPL stats             ║
╚══════════════════════════════════════════════════════════╝
""")


def instructions():
    print("""  How to enter players:
  ──────────────────────────────────────────────────────────
  • Name only     :  Virat Kohli
  • URL slug      :  virat-kohli-253802
  • Numeric ID    :  253802  (from ESPNCricinfo URL)
  • Full URL      :  https://www.espncricinfo.com/cricketers/virat-kohli-253802
  ──────────────────────────────────────────────────────────
""")


def get_xi_input(label: str) -> tuple[str, list[str]]:
    print(f"\n  {'═'*54}")
    print(f"  {label}")
    print(f"  {'═'*54}")
    name = input("\n  Team name: ").strip() or label
    print(f"\n  Enter 11 players for '{name}':")
    instructions()
    players = []
    for i in range(1, 12):
        while True:
            raw = input(f"    Player {i:>2}: ").strip()
            if raw:
                players.append(raw)
                break
    return name, players


def print_summary(xi: XI):
    bat  = xi_batting_stats(xi)
    bowl = xi_bowling_stats(xi)
    form = form_trend(xi)
    print(f"""
  ┌─ {xi.name} {'─'*max(0,46-len(xi.name))}┐
  │  Pred Score : {xi.predicted_batting_score():.0f} runs   Pred Concede: {xi.predicted_bowling_defense():.0f}
  │  Bat Impact : {xi.team_batting_impact():.1f}   Bowl Impact: {xi.team_bowling_impact():.1f}
  │  Balance    : {xi.balance_score():.0f}/100   Form: {form['trend']} ({form['avg_form']})
  │  Pace/Spin  : {bowl['pace_bowlers']}/{bowl['spin_bowlers']}   All-rounders: {len(xi.allrounders())}
  └{'─'*50}┘""")
    xi.order.display(xi.name)
    xi.bowling.display(xi.name)


def print_result(result: dict):
    s1  = result["xi1"]["scores"]
    s2  = result["xi2"]["scores"]
    bar = 26
    b1  = int(s1["total"] / max(s1["total"], s2["total"]) * bar)
    b2  = int(s2["total"] / max(s1["total"], s2["total"]) * bar)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║                    MATCH PREDICTION                     ║
╠══════════════════════════════════════════════════════════╣
║  {result['xi1']['name'][:24]:<24}  Score: {s1['pred_score']:>5.0f}           ║
║  {'█'*b1:<26}                              ║
║  {'█'*b2:<26}                              ║
║  {result['xi2']['name'][:24]:<24}  Score: {s2['pred_score']:>5.0f}           ║
║                                                          ║
║  Winner     : {result['winner']:<42}║
║  Confidence : {result['confidence']}%                                     ║
╚══════════════════════════════════════════════════════════╝""")


def run(xi1_name, xi1_in, xi2_name, xi2_in, offline=False):
    force = not offline
    p1 = scrape_xi(xi1_in, xi1_name, force=force)
    p2 = scrape_xi(xi2_in, xi2_name, force=force)

    if len(p1) != 11: raise InvalidXIError(len(p1))
    if len(p2) != 11: raise InvalidXIError(len(p2))

    xi1 = XI(xi1_name, p1)
    xi2 = XI(xi2_name, p2)

    print_summary(xi1)
    print_summary(xi2)

    result = Clash(xi1, xi2).predict()
    print_result(result)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(generate_report(xi1, xi2, result))
    print(f"\n  Report → {REPORT_PATH}")

    try:
        generate_all_charts(xi1, xi2, result)
    except Exception as e:
        print(f"  [WARN] Charts: {e}")

    print("\n  Done!\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--demo",    action="store_true")
    args = parser.parse_args()
    banner()

    if args.demo:
        run("Team Alpha", DEMO_A, "Team Beta", DEMO_B, offline=args.offline)
        return

    try:
        n1, p1 = get_xi_input("TEAM A — Build Your XI")
        n2, p2 = get_xi_input("TEAM B — Build Your XI")
        run(n1, p1, n2, p2, offline=args.offline)
    except (KeyboardInterrupt, EOFError):
        print("\n  Bye.")
    except InvalidXIError as e:
        print(f"\n  Error: {e}")


if __name__ == "__main__":
    main()
