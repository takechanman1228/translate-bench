"""The Overall score of Translate Bench v1.1 (results/v1.1/overall.json), from the published results.

Three pillars, each on a 0-100 scale, weigh equally; the Overall score is their mean, rounded to one
decimal (half up):

- Standard: COMET-22 x 100 over the directions the system covers (results/v1/summary.json:
  systems.ID.comet22.overall_measured, sentences and passages 50:50 in each direction).
- Reliability: the LLM judge's error-free share x 100 over its directions (results/v1/judge/summary.json:
  errors[].all.error_free).
- Hard cases: the pass rate x 100 on the Last Translation Benchmark items in the release's directions
  (results/ltb-v1/summary.json: systems.ID.our_directions, passed / items). A system below 18
  directions is scored on the items in the directions it covers (systems.ID.covered): items in the
  others leave the denominator instead of counting as failed.

A system gets an Overall score when every pillar covers at least MIN_DIRECTIONS of the 18 directions.
Below 18, each pillar is a mean over the directions the system covers, and `coverage` records how many
(the fewest of the three pillars) with `missing_languages`. A system without an Overall score keeps
the pillar values it has. MetricX-24 is not part of the Overall score, and it has no interval.

    python -m translate_bench.overall          # write results/v1.1/overall.json
    python -m translate_bench.overall --check  # exit 1 if the file differs from a recomputation

`translate-bench verify` runs the same check.
"""

import argparse
import hashlib
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from translate_bench import schema

PATH = Path("results") / "v1.1" / "overall.json"
SCHEMA = "translate-bench/overall@1"
RELEASE = "v1.1"
JUDGE = "claude-fable-5-2"  # the judge whose error-free share is the reliability pillar
# The fewest of the 18 directions every pillar must cover for an Overall score; below 18 the pillars are means
# over the covered directions.
MIN_DIRECTIONS = 12
PILLARS = ("standard", "reliability", "hard_cases")
SOURCES = {"standard": "results/v1/summary.json", "reliability": "results/v1/judge/summary.json",
           "hard_cases": "results/ltb-v1/summary.json"}
AGGREGATION = (
    "The Overall score is the mean of three pillars on a 0-100 scale, weighted equally and rounded to one decimal: "
    "standard (COMET-22 over the directions the system covers, times 100), reliability (the share of the LLM "
    "judge's sample with no error marked, in percent) and hard cases (the pass rate on the Last Translation "
    "Benchmark items in the release's directions, in percent; for a system below 18 directions, on the items in "
    "the directions it covers). MetricX-24 is not part of it, and it has no interval.")
ELIGIBILITY = (
    f"A system gets an Overall score when every pillar covers at least {MIN_DIRECTIONS} of the 18 directions. Below "
    "18, each pillar is a mean over the directions the system covers, and the coverage is published with the "
    "score. The other systems keep their pillar values.")


def r4(x):
    return None if x is None else round(float(x), 4) + 0.0


def one_decimal(x):
    """Half-up rounding to one decimal, so a value never turns on binary floating point."""
    return float(Decimal(repr(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def exists(root):
    return (Path(root) / PATH).is_file()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def missing_languages(block):
    """Languages with a direction lacking a complete sentence or passage cell, in the release's order."""
    kinds = block["directions"]
    covered = {d for d in schema.DIRECTIONS if d in kinds["sentence"] and d in kinds["passage"]}
    return [k for k in schema.LANGUAGES if not {f"en-{k}", f"{k}-en"} <= covered]


def system_entry(block, errors, hard):
    """One system's pillars (0-100, unrounded), their directions, coverage and eligibility."""
    n = len(schema.DIRECTIONS)
    comet = block["comet22"]["overall_measured"] if block["comet22"]["overall"] is None else block["comet22"]["overall"]
    standard_dirs = block["overall_measured_directions"] if comet is not None else 0
    reliability_dirs = errors["directions"] if errors else 0
    hard_value, hard_dirs, hard_items = None, 0, None
    if hard:
        figure = hard["our_directions"] if standard_dirs == n or not (hard.get("covered") or {}).get("items") \
            else hard["covered"]
        hard_value = 100 * figure["passed"] / figure["items"] if figure["items"] else None
        hard_dirs = figure.get("directions", n)
        hard_items = figure["items"]
    values = dict(standard=None if comet is None else 100 * comet,
                  reliability=None if errors is None else 100 * errors["error_free"], hard_cases=hard_value)
    directions = dict(standard=standard_dirs, reliability=reliability_dirs, hard_cases=hard_dirs)
    coverage = min(directions.values())
    eligible = all(v is not None for v in values.values()) and coverage >= MIN_DIRECTIONS
    return values, directions, coverage, hard_items, eligible


def build(root):
    """The content of results/v1.1/overall.json, recomputed from the published results."""
    root = Path(root)
    summary = schema.read_json(root / SOURCES["standard"])
    judge = schema.read_json(root / SOURCES["reliability"])
    hard_path = root / SOURCES["hard_cases"]
    hard = schema.read_json(hard_path) if hard_path.is_file() else {}
    errors = {e["system"]: e["all"] for e in judge["errors"] if e["judge"] == JUDGE and "all" in e}
    systems = {}
    for system in schema.read_json(root / "configs" / "systems.json")["systems"]:
        sid = system["id"]
        block = summary["systems"][sid]
        values, directions, coverage, items, eligible = system_entry(block, errors.get(sid),
                                                                     (hard.get("systems") or {}).get(sid))
        systems[sid] = dict(overall=one_decimal(sum(values.values()) / len(PILLARS)) if eligible else None,
                            **{k: r4(values[k]) for k in PILLARS}, coverage=coverage, directions=directions,
                            hard_cases_items=items, missing_languages=missing_languages(block))
    with_overall = [s for s in systems.values() if s["overall"] is not None]
    n = len(schema.DIRECTIONS)
    return dict(
        schema=SCHEMA, release=RELEASE, results=schema.RELEASE, aggregation=AGGREGATION, rule=ELIGIBILITY,
        min_directions=MIN_DIRECTIONS, directions=n,
        pillars=dict(
            standard=dict(name="Standard", description="COMET-22 over the directions the system covers, times 100",
                          source=SOURCES["standard"]),
            reliability=dict(name="Reliability", description="Share of the judge's sample with no error marked, "
                             "in percent", source=SOURCES["reliability"], judge=JUDGE),
            hard_cases=dict(name="Hard cases", description="Pass rate on the Last Translation Benchmark items in "
                            "the directions the system covers, in percent", source=SOURCES["hard_cases"],
                            verifier=(hard.get("verifier") or {}).get("model"),
                            items=(hard.get("dataset") or {}).get("our_direction_items"))),
        sources={rel: digest(root / rel) for rel in SOURCES.values() if (root / rel).is_file()},
        counts=dict(systems=len(systems), overall=len(with_overall),
                    full=sum(s["coverage"] == n for s in with_overall),
                    partial=sum(s["coverage"] < n for s in with_overall),
                    without_overall=len(systems) - len(with_overall)),
        systems=systems,
    )


def ranked(data, members=None):
    """Systems with an Overall score (of `members`, if given), highest first; ties go to the higher COMET-22."""
    systems = data["systems"]
    pool = [s for s in systems if systems[s]["overall"] is not None and (members is None or s in members)]
    return sorted(pool, key=lambda s: (-systems[s]["overall"], -systems[s]["standard"], s))


def check(root):
    """Differences between results/v1.1/overall.json and a recomputation; [] when the file is absent."""
    from translate_bench.verify import differences

    root = Path(root)
    if not exists(root):
        return []
    published = schema.read_json(root / PATH)
    return differences(published, json.loads(json.dumps(build(root))), "v1.1/overall.json")


def write(root):
    path = Path(root) / PATH
    schema.write_json(path, build(root))
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="the translate-bench checkout (default: found from here)")
    parser.add_argument("--check", action="store_true", help="compare with the committed file instead of writing")
    args = parser.parse_args(argv)
    root = schema.find_root(args.root)
    if args.check:
        found = check(root) if exists(root) else [f"{PATH}: missing"]
        for line in found:
            print(line)
        print(f"overall: {'differs from the results' if found else 'matches the results'} ({PATH})")
        return 1 if found else 0
    path = write(root)
    print(f"wrote {PATH} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
