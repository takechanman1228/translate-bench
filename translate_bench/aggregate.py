"""Cells, scores and comparisons of the release, computed from the item rows.

A cell is one text type in one direction for one system: 200 sentences, or 20 passages.
In the twelve directions outside the core, the 20 passages are the union of two WMT24++
document sets (set-8 and set-12); a system needs both for a passage cell.

Overall score. In each direction, the mean of the sentence cell and the passage cell
(50:50); then the mean over directions, each direction weighted equally. A cell's
COMET-22 is the mean over its scored items; its chrF++ is corpus chrF++ from the pooled
sufficient statistics of the same items.

Paired comparisons use, cell by cell, the items both systems scored, and the shared
document draws of `translate_bench.stats`.
"""

import math
from collections import defaultdict
from statistics import mean

from translate_bench import schema, stats

METRICS = ("comet22", "chrf")
VIEWS = ("overall", "sentence", "passage")
TYPE_ORDER = {"passage": 0, "sentence": 1}


def release_order(keys):
    """Cells in the order the release's profiles used: passages before sentences, then by direction."""
    return sorted(keys, key=lambda k: (TYPE_ORDER[k[0]], stats.stratum_cell(k[0], k[1])[1]))


def frame_order(keys):
    """Cells in the frame's direction order (used by the per-type size steps)."""
    return sorted(keys, key=lambda k: schema.DIRECTIONS.index(k[1]))


def view_keys(view, directions):
    types = schema.TYPES if view == "overall" else (view,)
    return [(t, d) for d in directions for t in types]


class Release:
    """The registry, the item rows of every system and the shared document draws."""

    def __init__(self, root, extra=None):
        self.root = root
        self.registry = schema.read_json(root / "configs" / "systems.json")
        self.systems = {s["id"]: s for s in self.registry["systems"]}
        folder = root / "results" / schema.RELEASE / "items"
        self.rows = {sid: schema.read_jsonl(folder / f"{sid}.jsonl") for sid in self.systems}
        self.published = list(self.systems)
        speed = root / "results" / schema.RELEASE / "speed.json"
        self.speed = schema.read_json(speed)["systems"] if speed.is_file() else {}
        self.tables = {sid: Tables(rows) for sid, rows in self.rows.items()}
        self.weights = stats.multiplicities(coverage(self.tables[s] for s in self.published))
        self.extra = {}
        for sid, (system, rows) in (extra or {}).items():
            self.add(sid, system, rows)

    def add(self, sid, system, rows):
        """Add a user-scored system that is compared with the release but does not change its draws."""
        if sid in self.systems:
            raise ValueError(f"System id {sid!r} is already part of the release")
        self.systems[sid] = system
        self.rows[sid] = rows
        self.tables[sid] = Tables(rows)
        self.extra[sid] = system

    def kind(self, sid):
        return self.systems[sid]["kind"]

    def draws(self, metric="comet22"):
        cells = {sid: table.items[metric] for sid, table in self.tables.items()}
        return stats.Draws(cells, self.weights)


class Tables:
    """One system's rows grouped into complete cells."""

    def __init__(self, rows):
        groups = defaultdict(list)
        for r in rows:
            groups[r["type"], r["direction"], r["subset"]].append(r)
        self.counts = {}  # (type, direction) -> (attempted, ok)
        self.items = {m: {} for m in METRICS}  # metric -> (type, direction) -> {id: (doc, comet, stats)}
        self.subsets = {m: {} for m in METRICS}  # metric -> (subset, direction) -> {id: ...}
        self.incomplete = []
        complete = {}
        for (kind, direction, subset), members in groups.items():
            size = schema.SUBSETS[subset] if subset else schema.CELL_SIZE[kind]
            if len(members) != size:
                self.incomplete.append((kind, direction, subset, len(members), size))
                continue
            complete[kind, direction, subset] = members
        merged = defaultdict(list)
        for (kind, direction, subset), members in complete.items():
            if subset:
                for m in METRICS:
                    self.subsets[m][subset, direction] = eligible(members, m)
                other = "set-8" if subset == "set-12" else "set-12"
                if (kind, direction, other) not in complete:
                    continue
            merged[kind, direction].extend(members)
        for key, members in merged.items():
            self.counts[key] = (len(members), sum(r["status"] == "ok" for r in members))
            for m in METRICS:
                self.items[m][key] = eligible(members, m)
        self.coverage_cells = {}
        for (kind, direction, subset), members in complete.items():
            for r in members:
                if r["status"] == "ok" and r["comet22"] is not None:
                    self.coverage_cells.setdefault(r["doc"], set()).add(stats.stratum_cell(subset or kind, direction))

    def has(self, keys):
        return all(k in self.counts for k in keys)

    def directions(self, kind=None):
        """Directions with a cell of `kind`, or with both types when kind is None."""
        types = schema.TYPES if kind is None else (kind,)
        return [d for d in schema.DIRECTIONS if all((t, d) in self.counts for t in types)]


def eligible(rows, metric):
    if metric == "comet22":
        return {r["id"]: (r["doc"], r["comet22"], r["chrf_stats"]) for r in rows
                if r["status"] == "ok" and r["comet22"] is not None}
    return {r["id"]: (r["doc"], math.nan if r["comet22"] is None else r["comet22"], r["chrf_stats"]) for r in rows
            if r["status"] == "ok" and r["chrf_stats"] is not None}


def coverage(tables):
    """doc -> cells it covers, over the published systems; this fixes the strata of the bootstrap."""
    result = defaultdict(set)
    for table in tables:
        for doc, cells in table.coverage_cells.items():
            result[doc] |= cells
    return result


def cell_score(items, metric):
    if not items:
        return None
    comet, chrf = stats.corpus_scores(list(items.values()))
    return comet if metric == "comet22" else chrf


def score(table, view, directions, metric="comet22", weight=0.5):
    """Mean over directions of the view's cell scores; None if a cell is missing."""
    values = []
    for d in directions:
        if view == "overall":
            s = cell_score(table.items[metric].get(("sentence", d)), metric)
            p = cell_score(table.items[metric].get(("passage", d)), metric)
            if s is None or p is None:
                return None
            values.append(weight * s + (1 - weight) * p)
        else:
            v = cell_score(table.items[metric].get((view, d)), metric)
            if v is None:
                return None
            values.append(v)
    return mean(values) if values else None


def paired(draws, keys, a, b, metric="comet22", order=release_order):
    """a - b with its 95% interval and the number of paired items; None when a cell has no common item."""
    delta, n = draws.pair(order(keys), a, b)
    if delta is None:
        return None
    ci = stats.interval(delta[METRICS.index(metric)])
    if ci is None:
        return None
    return dict(delta=ci[0], ci95=ci[1:], n=n)


def tied(result):
    return result is not None and result["ci95"][0] <= 0 <= result["ci95"][1]


def covering(release, keys, kind=None, systems=None):
    pool = systems if systems is not None else release.published
    return [s for s in pool if (kind is None or release.kind(s) == kind) and release.tables[s].has(keys)]


def ranking(release, view, directions=schema.DIRECTIONS, kind=None, metric="comet22", systems=None):
    """Systems with every cell of the view in `directions`, highest score first (ties by id)."""
    keys = view_keys(view, directions)
    members = covering(release, keys, kind, systems)
    scored = [(score(release.tables[s], view, directions, metric), s) for s in members]
    return [s for _, s in sorted(scored, key=lambda x: (-x[0], x[1]))]


def round6(x):
    return None if x is None else round(float(x), 6) + 0.0


def rounded(value):
    """Round every float of a nested structure to six decimals for the summary file."""
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    if isinstance(value, float):
        return round6(value)
    return value
