"""The numbers that the README, the site and the figures quote, read from the published files.

Everything comes from results/v1/ (summary, speed, item rows, judge v1), the hard-cases track
(results/ltb-v1/), the Overall score (results/v1.1/overall.json) and the registry. Nothing is typed in
by hand: a sentence in the README that names a number gets it from here, and a claim it
makes about two numbers ("above", "level with") is checked here, so a changed result either changes
the text or stops the generator.

Judge results come from the fixed-sample judge protocol in results/v1/judge/ (288 items drawn from the
ids alone, every system against DeepL API, errors counted one translation at a time).
"""

from functools import cached_property
from pathlib import Path

from translate_bench import aggregate, ltb, overall, schema, stats

JUDGE_SOURCE = "v1"
REFERENCE = "deepl-api"  # the common reference of the judge comparisons
JUDGE_MODEL = "claude-fable-5-2"  # the judge that rated every system


class JudgeV1:
    """Judge protocol v1 (results/v1/judge/): one fixed sample of 288 items, every system against DeepL API."""

    source = "v1"
    path = Path("results") / schema.RELEASE / "judge" / "summary.json"

    def __init__(self, root, model=JUDGE_MODEL):
        self.data = schema.read_json(root / self.path)
        self.model = model

    def _entry(self, stage, sid):
        for e in self.data[stage]:
            if e["system"] == sid and e["judge"] == self.model:
                return e
        return None

    def versus_reference(self, sid, scope="all"):
        e = self._entry("pairwise", sid)
        if e is None or scope not in e:
            return None
        x = e[scope]
        return dict(n=x["n"], wins=x["wins"], losses=x["losses"], ties=x["ties"], identical=x.get("identical"),
                    preferred=x["preferred"], net=x["net"], net_95=x["net_95"])

    def error_free(self, sid, scope="all"):
        e = self._entry("errors", sid)
        if e is None or scope not in e:
            return None
        x = e[scope]
        return dict(n=x["n"], error_free=x["error_free"], error_free_95=x["error_free_95"],
                    directions=x["directions"])

    def directions(self, sid, scope="all"):
        e = self._entry("pairwise", sid) or self._entry("errors", sid)
        return e[scope]["directions"] if e and scope in e else None


JUDGES = {"v1": JudgeV1}

# How each judge source is described wherever its numbers appear.
JUDGE_LABELS = {
    "v1": dict(
        en="judge v1", ja="judge v1",
        long_en=("judge protocol v1: one fixed sample of 288 items drawn from the item ids alone, every system "
                 "against DeepL API"),
        long_ja="judge v1（項目IDだけから選んだ288件の固定標本で、各構成をDeepL APIと比較）"),
}


class Facts:
    """Read-only access to the release's numbers, with the registry's names."""

    def __init__(self, root, judge_source=None):
        self.root = Path(root)
        base = self.root / "results" / schema.RELEASE
        self.summary = schema.read_json(base / "summary.json")
        self.speed = schema.read_json(base / "speed.json")
        self.registry = schema.read_json(self.root / "configs" / "systems.json")
        self.systems = {s["id"]: s for s in self.registry["systems"]}
        self.judge_source = judge_source or JUDGE_SOURCE
        self.judge = JUDGES[self.judge_source](self.root)
        self.judge_label = JUDGE_LABELS[self.judge_source]
        self.hard_summary = schema.read_json(self.root / ltb.BASE / "summary.json") if ltb.exists(self.root) else None
        self.second = ltb.second_verifier(self.root)
        self.overall_data = schema.read_json(self.root / overall.PATH) if overall.exists(self.root) else None

    # Names ------------------------------------------------------------------------------------------------

    def name(self, sid):
        return self.systems[sid]["name"]

    def label(self, sid):
        """System name with the developer in parentheses, as the figures write it."""
        s = self.systems[sid]
        return f"{s['name']} ({s['developer']})"

    def kind(self, sid):
        return self.systems[sid]["kind"]

    # Scores -----------------------------------------------------------------------------------------------

    def block(self, sid):
        return self.summary["systems"][sid]

    def comet(self, sid, view="overall"):
        return self.block(sid)["comet22"][view]

    def chrf(self, sid, view="overall"):
        return self.block(sid)["chrf"][view]

    def metricx(self, sid, which="ref", view=None):
        m = self.block(sid)["metricx24"]
        if m is None:
            return None
        return m[f"metricx24_{which}" + (f"_{view}" if view else "")]

    def full(self, sid):
        """True when the system has both text types in all 18 directions."""
        return self.comet(sid) is not None

    def ranked(self, kind=None, view="overall"):
        """Systems with every cell of the view, by the release's ranking (highest COMET-22 first)."""
        kinds = (kind,) if kind else schema.KINDS
        order = [s for k in kinds for s in self.summary["rankings"][view][k]]
        return sorted(order, key=lambda s: (-self.comet(s, view), s))

    # Hard cases and the Overall score ----------------------------------------------------------------------

    def hard(self, sid):
        """The hard-cases pillar (0-1): the pass rate on the items in the release's directions, or for a system
        below 18 directions on the items in the directions it covers; None without the track."""
        if self.overall_data is not None:
            value = self.overall_data["systems"][sid]["hard_cases"]
            return None if value is None else value / 100
        e = (self.hard_summary or {}).get("systems", {}).get(sid)
        return None if e is None else e["our_directions"]["passed"] / e["our_directions"]["items"]

    def hard_block(self, sid):
        return ((self.hard_summary or {}).get("systems") or {}).get(sid)

    def hard_figure(self, sid):
        """The block of the hard-cases pillar: `covered` for a system scored on its covered items, else
        `our_directions`."""
        e = self.hard_block(sid)
        if e is None:
            return None
        n = len(schema.DIRECTIONS)
        entry = (self.overall_data or {}).get("systems", {}).get(sid) or {}
        partial = (entry.get("directions") or {}).get("standard", n) < n
        return e["covered"] if partial and (e.get("covered") or {}).get("items") else e["our_directions"]

    def coverage(self, sid):
        """Directions (of 18) that every pillar of the Overall score covers."""
        return self.overall_data["systems"][sid]["coverage"] if self.overall_data else len(schema.DIRECTIONS)

    def coverage_mark(self, sid):
        """" (16/18)" for a system below all 18 directions, else ""."""
        n = self.coverage(sid)
        return "" if n == len(schema.DIRECTIONS) else f" ({n}/{len(schema.DIRECTIONS)})"

    def overall(self, sid):
        """The Overall score (0-100, one decimal), or None for a system without one."""
        return None if self.overall_data is None else self.overall_data["systems"][sid]["overall"]

    def ranked_overall(self, kind=None):
        """Systems with an Overall score, highest first (ties to the higher COMET-22)."""
        if self.overall_data is None:
            return []
        members = None if kind is None else {s for s in self.systems if self.kind(s) == kind}
        return overall.ranked(self.overall_data, members)

    def count_systems(self, kind=None):
        return sum(1 for s in self.systems.values() if kind is None or s["kind"] == kind)

    # Resources --------------------------------------------------------------------------------------------

    def speed_entry(self, sid):
        return self.speed["systems"].get(sid) or {}

    def seconds(self, sid, kind="sentence"):
        entry = self.speed_entry(sid).get(kind)
        return entry["median_s"] if entry else None

    def memory(self, sid):
        return self.speed_entry(sid).get("peak_memory_gib")

    def choice(self, rule):
        return next(c for c in self.summary["choices"] if c["rule"] == rule)

    # Paired comparisons -----------------------------------------------------------------------------------

    @cached_property
    def release(self):
        return aggregate.Release(self.root)

    @cached_property
    def _draws(self):
        return self.release.draws("comet22")

    def paired(self, a, b, view="overall", directions=schema.DIRECTIONS):
        """COMET-22 of a minus b with its paired 95% interval, as the summary computes them."""
        for e in self.summary["versus_leader"]:
            if directions == schema.DIRECTIONS and e["view"] == view and (e["system"], e["leader"]) == (a, b):
                return dict(delta=e["delta"], ci95=e["ci95"], n=e["n"])
        result = aggregate.paired(self._draws, aggregate.view_keys(view, directions), a, b)
        return aggregate.rounded(result)

    def tied(self, a, b, view="overall"):
        lo, hi = self.paired(a, b, view)["ci95"]
        return lo <= 0 <= hi

    @cached_property
    def _metricx_draws(self):
        """Document draws of MetricX-24 with the reference: plain means of the scored items in each cell."""
        cells = {}
        for sid, table in self.release.tables.items():
            rows = {r["id"]: r for r in self.release.rows[sid]}
            cells[sid] = {key: {i: (rows[i]["doc"], rows[i]["metricx24_ref"], rows[i]["chrf_stats"]) for i in items
                                if rows[i].get("metricx24_ref") is not None}
                          for key, items in table.items["comet22"].items()}
        return stats.Draws(cells, self.release.weights)

    def paired_metricx(self, a, b, view="overall", directions=schema.DIRECTIONS):
        """MetricX-24 (with the reference) of a minus b on common items, with its paired 95% interval.

        The same document draws and aggregation as COMET-22; lower is better, so a negative difference
        favours a. Not part of the summary: the README checks its claims about MetricX-24 order with it."""
        delta, n = self._metricx_draws.pair(aggregate.release_order(aggregate.view_keys(view, directions)), a, b)
        if delta is None:
            return None
        point, lo, hi = stats.interval(delta[0])
        return dict(delta=point, ci95=[lo, hi], n=n)


def require(condition, claim):
    """Stop the generator when a sentence it would write is no longer true."""
    if not condition:
        raise ValueError(f"The results no longer support the claim: {claim}. Rewrite the text that makes it.")
