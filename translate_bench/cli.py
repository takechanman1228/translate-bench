"""Command-line interface of Translate Bench.

    translate-bench prepare              download the test sets and assemble the inputs
    translate-bench run                  translate the inputs through an OpenAI-compatible endpoint
    translate-bench score                score your translations like the release
    translate-bench compare              place a scored system among the release's systems
    translate-bench evaluate             run, score and compare in one command
    translate-bench judge                error annotation or pairwise judging with a language model
    translate-bench validate-submission  the file checks a maintainer runs on a submitted system
    translate-bench verify               recompute results/v1/summary.json from the item rows
    translate-bench leaderboard          print the release's table
"""

import argparse
import sys
from pathlib import Path

from translate_bench import __version__, schema


def build_parser():
    parser = argparse.ArgumentParser(prog="translate-bench", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"translate-bench {__version__}")
    parser.add_argument("--root", type=Path, help="the translate-bench checkout (default: found from the "
                                                  "current directory)")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p = commands.add_parser("prepare", help="download the test sets and assemble the inputs",
                            description="Download each upstream file from its publisher, verify its SHA-256, "
                                        "rebuild every item and write sentences.tsv and passages.tsv.")
    p.add_argument("--out", type=Path, help="output directory (default: private/inputs in the checkout)")
    p.add_argument("--pairs", help="comma-separated language pairs, e.g. en-ja,en-ko (default: all nine)")
    p.add_argument("--scope", choices=("all", "sentences", "passages"), default="all")
    p.add_argument("--downloads", type=Path, help="download cache (default: OUT/downloads); inside the checkout "
                                                  "it must be in a directory Git ignores")
    p.add_argument("--no-selection-check", action="store_true",
                   help="skip recomputing the frozen selections on a full prepare")

    from translate_bench import judge, run

    p = commands.add_parser("run", help="translate the inputs through an OpenAI-compatible endpoint",
                            description=run.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    run.add_arguments(p)

    p = commands.add_parser("score", help="score your translations like the release",
                            description="Score a JSONL file of {id, translation} against the prepared inputs.")
    p.add_argument("--predictions", type=Path, required=True, help="JSONL with id and translation per line")
    p.add_argument("--inputs", type=Path, help="prepared inputs (default: private/inputs in the checkout)")
    p.add_argument("--metrics", default="chrf", help="comma-separated: chrf, comet22, metricx24 (default: chrf)")
    p.add_argument("--system-name", required=True, help="a name for your system")
    p.add_argument("--out", type=Path, help="write items/<system>.jsonl, system.json and summary.json here")

    p = commands.add_parser("compare", help="place a scored system among the release's systems")
    p.add_argument("--results", type=Path, required=True, help="a `score` output directory or an item-row file")
    p.add_argument("--against", nargs="+", metavar="SYSTEM_ID",
                   help="systems to compare with (default: deepl-api local-leader cloud-leader)")
    p.add_argument("--metric", choices=("comet22", "chrf"),
                   help="default: comet22 if the rows have COMET-22 scores, else chrf")
    p.add_argument("--view", choices=("overall", "sentence", "passage"), default="overall")
    p.add_argument("--judge", type=Path, metavar="DIR",
                   help="a `translate-bench judge` --out folder: its error-free share (and pairwise result, if any) "
                        "beside the published judge v1 results")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")

    p = commands.add_parser("evaluate", help="run, score and compare in one command",
                            description="`run` into --out, then `score` its predictions.jsonl into OUT/score, then "
                                        "`compare` OUT/score. Each step writes what it writes on its own; the "
                                        "command stops with a non-zero status at the first step that fails.")
    run.add_arguments(p)
    p.add_argument("--system-name", help="a name for your system (default: --model)")
    p.add_argument("--metrics", default="chrf", help="comma-separated: chrf, comet22, metricx24 (default: chrf)")
    p.add_argument("--against", nargs="+", metavar="SYSTEM_ID", help="systems to compare with")
    p.add_argument("--view", choices=("overall", "sentence", "passage"),
                   help="the comparison's view (default: overall if the rows have both text types, else the one "
                        "they have)")
    p.add_argument("--metric", choices=("comet22", "chrf"),
                   help="the comparison's metric (default: comet22 if scored, else chrf)")

    p = commands.add_parser("judge", help="error annotation or pairwise judging with a language model",
                            description=judge.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    judge.add_arguments(p)

    p = commands.add_parser("validate-submission", help="the file checks a maintainer runs on a submitted system")
    p.add_argument("folder", type=Path, metavar="DIR", help="the submission directory")
    p.add_argument("--rescored", type=Path, metavar="SCORE_DIR",
                   help="a maintainer's `score --out` of the contributor's predictions, compared row by row")

    p = commands.add_parser("verify", help="recompute results/v1/summary.json and check every results file")
    p.add_argument("--quiet", action="store_true")

    p = commands.add_parser("leaderboard", help="print the release's table from the item rows")
    p.add_argument("--metric", choices=("comet22", "chrf", "metricx24_ref", "metricx24_qe", "judge_preferred",
                                        "judge_net", "error_free"), default="comet22",
                   help="judge_preferred, judge_net and error_free: judge protocol v1 (results/v1/judge/)")
    p.add_argument("--pairs", help="comma-separated language pairs (default: all nine)")
    p.add_argument("--view", choices=("overall", "sentence", "passage"), default="overall")
    p.add_argument("--kind", choices=("local", "cloud"))
    p.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = schema.find_root(args.root)
        if args.command == "prepare":
            from translate_bench import prepare

            prepare.main(root, args.out, args.pairs, args.scope, args.downloads,
                         False if args.no_selection_check else None)
        elif args.command == "run":
            from translate_bench import run

            return run.main(root, args)
        elif args.command == "evaluate":
            return evaluate(root, args)
        elif args.command == "judge":
            from translate_bench import judge

            return judge.main(root, args)
        elif args.command == "validate-submission":
            from translate_bench import submission

            return submission.main(root, args.folder, rescoring=args.rescored)
        elif args.command == "score":
            from translate_bench import score

            score.main(root, args.predictions, args.inputs, args.metrics, args.system_name, args.out)
        elif args.command == "compare":
            from translate_bench import compare

            compare.main(root, args.results, args.against, args.metric, args.view, args.json, judge=args.judge)
        elif args.command == "verify":
            from translate_bench import verify

            return verify.main(root, args.quiet)
        elif args.command == "leaderboard":
            from translate_bench import leaderboard

            leaderboard.main(root, args.metric, args.pairs, args.view, args.kind, args.json)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"translate-bench {args.command}: {exc}", file=sys.stderr)
        return 2
    return 0


def evaluate(root, args):
    """`run`, then `score` of its predictions, then `compare`: a thin composition of the three commands."""
    from translate_bench import compare, run, score

    args.hint = False
    code = run.main(root, args)
    if code:
        return code
    out = schema.safe_location(args.out, root, "--out")
    _, rows, _ = score.main(root, out / "predictions.jsonl", args.inputs, args.metrics,
                            args.system_name or args.model, out / "score")
    kinds = {r["type"] for r in rows}
    view = args.view or ("overall" if kinds == set(schema.TYPES) else kinds.pop())
    try:
        compare.main(root, out / "score", args.against, args.metric, view)
    except ValueError as exc:
        print(f"translate-bench compare: {exc}", file=sys.stderr)
        return 2
    return 0


def entry():
    sys.exit(main())


if __name__ == "__main__":
    entry()
