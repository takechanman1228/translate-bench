"""Draw the README figures as SVG from the published results (needs the `figures` extra: matplotlib).

    python -m pip install -e '.[figures]'
    python -m translate_bench.export.figures          # writes figures/*.svg

Figures show the chart only: no headline, finding or footnote inside the image (captions live in the
README), raw scores rather than differences, and each system as "Name (Developer)". They are drawn
on a white background so that they read the same on GitHub's light and dark pages.

- lead.svg                 the Overall score and its three pillars, on one 0-100 scale, for the systems with
                           an Overall score (results/v1.1/overall.json); below 18 directions with "(16/18)"
- hard-cases.svg           the hard-cases pillar with its 95% interval for every system (results/ltb-v1/): the
                           pass rate on the items in the release's directions, or in the directions a system
                           covers when it covers fewer than 18, marked "(16/18)"
- size-quality.svg         COMET-22 by total parameters for the local families with several sizes
- quality-memory.svg       COMET-22 against peak process memory, with the Pareto frontier
- metric-disagreement.svg  COMET-22 against MetricX-24 for the same systems
"""

import argparse
import sys
from pathlib import Path

from translate_bench import schema
from translate_bench.export.facts import REFERENCE, Facts

OUT = Path("figures")
# Categorical slots validated for colour-vision deficiency (light surface); local and cloud are the first two.
LOCAL, CLOUD = "#2a78d6", "#eb6834"
FAMILY_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
FAMILY_MARKERS = ["o", "s", "D", "^", "v", "P"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#6f6d67", "#e1e0d9", "#c3c2b7"


# Names too long for an axis label, shortened as the leaderboard shortens them.
SHORT_NAMES = {
    "Apple Intelligence on-device model (Foundation Models)": "Apple Foundation Models",
    "Apple Intelligence on-device model (Foundation Models, permissive guardrails)":
        "Apple Foundation Models, permissive guardrails",
}


def tint(color, share):
    """`color` mixed with white: an opaque lighter shade, so grid lines stay behind it."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(255 - share * (255 - c)):02x}" for c in rgb)


def setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 8.5,
        "svg.fonttype": "none",
        "svg.hashsalt": "translate-bench",
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.linewidth": 0.8,
        "xtick.color": MUTED, "ytick.color": INK2, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "legend.frameon": False,
    })
    return plt


def grid(ax, axis="both"):
    ax.grid(True, axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", bbox_inches="tight", pad_inches=0.15, metadata={"Date": None, "Creator": None})


def short_label(facts, sid):
    """Name (Developer), without a parenthesis already in the name. DeepL API is named as such alone."""
    s = facts.systems[sid]
    name = SHORT_NAMES.get(s["name"], s["name"].replace(" (on-device)", ""))
    return name if s["developer"] == "DeepL" else f"{name} ({s['developer']})"


def label_points(ax, points, fontsize=7.2, offsets=None, lines=()):
    """Place one text label per point without overlapping labels, points or lines (greedy, with leaders)."""
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = []
    dots = [ax.transData.transform((x, y)) for x, y, _ in points]
    segments = []
    for line in lines:
        pts = [ax.transData.transform(p) for p in line]
        segments += list(zip(pts, pts[1:]))
    near = offsets or [(6, -3), (-6, -3), (0, 6), (0, -11), (6, 5), (6, -11), (-6, 5), (-6, -11)]
    far = [(18, 8), (18, -16), (-18, 8), (-18, -16), (28, -3), (-28, -3), (0, 18), (0, -24), (30, 14),
           (30, -20), (-30, 14), (-30, -20)]
    axes_box = ax.get_window_extent(renderer)

    def crosses(box):
        for (x1, y1), (x2, y2) in segments:
            if max(x1, x2) < box.x0 or min(x1, x2) > box.x1 or max(y1, y2) < box.y0 or min(y1, y2) > box.y1:
                continue
            if x1 == x2 or y1 == y2:  # axis-aligned segments (frontier steps)
                return True
            for t in (i / 20 for i in range(21)):  # sample a sloped segment
                px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                if box.x0 <= px <= box.x1 and box.y0 <= py <= box.y1:
                    return True
        return False

    order = sorted(range(len(points)), key=lambda i: -points[i][1])
    unplaced = []
    for i in order:
        x, y, text = points[i]
        for k, (dx, dy) in enumerate(near + far):
            leader = k >= len(near)
            ha = "left" if dx > 0 else "right" if dx < 0 else "center"
            t = ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va="bottom",
                            fontsize=fontsize, color=INK,
                            arrowprops=dict(arrowstyle="-", color=AXIS, linewidth=0.7, shrinkA=0, shrinkB=3)
                            if leader else None)
            box = t.get_window_extent(renderer).expanded(1.02, 1.08)
            inside = box.x0 >= axes_box.x0 - 2 and box.x1 <= axes_box.x1 + 4 and box.y0 >= axes_box.y0 and \
                box.y1 <= axes_box.y1 + 4
            hits_label = any(box.overlaps(b) for b in placed)
            hits_dot = any(box.x0 - 3 < px < box.x1 + 3 and box.y0 - 3 < py < box.y1 + 3
                           for j, (px, py) in enumerate(dots) if j != i)
            if inside and not hits_label and not hits_dot and not crosses(box):
                placed.append(box)
                break
            t.remove()
        else:
            unplaced.append(i)
    # What fits nowhere goes to a column right of the axes, in vertical order, with leader lines.
    if unplaced:
        step = fontsize * 1.45 * fig.dpi / 72
        unplaced.sort(key=lambda i: -dots[i][1])
        y_next = None
        for i in unplaced:
            px, py = dots[i]
            ty = py if y_next is None else min(py, y_next)
            y_next = ty - step
            xa, ya = ax.transAxes.inverted().transform((axes_box.x1 + 14, ty))
            ax.annotate(points[i][2], (points[i][0], points[i][1]), xytext=(xa, ya), textcoords="axes fraction",
                        ha="left", va="center", fontsize=fontsize, color=INK, annotation_clip=False,
                        arrowprops=dict(arrowstyle="-", color=AXIS, linewidth=0.7, shrinkA=2, shrinkB=3))


def clip_marker(ax, x, y, text, side, color):
    """A point outside the plotted range: a triangle at the edge of the axes and its value."""
    marker = {"left": "<", "right": ">", "bottom": "v"}[side]
    ax.plot([x], [y], marker=marker, markersize=6, color=color, linestyle="none", clip_on=False, zorder=4)
    dx, dy, ha = {"left": (7, -3, "left"), "right": (-7, -3, "right"), "bottom": (7, -2, "left")}[side]
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va="bottom", fontsize=7,
                color=INK2)


def kind_legend(plt, fig):
    handles = [plt.Line2D([], [], marker="s", color=LOCAL, linestyle="none", markersize=6, label="Local"),
               plt.Line2D([], [], marker="s", color=CLOUD, linestyle="none", markersize=6, label="Cloud")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.0), ncol=2, fontsize=8, handletextpad=0.3)


def lead(facts, plt, path):
    """The Overall score and its three pillars as bars on one 0-100 scale, so each pillar's share is visible."""
    data = facts.overall_data["systems"]
    rows = list(reversed(facts.ranked_overall()))
    fig, axes = plt.subplots(1, 4, figsize=(11.4, 0.215 * len(rows) + 1.0), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1, 1, 1], "wspace": 0.1})
    y = range(len(rows))
    panels = [("Overall\n(mean of the three pillars)", "overall", 1.0),
              ("Standard\nCOMET-22 × 100", "standard", 0.45),
              ("Reliability\nerror-free translations, %", "reliability", 0.45),
              ("Hard cases\npass rate, %", "hard_cases", 0.45)]
    for ax, (title, key, shade) in zip(axes, panels):
        grid(ax, "x")
        for yy, s in zip(y, rows):
            v = data[s][key]
            color = tint(LOCAL if facts.kind(s) == "local" else CLOUD, shade)
            ax.barh([yy], [v], height=0.68, color=color, linewidth=0, zorder=2)
            ax.annotate(f"{v:.1f}", (v, yy), xytext=(3, 0), textcoords="offset points", va="center", ha="left",
                        fontsize=6.9, color=INK if key == "overall" else INK2)
        ax.set_xlim(0, 114)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel(title, fontsize=8.5, color=INK2)
        ax.xaxis.set_label_position("top")
        ax.tick_params(axis="x", labeltop=True, labelbottom=True, top=False, length=0)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(ax is axes[0])
        ax.spines["bottom"].set_visible(False)
    axes[0].set_yticks(list(y))
    axes[0].set_yticklabels([short_label(facts, s) + facts.coverage_mark(s) for s in rows])
    axes[0].set_ylim(-0.7, len(rows) - 0.3)
    kind_legend(plt, fig)
    save(fig, path)
    plt.close(fig)


def hard_cases(facts, plt, path):
    """Every system's pass rate on the hard-case items in the release's directions, with its 95% interval."""
    summary = facts.hard_summary
    # The hard-cases pillar: on the items in the directions a system covers when it covers fewer than 18.
    entries = {s: facts.hard_figure(s) for s in summary["systems"]}
    marks = {s: facts.coverage_mark(s) if entries[s] is summary["systems"][s].get("covered") else "" for s in entries}
    rows = sorted(entries, key=lambda s: (entries[s]["passed"] / entries[s]["items"], facts.comet(s, "overall_measured")
                                          or 0, s))
    fig, ax = plt.subplots(figsize=(7.4, 0.2 * len(rows) + 1.0))
    grid(ax, "x")
    for yy, s in enumerate(rows):
        e = entries[s]
        rate, (lo, hi) = 100 * e["passed"] / e["items"], (100 * x for x in e["ci95"])
        local = facts.kind(s) == "local"
        color = LOCAL if local else CLOUD
        ax.plot([lo, hi], [yy, yy], color=tint(color, 0.5), linewidth=1.6, solid_capstyle="butt", zorder=2)
        ax.plot([rate], [yy], marker="o" if local else "s", markersize=5.2, color=color, markeredgecolor="white",
                markeredgewidth=0.9, linestyle="none", zorder=3)
        ax.annotate(f"{rate:.1f}", (hi, yy), xytext=(4, 0), textcoords="offset points", va="center", ha="left",
                    fontsize=6.9, color=INK2)
    ax.set_xlim(0, 80)
    ax.set_xticks([0, 20, 40, 60, 80])
    ax.set_xlabel("Pass rate on the hard items, % (line: 95% interval)", fontsize=8.5, color=INK2)
    ax.xaxis.set_label_position("top")
    ax.tick_params(axis="x", labeltop=True, labelbottom=True, top=False, length=0)
    ax.tick_params(axis="y", length=0)
    ax.spines["bottom"].set_visible(False)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([short_label(facts, s) + marks[s] for s in rows])
    ax.set_ylim(-0.7, len(rows) - 0.3)
    handles = [plt.Line2D([], [], marker="o", color=LOCAL, linestyle="none", markersize=5.5, label="Local"),
               plt.Line2D([], [], marker="s", color=CLOUD, linestyle="none", markersize=5.5, label="Cloud")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.0), ncol=2, fontsize=8, handletextpad=0.3)
    save(fig, path)
    plt.close(fig)


def size_quality(facts, plt, path):
    families = {}
    for sid, s in facts.systems.items():
        if s["kind"] == "local" and s.get("parameters"):
            families.setdefault(s["family"], []).append(sid)
    families = {f: sorted(m, key=lambda x: facts.systems[x]["parameters"]) for f, m in families.items() if len(m) > 1}
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    grid(ax)
    lo, hi = 0.828, 0.865
    handles = []
    for i, (family, members) in enumerate(families.items()):
        color, marker = FAMILY_COLORS[i % len(FAMILY_COLORS)], FAMILY_MARKERS[i % len(FAMILY_MARKERS)]
        xs = [facts.systems[m]["parameters"] / 1e9 for m in members]
        full = [facts.full(m) for m in members]
        ys = [facts.comet(m) if f else facts.comet(m, "overall_measured") for m, f in zip(members, full)]
        ax.plot(xs, [max(v, lo) for v in ys], color=color, linewidth=1.8, zorder=2)
        for x, yv, f in zip(xs, ys, full):
            if yv < lo:
                clip_marker(ax, x, lo, f"{yv:.3f}", "bottom", color)
                continue
            ax.plot([x], [yv], marker=marker, markersize=6, color=color, markerfacecolor=color if f else "white",
                    markeredgecolor=color if not f else "white", markeredgewidth=1.4 if not f else 0.8, zorder=3,
                    linestyle="none")
        developer = facts.systems[members[0]]["developer"]
        dirs = "" if all(full) else f", {facts.block(members[0])['overall_measured_directions']} directions"
        handles.append(plt.Line2D([], [], color=color, marker=marker, markersize=6, linewidth=1.8,
                                  markerfacecolor=color if all(full) else "white",
                                  label=f"{family} ({developer}{dirs})"))
    for sid in (facts.ranked("cloud")[0], REFERENCE):
        v = facts.comet(sid)
        ax.axhline(v, color=MUTED, linewidth=0.9, zorder=1)
        ax.annotate(short_label(facts, sid), (0.62, v), xytext=(0, 3), textcoords="offset points", fontsize=7.2,
                    color=INK2, va="bottom")
    ax.set_xscale("log")
    ticks = [1, 2, 4, 8, 16, 32]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t}B" for t in ticks])
    ax.minorticks_off()
    ax.set_xlim(0.6, 45)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Total parameters (log scale)")
    ax.set_ylabel("COMET-22, overall")
    ax.tick_params(length=0)
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=7.4, handlelength=2.2)
    save(fig, path)
    plt.close(fig)


def quality_memory(facts, plt, path):
    systems = [s for s in facts.ranked("local") if facts.memory(s) is not None]
    pts = sorted(((facts.memory(s), facts.comet(s), s) for s in systems), key=lambda p: (p[0], -p[1]))
    front, best = [], -1.0
    for m, c, s in pts:
        if c > best:
            front.append((m, c, s))
            best = c
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    grid(ax)
    xs, ys = [], []
    for k, (m, c, _) in enumerate(front):
        if k:
            xs += [m]
            ys += [front[k - 1][1]]
        xs.append(m)
        ys.append(c)
    xs.append(30)
    ys.append(front[-1][1])
    ax.plot(xs, ys, color=INK2, linewidth=1.3, zorder=2)
    on_front = {s for _, _, s in front}
    shown = []
    for m, c, s in pts:
        if c < 0.828:
            clip_marker(ax, m, 0.828, f"{short_label(facts, s)}, {c:.3f}", "bottom", LOCAL)
            continue
        shown.append((m, c, s))
        ax.plot([m], [c], marker="o", markersize=6, color=LOCAL, markeredgecolor="white", markeredgewidth=0.9,
                zorder=3, linestyle="none", alpha=1 if s in on_front else 0.75)
    ax.set_xscale("log", base=2)
    ticks = [1, 2, 4, 8, 16, 32]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks])
    ax.minorticks_off()
    ax.set_xlim(1.6, 30)
    ax.set_ylim(0.828, 0.862)
    ax.set_xlabel(f"Peak process memory, GiB (log scale) · {facts.speed['machine']}")
    ax.set_ylabel("COMET-22, overall")
    ax.tick_params(length=0)
    label_points(ax, [(m, c, short_label(facts, s)) for m, c, s in shown], fontsize=6.9, lines=[list(zip(xs, ys))])
    save(fig, path)
    plt.close(fig)


def metric_disagreement(facts, plt, path):
    systems = facts.ranked()
    fig, ax = plt.subplots(figsize=(8.6, 6.2))
    grid(ax)
    xlo, ylo = 0.832, 4.55
    shown = []
    for s in systems:
        local = facts.kind(s) == "local"
        color = LOCAL if local else CLOUD
        x, y = facts.comet(s), facts.metricx(s)
        if x < xlo or y > ylo:
            clip_marker(ax, xlo, ylo, f"{short_label(facts, s)}: {x:.3f}, {y:.2f}", "left", color)
            continue
        shown.append(s)
        ax.plot([x], [y], marker="o" if local else "s", markersize=6, color=color, markeredgecolor="white",
                markeredgewidth=0.9, linestyle="none", zorder=3)
    ax.set_xlim(xlo, 0.8655)
    ax.set_ylim(ylo, 3.2)
    ax.set_xlabel("COMET-22, overall (higher is better)")
    ax.set_ylabel("MetricX-24 with reference (lower is better; axis reversed)")
    ax.tick_params(length=0)
    handles = [plt.Line2D([], [], marker="o", color=LOCAL, linestyle="none", markersize=5.5, label="Local"),
               plt.Line2D([], [], marker="s", color=CLOUD, linestyle="none", markersize=5.5, label="Cloud")]
    ax.legend(handles=handles, loc="lower right", fontsize=8)
    label_points(ax, [(facts.comet(s), facts.metricx(s), short_label(facts, s)) for s in shown], fontsize=6.6)
    save(fig, path)
    plt.close(fig)


FIGURES = {"lead.svg": lead, "hard-cases.svg": hard_cases, "size-quality.svg": size_quality,
           "quality-memory.svg": quality_memory, "metric-disagreement.svg": metric_disagreement}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="the translate-bench checkout (default: found from here)")
    parser.add_argument("--out", type=Path, help="output directory (default: figures/ in the checkout)")
    args = parser.parse_args(argv)
    root = schema.find_root(args.root)
    try:
        plt = setup()
    except ImportError:
        print("figures: matplotlib is missing; install the extra with  python -m pip install -e '.[figures]'",
              file=sys.stderr)
        return 2
    facts = Facts(root)
    out = args.out or root / OUT
    for name, draw in FIGURES.items():
        draw(facts, plt, out / name)
        print(f"wrote {(out / name).relative_to(root) if (out / name).is_relative_to(root) else out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
