"""
models.py — OOP Design with proper batting positions and bowling roles
Concepts : Object-Oriented System Design, Custom Exception Handling
"""

# ─────────────────────────────────────────────
# CUSTOM EXCEPTIONS
# ─────────────────────────────────────────────

class IPLClashError(Exception):
    pass

class PlayerNotFoundError(IPLClashError):
    def __init__(self, name: str):
        super().__init__(
            f"Could not find '{name}'.\n"
            f"  Use full name ('Virat Kohli'), slug ('virat-kohli-253802'),\n"
            f"  or numeric ID ('253802')."
        )

class ScrapeError(IPLClashError):
    def __init__(self, player: str, reason: str):
        super().__init__(f"Failed to scrape '{player}': {reason}")

class InvalidXIError(IPLClashError):
    def __init__(self, count: int):
        super().__init__(f"XI needs exactly 11 players. You gave {count}.")

class BowlingShortageError(IPLClashError):
    def __init__(self, name: str, have: int):
        super().__init__(
            f"'{name}' only has {have} players who can bowl. "
            f"A T20 XI needs at least 5 bowlers."
        )


# ─────────────────────────────────────────────
# ENUMS / CONSTANTS
# ─────────────────────────────────────────────

# Batting position slots
BAT_POSITIONS = {
    "Opener":        (1, 2),
    "Top Order":     (3, 3),
    "Upper Middle":  (4, 4),
    "Middle Order":  (5, 6),
    "Lower Middle":  (7, 7),
    "Finisher":      (6, 8),
    "All-rounder":   (5, 8),
    "Tail":          (9, 11),
    "Bowler":        (9, 11),
}

# Bowling type tags
BOWL_TYPES = ["Fast", "Fast-medium", "Medium-fast", "Medium",
              "Off-break", "Left-arm orthodox", "Leg-break", "Googly",
              "Slow left-arm", "Left-arm fast"]

PACE_TYPES  = {"Fast", "Fast-medium", "Medium-fast", "Medium"}
SPIN_TYPES  = {"Off-break", "Left-arm orthodox", "Leg-break",
               "Googly", "Slow left-arm"}


# ─────────────────────────────────────────────
# PLAYER
# ─────────────────────────────────────────────

class Player:
    """
    A cricket player with IPL stats, explicit batting position preference,
    and bowling type (pace / spin / none).
    """

    def __init__(self, name: str, cricinfo_id: int):
        self.name        = name
        self.cricinfo_id = cricinfo_id
        self.record_name = ""
        self.cricbuzz_id = ""

        # ── Batting stats (IPL) ──
        self.ipl_matches   = 0
        self.ipl_innings   = 0
        self.ipl_runs      = 0
        self.ipl_highest   = 0
        self.ipl_avg       = 0.0
        self.ipl_sr        = 0.0
        self.ipl_fifties   = 0
        self.ipl_hundreds  = 0
        self.ipl_fours     = 0
        self.ipl_sixes     = 0
        self.ipl_not_outs  = 0
        self.ipl_ducks     = 0

        # ── Bowling stats (IPL) ──
        self.ipl_overs     = 0.0
        self.ipl_wickets   = 0
        self.ipl_bowl_avg  = 0.0
        self.ipl_economy   = 0.0
        self.ipl_best      = "0/0"
        self.ipl_four_fers = 0
        self.ipl_sr_bowl   = 0.0   # bowling strike rate

        # ── Fielding stats (IPL) ──
        self.ipl_catches    = 0    # catches taken (outfield + close-in)
        self.ipl_stumpings  = 0    # stumpings (keeper only)
        self.ipl_run_outs   = 0    # run outs contributed
        self.ipl_dismissals = 0    # total: catches + stumpings + run outs
        self.is_keeper      = False  # True if stumpings > 0

        # ── Bowling type (scraped from profile) ──
        # e.g. "Right-arm fast", "Slow left-arm orthodox", "Leg-break googly"
        self.bowling_style   = ""
        self.bowling_type    = "None"   # "Pace" | "Spin" | "None"

        # ── Batting hand ──
        self.batting_hand    = ""   # "Right-hand bat" | "Left-hand bat"

        # ── Recent form: last 5 IPL innings ──
        self.recent_scores: list[int] = []

        # ── Assigned by BattingOrder ──
        self.batting_position   = 0    # 1–11
        self.batting_role       = ""   # "Opener" | "Top Order" | etc.

        # ── Assigned by BowlingLineup ──
        self.bowling_overs_quota = 0   # 0, 2, 3, or 4 overs per innings
        self.is_main_bowler      = False

    # ── Impact scoring ────────────────────────────────────────────────────────

    def batting_impact(self) -> float:
        """Composite batting impact 0–100. SR 35% + avg 30% + volume 20% + boundaries 15%"""
        if self.ipl_innings == 0:
            return 0.0
        sr_s   = min(self.ipl_sr  / 185, 1.0) * 35
        avg_s  = min(self.ipl_avg / 55,  1.0) * 30
        vol_s  = min(self.ipl_runs / 600, 1.0) * 20
        bdry_s = min((self.ipl_fours + self.ipl_sixes) / 70, 1.0) * 15
        return round(sr_s + avg_s + vol_s + bdry_s, 2)

    def bowling_impact(self) -> float:
        """Composite bowling impact 0–100. Wickets 40% + economy 35% + avg 25%"""
        if self.ipl_overs == 0 and self.ipl_wickets == 0:
            return 0.0
        wkt_s  = min(self.ipl_wickets / 25, 1.0) * 40
        eco_s  = max(0, (12 - self.ipl_economy) / 12) * 35 if self.ipl_economy > 0 else 0
        avg_s  = max(0, (60 - self.ipl_bowl_avg) / 60) * 25 if self.ipl_bowl_avg > 0 else 0
        return round(wkt_s + eco_s + avg_s, 2)

    def form_score(self) -> float:
        """Weighted recent form score 0–100 (most recent innings weighted highest)."""
        if not self.recent_scores:
            return 50.0
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]
        total = sum(
            min(s / 80, 1.0) * 100 * weights[i]
            for i, s in enumerate(self.recent_scores[:5])
        )
        return round(total, 2)

    def fielding_impact(self) -> float:
        """Fielding impact 0–100. Dismissals 60% + keeper bonus 40%"""
        if self.ipl_matches == 0:
            return 0.0
        # dismissals per match (normalized: 1.0 dismissal/match = elite)
        dis_rate = self.ipl_dismissals / max(self.ipl_matches, 1)
        dis_score = min(dis_rate / 1.0, 1.0) * 60
        # keeper bonus — stumpings are hard, reward them
        keep_score = min(self.ipl_stumpings / 30, 1.0) * 40 if self.is_keeper else 0
        return round(dis_score + keep_score, 2)

    def overall_impact(self) -> float:
        """Batting 45% + bowling 28% + form 18% + fielding 9%"""
        return round(
            self.batting_impact()  * 0.45 +
            self.bowling_impact()  * 0.28 +
            self.form_score()      * 0.18 +
            self.fielding_impact() * 0.09,
            2
        )

    def predicted_runs(self) -> float:
        """
        Expected runs contribution in one T20 innings.

        Logic:
        - In T20, a batter faces ~20 balls on average (200 balls / 10 wickets)
        - Expected runs = balls_faced × (sr/100)
        - We estimate balls faced from position probability × 20
        - Adjusted by form multiplier
        - Top order bats more balls, tail barely bats
        """
        if self.ipl_avg == 0 or self.ipl_sr == 0:
            return 4.0
        # avg balls faced per innings ≈ avg × 100/sr
        avg_balls = self.ipl_avg * (100 / max(self.ipl_sr, 50))
        # cap at 60 balls (T20 maximum realistic for any batter)
        avg_balls = min(avg_balls, 60)
        # predicted runs = balls × (SR/100)
        pred = avg_balls * (self.ipl_sr / 100)
        # form adjustment: 0.75 (cold) to 1.25 (hot)
        form_mult = 0.75 + (self.form_score() / 100) * 0.50
        return round(min(pred * form_mult, 80), 1)

    def predicted_wickets(self) -> float:
        """Expected wickets per 4-over spell."""
        if self.ipl_overs == 0:
            return 0.0
        wkt_rate = self.ipl_wickets / max(self.ipl_overs, 1)
        return round(min(wkt_rate * 4, 3.5), 2)

    def predicted_runs_conceded(self, overs: float = 4.0) -> float:
        """Expected runs conceded in `overs` overs."""
        if self.ipl_economy == 0:
            return overs * 9.0  # default economy
        return round(self.ipl_economy * overs, 1)

    # ── Role detection ────────────────────────────────────────────────────────

    def detect_roles(self):
        """
        Auto-detect batting role, bowling type, and keeper status from stats.
        Called after stats are loaded.
        """
        self.is_keeper = self.ipl_stumpings > 0
        self.ipl_dismissals = self.ipl_catches + self.ipl_stumpings + self.ipl_run_outs
        self._detect_batting_role()
        self._detect_bowling_type()

    def _detect_batting_role(self):
        bat  = self.batting_impact()
        bowl = self.bowling_impact()

        if self.ipl_innings == 0:
            if bowl > 15:
                self.batting_role = "Bowler"
            else:
                self.batting_role = "Batsman"
            return

        # ── Simple 3-way Role Logic ──
        # All-rounders: Significant impact in both departments (>25 score)
        if bat > 25 and bowl > 25:
            self.batting_role = "All-rounder"
        # Batsmen: Superior batting impact compared to bowling
        elif bat >= bowl:
            self.batting_role = "Batsman"
        # Bowlers: Superior bowling impact compared to batting
        else:
            self.batting_role = "Bowler"

    def _detect_bowling_type(self):
        """Determine Pace / Spin / None from bowling_style string."""
        style = self.bowling_style.lower()
        if not style or style in ("", "none", "-"):
            # Infer from economy: spinners typically 7–8.5, pacers 8–10
            if self.ipl_economy > 0:
                self.bowling_type = "Pace" if self.ipl_economy > 8.8 else "Spin"
            else:
                self.bowling_type = "None"
            return

        pace_keywords = ["fast", "medium", "seam", "swing", "pace"]
        spin_keywords = ["off", "leg", "break", "spin", "slow", "orthodox",
                         "googly", "left-arm spin", "chinaman"]

        if any(k in style for k in pace_keywords):
            self.bowling_type = "Pace"
        elif any(k in style for k in spin_keywords):
            self.bowling_type = "Spin"
        else:
            self.bowling_type = "None"

    def can_bowl(self) -> bool:
        return self.ipl_overs > 0 or self.ipl_wickets > 0

    def is_allrounder(self) -> bool:
        return self.batting_impact() > 25 and self.bowling_impact() > 20

    def is_pure_bowler(self) -> bool:
        return self.batting_impact() < 12 and self.bowling_impact() > 15

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":            self.name,
            "cricinfo_id":     self.cricinfo_id,
            "batting_hand":    self.batting_hand,
            "bowling_style":   self.bowling_style,
            "bowling_type":    self.bowling_type,
            "batting_role":    self.batting_role,
            "ipl_matches":     self.ipl_matches,
            "ipl_innings":     self.ipl_innings,
            "ipl_runs":        self.ipl_runs,
            "ipl_highest":     self.ipl_highest,
            "ipl_avg":         self.ipl_avg,
            "ipl_sr":          self.ipl_sr,
            "ipl_fifties":     self.ipl_fifties,
            "ipl_hundreds":    self.ipl_hundreds,
            "ipl_fours":       self.ipl_fours,
            "ipl_sixes":       self.ipl_sixes,
            "ipl_not_outs":    self.ipl_not_outs,
            "ipl_ducks":       self.ipl_ducks,
            "ipl_overs":       self.ipl_overs,
            "ipl_wickets":     self.ipl_wickets,
            "ipl_bowl_avg":    self.ipl_bowl_avg,
            "ipl_economy":     self.ipl_economy,
            "ipl_best":        self.ipl_best,
            "ipl_four_fers":   self.ipl_four_fers,
            "ipl_sr_bowl":     self.ipl_sr_bowl,
            "ipl_catches":     self.ipl_catches,
            "ipl_stumpings":   self.ipl_stumpings,
            "ipl_run_outs":    self.ipl_run_outs,
            "ipl_dismissals":  self.ipl_dismissals,
            "is_keeper":       self.is_keeper,
            "recent_scores":   ",".join(map(str, self.recent_scores)),
            "fielding_impact": self.fielding_impact(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        p = cls(d["name"], int(d.get("cricinfo_id", 0)))
        for field in ["batting_hand", "bowling_style", "bowling_type", "batting_role"]:
            setattr(p, field, d.get(field, ""))
        for field in ["ipl_matches", "ipl_innings", "ipl_runs", "ipl_highest",
                      "ipl_fifties", "ipl_hundreds", "ipl_fours", "ipl_sixes",
                      "ipl_not_outs", "ipl_ducks", "ipl_wickets", "ipl_four_fers"]:
            setattr(p, field, int(d.get(field, 0)))
        for field in ["ipl_avg", "ipl_sr", "ipl_overs", "ipl_bowl_avg",
                      "ipl_economy", "ipl_sr_bowl"]:
            setattr(p, field, float(d.get(field, 0)))
        p.ipl_best      = d.get("ipl_best", "0/0")
        p.ipl_catches   = int(d.get("ipl_catches",   0))
        p.ipl_stumpings = int(d.get("ipl_stumpings", 0))
        p.ipl_run_outs  = int(d.get("ipl_run_outs",  0))
        p.ipl_dismissals= int(d.get("ipl_dismissals",0))
        p.is_keeper     = str(d.get("is_keeper", "False")).lower() == "true"
        raw = d.get("recent_scores", "")
        p.recent_scores = [int(x) for x in raw.split(",") if x.strip().isdigit()]
        return p

    def __repr__(self):
        return f"Player({self.name!r}, pos={self.batting_position}, role={self.batting_role!r}, bowl={self.bowling_type!r})"


# ─────────────────────────────────────────────
# BATTING ORDER
# ─────────────────────────────────────────────

class BattingOrder:
    """
    Arranges 11 players into an optimal batting order.

    Logic:
    - Slot 1-2:  Openers (high SR + decent avg)
    - Slot 3:    Best avg batsman (anchor)
    - Slot 4-5:  Strong middle order (avg + SR balance)
    - Slot 6-7:  Finishers / all-rounders (SR > avg)
    - Slot 8-9:  Lower middle / bowling all-rounders
    - Slot 10-11: Tail enders / pure bowlers
    """

    # Per-position weighting: (avg_weight, sr_weight, form_weight)
    WEIGHTS = {
        1:  (0.25, 0.55, 0.20),
        2:  (0.25, 0.55, 0.20),
        3:  (0.55, 0.25, 0.20),
        4:  (0.50, 0.30, 0.20),
        5:  (0.40, 0.38, 0.22),
        6:  (0.28, 0.48, 0.24),
        7:  (0.22, 0.50, 0.28),
        8:  (0.18, 0.45, 0.37),
        9:  (0.12, 0.38, 0.50),
        10: (0.10, 0.30, 0.60),
        11: (0.08, 0.25, 0.67),
    }

    # Probability of each position actually batting (affects predicted total)
    # Probability each position gets to bat in a T20 innings
    # Top 6 almost always bat; 7-8 bat 60-70%; 9-11 rarely
    BAT_PROBABILITY = [1.0, 1.0, 0.98, 0.95, 0.90,
                       0.82, 0.68, 0.52, 0.36, 0.22, 0.10]

    def __init__(self, players: list):
        if len(players) != 11:
            raise InvalidXIError(len(players))
        self.players = players
        self.order: list = []
        self._arrange()

    def _pos_score(self, player, pos: int) -> float:
        wa, ws, wf = self.WEIGHTS.get(pos, (0.33, 0.33, 0.34))
        avg_n  = min(player.ipl_avg / 55,  1.0) * 100
        sr_n   = min(player.ipl_sr  / 200, 1.0) * 100
        form_n = player.form_score()
        return wa * avg_n + ws * sr_n + wf * form_n

    def _arrange(self):
        """Preserve exact user input order. Detect roles for display only."""
        for p in self.players:
            if not p.batting_role:
                p.detect_roles()
        self.order = list(self.players[:11])
        for i, p in enumerate(self.order):
            p.batting_position = i + 1

    def predicted_total(self) -> float:
        """
        Predict a T20 innings total.
        Each position has a probability of actually getting to bat.
        Total is capped to realistic T20 range (90-220).
        """
        raw = sum(
            p.predicted_runs() * self.BAT_PROBABILITY[i]
            for i, p in enumerate(self.order)
        )
        # T20 realistic range: 90 minimum, 230 maximum
        return round(max(90.0, min(raw, 230.0)), 1)

    def display(self, team_name: str = ""):
        title = f"BATTING ORDER — {team_name}" if team_name else "BATTING ORDER"
        print(f"\n  {'─'*65}")
        print(f"  {title}")
        print(f"  {'─'*65}")
        print(f"  {'#':<3} {'Player':<22} {'Role':<14} {'Bat':>3} {'Avg':>5} {'SR':>6} {'Form':>5} {'Pred':>5}")
        print(f"  {'─'*65}")
        for p in self.order:
            hand = "L" if "left" in p.batting_hand.lower() else "R"
            print(
                f"  {p.batting_position:<3} "
                f"{p.name:<22} "
                f"{p.batting_role:<14} "
                f"{hand:>3} "
                f"{p.ipl_avg:>5.1f} "
                f"{p.ipl_sr:>6.1f} "
                f"{p.form_score():>5.1f} "
                f"{p.predicted_runs():>5.1f}"
            )
        print(f"  {'─'*65}")
        print(f"  Predicted Score: {self.predicted_total():.0f} runs")


# ─────────────────────────────────────────────
# BOWLING LINEUP
# ─────────────────────────────────────────────

class BowlingLineup:
    """
    Assigns bowling overs quota to each player in a T20 XI.

    Rules:
    - Each player can bowl max 4 overs
    - Total 20 overs to be distributed
    - Pure bowlers get 4 overs each
    - All-rounders get 3-4 overs
    - Part-timers get 1-2 overs
    - Batsmen who can't bowl get 0 overs
    - Must fill all 20 overs with at least 5 bowlers
    """

    def __init__(self, players: list):
        self.players = players
        self.lineup: list[dict] = []
        self._assign()

    def _assign(self):
        bowlers = sorted(
            [p for p in self.players if p.can_bowl()],
            key=lambda p: p.bowling_impact(), reverse=True
        )
        non_bowlers = [p for p in self.players if not p.can_bowl()]

        quotas = {}
        overs_left = 20

        # Main bowlers (top 5 by bowling impact) — 4 overs each
        main = bowlers[:5]
        for p in main:
            q = min(4, overs_left)
            quotas[p.name] = q
            overs_left -= q
            p.is_main_bowler = True

        # Support bowlers — distribute remaining overs
        support = bowlers[5:]
        for p in support:
            if overs_left <= 0:
                quotas[p.name] = 0
            else:
                q = min(3, overs_left)
                quotas[p.name] = q
                overs_left -= q

        # Assign to part-timers if still overs left (shouldn't happen normally)
        if overs_left > 0:
            part_timers = sorted(non_bowlers, key=lambda p: p.batting_impact())
            for p in part_timers:
                if overs_left <= 0:
                    break
                q = min(2, overs_left)
                quotas[p.name] = q
                overs_left -= q

        # Non-bowlers get 0
        for p in non_bowlers:
            if p.name not in quotas:
                quotas[p.name] = 0

        # Assign quotas and build lineup — ALL 11 players included
        for p in self.players:
            q = quotas.get(p.name, 0)
            p.bowling_overs_quota = q
            self.lineup.append({
                "player":         p,
                "overs":          q,
                "overs_quota":    q,
                "is_main_bowler": getattr(p, "is_main_bowler", False),
                "type":           p.bowling_type,
                "impact":         p.bowling_impact(),
                "economy":        p.ipl_economy,
                "wickets":        p.ipl_wickets,
                "best":           p.ipl_best,
            })

        # Sort: real bowlers first (by impact), then part-timers, then pure batters
        self.lineup.sort(key=lambda d: (
            0 if d["type"] in ("Pace","Spin") else 1,
            -d["impact"]
        ))

    def pace_count(self) -> int:
        return sum(1 for d in self.lineup if d["type"] == "Pace")

    def spin_count(self) -> int:
        return sum(1 for d in self.lineup if d["type"] == "Spin")

    def predicted_wickets(self) -> float:
        """Total predicted wickets across all bowlers."""
        return round(sum(
            d["player"].predicted_wickets()
            for d in self.lineup
        ), 1)

    def predicted_runs_conceded(self) -> float:
        """Total predicted runs conceded in 20 overs."""
        return round(sum(
            d["player"].predicted_runs_conceded(d["overs"])
            for d in self.lineup
        ), 1)

    def display(self, team_name: str = ""):
        title = f"BOWLING LINEUP — {team_name}" if team_name else "BOWLING LINEUP"
        print(f"\n  {'─'*65}")
        print(f"  {title}")
        print(f"  {'─'*65}")
        print(f"  {'Player':<22} {'Type':<8} {'Overs':>5} {'Wkts':>5} {'Eco':>5} {'Best':>8} {'Impact':>7}")
        print(f"  {'─'*65}")
        for d in self.lineup:
            p = d["player"]
            marker = " *" if p.is_main_bowler else "  "
            print(
                f"  {p.name:<22}"
                f"{d['type']:<8}"
                f"{d['overs']:>5}"
                f"{p.ipl_wickets:>5}"
                f"{p.ipl_economy:>6.1f}"
                f"{p.ipl_best:>9}"
                f"{d['impact']:>8.1f}"
                f"{marker}"
            )
        print(f"  {'─'*65}")
        print(f"  Pace: {self.pace_count()}  Spin: {self.spin_count()}  "
              f"| Pred Wkts: {self.predicted_wickets():.1f}  "
              f"| Pred Conceded: {self.predicted_runs_conceded():.0f}")
        print(f"  * = Main bowler (4 overs)")


# ─────────────────────────────────────────────
# XI
# ─────────────────────────────────────────────

class XI:
    """A complete fantasy XI — batting order + bowling lineup."""

    def __init__(self, name: str, players: list):
        if len(players) != 11:
            raise InvalidXIError(len(players))
        self.name    = name
        self.players = players
        self.order   = BattingOrder(players)
        self.bowling = BowlingLineup(players)

    def predicted_batting_score(self) -> float:
        return self.order.predicted_total()

    def predicted_bowling_defense(self) -> float:
        """Lower is better — predicted runs conceded."""
        return self.bowling.predicted_runs_conceded()

    def team_batting_impact(self) -> float:
        return round(sum(p.batting_impact() for p in self.players) / 11, 2)

    def team_bowling_impact(self) -> float:
        return round(sum(p.bowling_impact() for p in self.players) / 11, 2)

    def team_form(self) -> float:
        return round(sum(p.form_score() for p in self.players) / 11, 2)

    def allrounders(self) -> list:
        return [p for p in self.players if p.is_allrounder()]

    def balance_score(self) -> float:
        """
        How well-balanced is this XI?
        Rewards having both pace + spin, enough bowlers, allrounders.
        """
        pace  = self.bowling.pace_count()
        spin  = self.bowling.spin_count()
        ar    = len(self.allrounders())
        bowlers = len([p for p in self.players if p.can_bowl()])

        pace_spin = min(pace, 3) * 5 + min(spin, 2) * 5   # max 25
        ar_bonus  = min(ar, 3) * 8                          # max 24
        depth     = min(bowlers, 7) * 7                     # max 49
        return round(min(pace_spin + ar_bonus + depth, 100), 2)

    def __repr__(self):
        return f"XI(name={self.name!r}, players={len(self.players)})"


# ─────────────────────────────────────────────
# CLASH
# ─────────────────────────────────────────────

class Clash:
    """
    Compares two XIs across batting, bowling, balance, and form.
    Predicts a match winner with score estimate.
    """

    def __init__(self, xi1: XI, xi2: XI):
        self.xi1 = xi1
        self.xi2 = xi2

    def _composite(self, xi: XI) -> dict:
        bat     = xi.team_batting_impact()
        bowl    = xi.team_bowling_impact()
        form    = xi.team_form()
        balance = xi.balance_score()
        bat_score  = xi.predicted_batting_score()
        bowl_score = xi.predicted_bowling_defense()

        # Total: batting 35%, bowling 30%, form 20%, balance 15%
        total = bat * 0.35 + bowl * 0.30 + form * 0.20 + balance * 0.15
        return {
            "batting":    round(bat,       2),
            "bowling":    round(bowl,      2),
            "form":       round(form,      2),
            "balance":    round(balance,   2),
            "pred_score": bat_score,
            "pred_def":   bowl_score,
            "total":      round(total,     2),
        }

    def predict(self) -> dict:
        s1 = self._composite(self.xi1)
        s2 = self._composite(self.xi2)

        if s1["total"] > s2["total"]:
            winner     = self.xi1.name
            margin     = round(s1["total"] - s2["total"], 2)
            confidence = min(55 + int(margin * 2.5), 91)
        elif s2["total"] > s1["total"]:
            winner     = self.xi2.name
            margin     = round(s2["total"] - s1["total"], 2)
            confidence = min(55 + int(margin * 2.5), 91)
        else:
            winner, margin, confidence = "Too Close to Call", 0, 50

        return {
            "xi1":        {"name": self.xi1.name, "scores": s1},
            "xi2":        {"name": self.xi2.name, "scores": s2},
            "winner":     winner,
            "margin":     margin,
            "confidence": confidence,
        }