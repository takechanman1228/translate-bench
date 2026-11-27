"""Fill the generated parts of README.md, README.ja.md, docs/metrics.md and docs/methodology.md from the results.

    python -m translate_bench.export.readme          # rewrite the generated blocks
    python -m translate_bench.export.readme --check  # exit 1 if a generated block differs from the results

A generated block sits between `<!-- tb:NAME -->` and `<!-- /tb:NAME -->`; the text around it is
written by hand. Every number in a block comes from the published files through `facts.Facts`
(results/v1/, results/ltb-v1/ and results/v1.1/overall.json). A sentence that states an order or a
direction ("ahead of", "lower", "under 10%") checks it first, so a change in the results either
changes the sentence or, for a claim the wording cannot follow, stops the generator.
"""

import argparse
import re
import sys
from pathlib import Path
from statistics import mean

from translate_bench import schema
from translate_bench.export.facts import REFERENCE, Facts, require

FILES = {"README.md": "en", "README.ja.md": "ja", "docs/metrics.md": "metrics", "docs/methodology.md": "methodology"}
BLOCK = re.compile(r"(<!-- tb:([\w.:/-]+) -->\n)(.*?)(<!-- /tb:\2 -->)", re.S)
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
                10: "ten", 11: "eleven", 12: "twelve"}
LEADERBOARD = "https://takechanman1228.github.io/translate-bench/"
LTB_URL = "https://github.com/zouharvi/last-translation-benchmark"
LTB_PAPER = "https://arxiv.org/abs/2609.04173"
ANCHOR = {"en": "#overall-score", "ja": "#総合スコア"}
TOP_ROWS = 12  # the top ten are all cloud systems; twelve rows reach the top local system and DeepL API


# Formatting -----------------------------------------------------------------------------------------------

def c4(x):
    return f"{x:.4f}"


def pct(x):
    return f"{100 * x:.0f}%"


def pct1(x):
    return f"{100 * x:.1f}%"


def o1(x):
    return f"{x:.1f}"


def signed(x):
    return f"{'−' if x < 0 else '+'}{abs(x):.2f}"


def words(n, lang="en"):
    return NUMBER_WORDS.get(n, str(n)) if lang == "en" else str(n)


# README blocks --------------------------------------------------------------------------------------------

def hard_items(facts):
    return facts.hard_summary["dataset"]["our_direction_items"]


def counts(facts, lang):
    n, full = facts.count_systems(), len(facts.ranked())
    local, cloud = facts.count_systems("local"), facts.count_systems("cloud")
    dirs = len(schema.DIRECTIONS)
    sent, pas = schema.CELL_SIZE["sentence"], schema.CELL_SIZE["passage"]
    items = dirs * (sent + pas)
    hard = hard_items(facts)
    if lang == "en":
        return "\n".join([
            f"- **Systems:** {n} configurations ({local} local, {cloud} cloud). {full} cover all {dirs} directions.",
            f"- **Test set:** {dirs} directions between English and 9 languages. Each has {sent} news sentences and "
            f"{pas} longer passages ({items:,} items in total).",
            "- **Hardware:** local models ran on one Apple M6 with 32 GiB of memory.",
            f"- **Quality:** COMET-22, MetricX-24, an LLM judge and {hard} hard cases from the Last Translation "
            f"Benchmark, side by side, plus an [Overall score]({ANCHOR['en']}) that averages three of them.",
        ])
    return "\n".join([
        f"- **構成：** {n}（ローカル{local}、クラウド{cloud}）。うち{full}構成が{dirs}方向すべてに対応。",
        f"- **評価データ：** 英語と9言語の間の{dirs}方向。各方向にニュース文{sent}文と長めの文章{pas}件"
        f"（合計{items:,}件）。",
        "- **実行環境：** ローカルモデルはメモリ32 GiBのApple M6 1台で実行。",
        f"- **品質の指標：** COMET-22、MetricX-24、LLMによる判定、Last Translation Benchmarkの難しい例{hard}件を"
        f"並べて示し、うち3つを平均した[総合スコア]({ANCHOR['ja']})も付ける。",
    ])


def leading_group(facts, lang):
    """The first two by Overall, as a group: their gap is within the hard-case sampling uncertainty."""
    a, b = facts.ranked_overall()[:2]
    gap = facts.overall(a) - facts.overall(b)
    # A third of the half-width of each leader's 95% hard-case interval is what that pillar alone can move Overall.
    ci = {s: facts.hard_figure(s)["ci95"] for s in (a, b)}
    half = min(100 * (ci[s][1] - ci[s][0]) / 2 / 3 for s in (a, b))
    require(gap < half, "the first two systems by Overall are closer than the hard-case uncertainty can move them")
    n = hard_items(facts)
    nm = facts.name
    if lang == "en":
        return (f"{nm(a)} ({o1(facts.overall(a))}) and {nm(b)} ({o1(facts.overall(b))}) lead, {o1(gap)} points apart. "
                f"That gap is within the uncertainty of the {n} hard items, so the two form a leading group rather "
                f"than one winner.")
    return (f"先頭は{nm(a)}（{o1(facts.overall(a))}）と{nm(b)}（{o1(facts.overall(b))}）で、差は{o1(gap)}ポイント。"
            f"難しい例{n}件の不確かさの範囲内なので、どちらか一方を勝者とせず、先頭集団として扱います。")


def top_table(facts, lang, n=TOP_ROWS):
    """The first rows of the leaderboard: the top `n` systems by the Overall score."""
    en = lang == "en"
    rows = []
    for s in facts.ranked_overall()[:n]:
        ef = facts.judge.error_free(s)
        mem, sec = facts.memory(s), facts.seconds(s)
        local = facts.kind(s) == "local"
        comet = facts.comet(s) if facts.full(s) else facts.comet(s, "overall_measured")
        cells = [facts.name(s) + facts.coverage_mark(s),
                 ("Local" if en else "ローカル") if local else ("Cloud" if en else "クラウド"),
                 o1(facts.overall(s)), c4(comet), pct1(ef["error_free"]), pct1(facts.hard(s)),
                 f"{mem:.2f} GiB" if local and mem is not None else "—",
                 f"{sec:.2f} s" if local and sec is not None else "—"]
        rows.append("| " + " | ".join(cells) + " |")
    k, total = len(facts.ranked_overall()), facts.count_systems()
    if en:
        head = ("| System | Type | Overall ↑ | COMET-22 ↑ | Error-free ↑ | Hard cases ↑ | Peak memory | "
                "Per sentence |\n| --- | --- | --- | --- | --- | --- | --- | --- |")
        intro = (f"The top {words(n)} of the {k} systems with an [Overall score]({ANCHOR['en']}), the mean of "
                 f"COMET-22, the share of error-free translations and the pass rate on hard cases. All {total} systems "
                 f"are on the [leaderboard]({LEADERBOARD}).")
        note = ("Cloud systems received up to 25 sentences or 5 passages per request, and local models one item per "
                "request. Memory and time per sentence are shown for local systems only.")
    else:
        head = ("| 構成 | 種類 | 総合 ↑ | COMET-22 ↑ | 誤りなし ↑ | 難しい例 ↑ | ピークメモリ | 1文あたり |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- |")
        intro = (f"[総合スコア]({ANCHOR['ja']})を持つ{k}構成のうち、上位{n}構成を示します。総合スコアは、COMET-22、"
                 f"誤りのない訳の割合、難しい例の合格率の平均です。全{total}構成は[リーダーボード]({LEADERBOARD})に"
                 f"あります。")
        note = ("クラウド構成には1回の依頼で最大25文または文章5件をまとめて渡し、ローカルモデルには1件ずつ渡しました。"
                "メモリと1文あたりの時間はローカル構成だけに示します。")
    return intro + "\n\n" + head + "\n" + "\n".join(rows) + "\n\n" + leading_group(facts, lang) + "\n\n" + note


def finding_standard(facts, lang):
    """On COMET-22 the leading cloud systems and the best local system sit in one narrow band."""
    top = [s for s in facts.ranked_overall("cloud")][:10]
    require(top == facts.ranked_overall()[:10], "the ten systems with the highest Overall score are cloud systems")
    lo, hi = min(map(facts.comet, top)), max(map(facts.comet, top))
    local = facts.ranked("local")[0]
    require(lo <= facts.comet(local) <= hi, "the best local COMET-22 lies within the range of the top ten by Overall")
    nm = facts.name
    if lang == "en":
        return (f"**On the standard metric, cloud and local systems are close.** On COMET-22, the {words(len(top))} "
                f"systems with the highest Overall score, all cloud, lie between {c4(lo)} and {c4(hi)}. The best local "
                f"system on COMET-22, {nm(local)} ({c4(facts.comet(local))}), lies between them.")
    return (f"**標準的な指標では、クラウドとローカルの差は小さい。** "
            f"COMET-22で、総合スコア上位{len(top)}構成（すべてクラウド）は{c4(lo)}〜{c4(hi)}の範囲にある。COMET-22のローカル首位{nm(local)}（{c4(facts.comet(local))}）も"
            f"その範囲に入る。")


def finding_hard(facts, lang):
    """On hard cases the leading cloud systems pass 40% or more; every local system stays under 10%."""
    rates = {s: facts.hard(s) for s in facts.systems if facts.hard(s) is not None}
    cloud = sorted((s for s in rates if facts.kind(s) == "cloud" and rates[s] >= 0.40), key=lambda s: -rates[s])
    local = sorted((s for s in rates if facts.kind(s) == "local"), key=lambda s: -rates[s])
    require(len(cloud) >= 2, "several cloud systems pass 40% or more of the hard items")
    require(len(local) == facts.count_systems("local"), "every local system has a hard-cases score")
    require(rates[local[0]] < 0.10, "every local system passes fewer than 10% of the hard items")
    all_items = [facts.hard_block(s)["our_directions"]["pass_rate"] for s in local]
    require(max(all_items) < 0.10, "every local system passes fewer than 10% of all the hard items too")
    require(rates[REFERENCE] < 0.10, "DeepL API passes fewer than 10% of the hard items")
    n, nm = hard_items(facts), facts.name
    lo, hi = pct1(rates[cloud[-1]]), pct1(rates[cloud[0]])
    if lang == "en":
        return (f"**On hard cases, the gap is wide.** {words(len(cloud)).capitalize()} cloud systems pass 40% or more "
                f"of the {n} hard items ({lo} to {hi}). Every one of the {len(local)} local systems passes fewer than "
                f"10%, counted on all {n} items or only on those in the directions it covers; the best, "
                f"{nm(local[0])}, passes {pct1(rates[local[0]])}. {nm(REFERENCE)} passes "
                f"{pct1(rates[REFERENCE])}.")
    return (f"**難しい例では差が大きい。** "
            f"{n}件の難しい例で、クラウドの{len(cloud)}構成が40%以上（{lo}〜{hi}）に合格した。"
            f"ローカルは{len(local)}構成すべてが、{n}件全体で数えても対応する方向の項目だけで数えても10%未満で、"
            f"最も高い{nm(local[0])}でも{pct1(rates[local[0]])}。"
            f"{nm(REFERENCE)}は{pct1(rates[REFERENCE])}。")


def finding_local_vs_reference(facts, lang):
    """The top local system by Overall against DeepL API, pillar by pillar."""
    g, d = facts.ranked_overall("local")[0], REFERENCE
    require(facts.overall(g) > facts.overall(d), "the top local system is ahead of DeepL API on Overall")
    ef = {s: facts.judge.error_free(s)["error_free"] for s in (g, d)}
    require(facts.comet(g) < facts.comet(d), "the top local system's COMET-22 is below DeepL API's")
    require(ef[g] > ef[d] and facts.hard(g) > facts.hard(d),
            "the top local system has more error-free translations and passes more hard cases than DeepL API")
    nm = facts.name
    pairs = dict(o=(o1(facts.overall(g)), o1(facts.overall(d))), c=(c4(facts.comet(g)), c4(facts.comet(d))),
                 e=(pct1(ef[g]), pct1(ef[d])), h=(pct1(facts.hard(g)), pct1(facts.hard(d))))
    if lang == "en":
        v = {k: f"{a} against {b}" for k, (a, b) in pairs.items()}
        return (f"**The top local system on Overall, {nm(g)}, is ahead of {nm(d)}** ({v['o']}). Its COMET-22 is lower "
                f"({v['c']}), but more of its translations are error-free ({v['e']}) and it passes more hard cases "
                f"({v['h']}).")
    v = {k: f"{a}対{b}" for k, (a, b) in pairs.items()}
    return (f"**総合スコアでローカル首位の{nm(g)}は、{nm(d)}を上回る**（{v['o']}）。COMET-22は低い（{v['c']}）が、"
            f"誤りのない訳の割合（{v['e']}）と難しい例の合格率（{v['h']}）で上回る。")


def findings(facts, lang):
    parts = [finding_standard, finding_hard, finding_local_vs_reference]
    body = "\n".join(f"{i}. {fn(facts, lang)}" for i, fn in enumerate(parts, 1))
    note = (f"The pillars are defined under [Overall score]({ANCHOR['en']}). Results by direction are on the "
            f"[leaderboard]({LEADERBOARD})." if lang == "en" else
            f"3つの柱の定義は[総合スコア]({ANCHOR['ja']})にあります。方向別の結果は[リーダーボード]({LEADERBOARD})に"
            f"あります。")
    return body + "\n\n" + note


def second_verifier(facts):
    """(systems, agreement, items, largest gap in points, swapped pairs with their gap in items)."""
    second = facts.second
    primary, other = second["primary"], second["verifier"]["model"]
    systems = second["systems"]
    rate = {v: {s: e["passed"][v] / e["items"] for s, e in systems.items()} for v in (primary, other)}
    gap = max(100 * abs(rate[other][s] - rate[primary][s]) for s in systems)
    swaps = [abs(systems[a]["passed"][other] - systems[b]["passed"][other]) for a in systems for b in systems
             if a < b and (rate[primary][a] - rate[primary][b]) * (rate[other][a] - rate[other][b]) < 0]
    total = second["total"]
    return list(systems), total["agreed"] / total["items"], total["items"], gap, swaps


def coverage_shifts(facts):
    """How far COMET-22 x 100 of the systems with all 18 directions moves when only the directions of a partly
    covered system count: {coverage set: (systems, directions, mean shift, largest absolute shift)}."""
    from translate_bench import aggregate

    full = facts.ranked()
    out = {}
    for sid in facts.systems:
        if facts.full(sid) or facts.comet(sid, "overall_measured") is None:
            continue
        dirs = tuple(facts.release.tables[sid].directions())
        if dirs in {d for _, d, _, _ in out.values()}:
            out[next(k for k, v in out.items() if v[1] == dirs)][0].append(sid)
            continue
        shifts = [100 * (aggregate.score(facts.release.tables[f], "overall", list(dirs)) - facts.comet(f))
                  for f in full]
        out[sid] = ([sid], dirs, mean(shifts), max(map(abs, shifts)))
    return out


def group_name(facts, members, lang):
    """Several systems in a few words: "PLaMo 3 Translate 31B, 8B, 2B and 0.8B" for the sizes of one family."""
    from translate_bench.export.figures import SHORT_NAMES

    entries = [facts.systems[s] for s in members]
    joiner = (" and ", ", ") if lang == "en" else ("、", "、")
    if len(entries) > 1 and len({e["family"] for e in entries}) == 1 and all(e.get("size_label") for e in entries):
        sizes = [e["size_label"] for e in entries]
        listed = sizes[0] if len(sizes) == 1 else joiner[1].join(sizes[:-1]) + joiner[0] + sizes[-1]
        return f"{entries[0]['family']} {listed}"
    names = [SHORT_NAMES.get(e["name"], e["name"]).replace(",", "").split() for e in entries]
    common = []
    for parts in zip(*names):
        if len(set(parts)) > 1:
            break
        common.append(parts[0])
    if len(entries) > 1 and len(common) >= 2:
        label = " ".join(common)
        return (f"both {label} configurations" if len(entries) == 2 else f"the {words(len(entries))} {label} "
                "configurations") if lang == "en" else f"{label}の{len(entries)}構成"
    names = [" ".join(n) for n in names]
    return names[0] if len(names) == 1 else joiner[1].join(names[:-1]) + joiner[0] + names[-1]


def language_list(codes, lang):
    names = [schema.LANGUAGE_NAMES[c] for c in codes]
    if lang == "en":
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    ja = {"ja": "日本語", "zh-Hans": "中国語（簡体字）", "es": "スペイン語", "ko": "韓国語", "fr": "フランス語",
          "de": "ドイツ語", "pt-BR": "ポルトガル語（ブラジル）", "ar": "アラビア語", "id": "インドネシア語"}
    return "と".join(ja[c] for c in codes)


def overall_section(facts, lang):
    """The definition of the Overall score, its coverage rule, the LTB credit and the caveats."""
    data = facts.overall_data
    counts, rule = data["counts"], data["min_directions"]
    k, total = counts["overall"], counts["systems"]
    n, dirs = hard_items(facts), len(schema.DIRECTIONS)
    judge, verifier = facts.name(facts.judge.model), facts.hard_summary["verifier"]["name"]
    upstream = facts.hard_summary["verifier"]["upstream_name"]
    checked, agree, items, gap, swaps = second_verifier(facts)
    top = facts.ranked_overall()[:len(checked)]
    require(set(checked) == set(top) and all(facts.kind(s) == "cloud" for s in top),
            "the second verifier re-ran the systems with the highest Overall score, all cloud")
    require(facts.second["verifier"]["name"] == upstream, "the second verifier is the model LTB's leaderboard uses")
    require(len(swaps) <= 1, "the two verifiers order the re-run systems the same, but for one pair at most")
    second = facts.second["verifier"]["name"]
    partial = [s for s in facts.ranked_overall() if facts.coverage(s) < dirs]
    without = [s for s in facts.systems if facts.overall(s) is None]
    shifts = coverage_shifts(facts)
    kept = {k_: v for k_, v in shifts.items() if facts.overall(k_) is not None}
    dropped = {k_: v for k_, v in shifts.items() if facts.overall(k_) is None and v[1]}
    small = max(v[3] for v in kept.values())
    require(small < 0.5, "dropping a scored partial system's missing directions moves COMET-22 x 100 under 0.5")
    require(all(v[2] > 4 * small for v in dropped.values()), "the excluded coverage moves COMET-22 far more")
    sizes = sorted({len(v[1]) for v in kept.values()}, reverse=True)
    nm = facts.name
    families = {}
    for s in [x for x in facts.systems if x in partial]:  # registry order within a group
        families.setdefault(tuple(data["systems"][s]["missing_languages"]), []).append(s)
    if lang == "en":
        apart = "" if not swaps else f"{words(swaps[0])} item{'s' if swaps[0] > 1 else ''} apart"
        order = "the order stayed the same" + (f" except for two systems {apart}" if swaps else "")
        groups = "; ".join(f"{group_name(facts, members, 'en')} without {language_list(list(m), 'en')} "
                           f"({facts.coverage(members[0])}/{dirs})" for m, members in families.items())
        why = []
        for s in without:
            c = data["systems"][s]["directions"]["standard"]
            why.append(f"{nm(s)} ({c} directions with both text types)" if c else
                       f"{nm(s)} (no direction with both text types)")
        means = [v[2] for v in kept.values()]
        dropped_text = " and ".join(f"{nm(v[0][0])}'s {len(v[1])} directions" for v in dropped.values())
        return "\n".join([
            "The Overall score is the mean of three pillars, each on a 0–100 scale and weighted equally, rounded to "
            "one decimal:",
            "",
            f"- **Standard:** COMET-22 over the directions the system covers (all {dirs} for most), times 100.",
            f"- **Reliability:** the share of the LLM judge's sample in which {judge} marked no error, in percent.",
            f"- **Hard cases:** the pass rate on the {n} items of the [Last Translation Benchmark]({LTB_URL}) (LTB; "
            f"Zouhar et al., 2026, [arXiv:2609.04173]({LTB_PAPER}); data CC BY 4.0) whose direction is one of this "
            f"benchmark's, in percent. An item passes when the translation meets all of its handwritten rules, as "
            f"checked by {verifier}. These are not official LTB leaderboard numbers: they use a {n}-item subset in "
            f"this benchmark's directions and a different verifier ([protocol](results/ltb-v1/protocol.md)).",
            "",
            f"A system gets an Overall score when every pillar covers at least {rule} of the {dirs} directions: "
            f"{k} of the {total}. {words(counts['partial']).capitalize()} of them cover fewer than {dirs}: {groups}. "
            f"For these, each pillar is a mean over the directions the system covers, and the hard cases count only "
            f"the items in those directions. The leaderboard marks them with their coverage. "
            f"{' and '.join(why)} get no Overall score.",
            "",
            f"A mean over fewer directions is not the same test. Among the {len(facts.ranked())} systems with all "
            f"{dirs} directions, keeping only the {' or '.join(map(str, sizes))} directions of a system above moves "
            f"COMET-22 × 100 by at most {small:.2f} points (mean shift {signed(min(means))} to {signed(max(means))}); "
            f"keeping only {dropped_text} moves it by {max(v[2] for v in dropped.values()):.1f} points on average, "
            "which is why that system gets no Overall score. "
            "MetricX-24 stays a separate column and is not part of the Overall score, which has no interval. "
            "[`results/v1.1/overall.json`](results/v1.1/overall.json) holds every system's pillars and coverage, and "
            "`translate-bench verify` recomputes it.",
            "",
            f"**Caveats.** The LLM judge is {judge} and the hard-case verifier is {verifier}. The hard-case verdicts "
            f"of the {words(len(checked))} systems with the highest Overall score, all cloud, were re-run with "
            f"{second}, the verifier LTB uses: the two agreed on {100 * agree:.1f}% of {items:,} items, the pass rates "
            f"moved by at most {gap:.1f} points, and {order}. The judge pillar has no such second verifier.",
        ])
    order = ("順位も同じ" if not swaps else f"順位は{swaps[0]}件差の2構成が入れ替わったほかは同じ")
    groups = "、".join(f"{group_name(facts, members, 'ja')}（{language_list(list(m), 'ja')}なし、"
                       f"{facts.coverage(members[0])}/{dirs}）" for m, members in families.items())
    why = "と".join(f"{nm(s)}（文と文章の両方がそろう方向が{data['systems'][s]['directions']['standard']}）"
                    if data["systems"][s]["directions"]["standard"] else f"{nm(s)}（文と文章の両方がそろう方向がない）"
                    for s in without)
    means = [v[2] for v in kept.values()]
    dropped_text = "、".join(f"{nm(v[0][0])}の{len(v[1])}方向だけにすると平均{v[2]:.1f}ポイント"
                             for v in dropped.values())
    return "\n".join([
        "総合スコアは、0〜100に揃えた3つの柱を同じ重みで平均し、小数第1位に丸めたものです。",
        "",
        f"- **標準：** その構成が対応する方向（ほとんどは{dirs}方向すべて）のCOMET-22を100倍した値。",
        f"- **信頼性：** LLMによる判定の標本のうち、{judge}が誤りを1つも付けなかった訳の割合（%）。",
        f"- **難しい例：** [Last Translation Benchmark]({LTB_URL})（LTB。Zouhar et al., 2026、"
        f"[arXiv:2609.04173]({LTB_PAPER})、データはCC BY 4.0）のうち、"
        f"方向がこのベンチマークと重なる{n}件の合格率（%）。"
        f"訳文が手書きの規則をすべて満たすと合格で、判定は{verifier}が行う。LTBの公式リーダーボードの数値ではない。"
        f"このベンチマークの方向にある{n}件だけを使い、判定するモデルも異なる（[プロトコル](results/ltb-v1/protocol.md)）。",
        "",
        f"総合スコアは、3つの柱のどれもが{dirs}方向のうち{rule}方向以上に対応する構成に付けます（{total}構成中{k}構成）。"
        f"うち{counts['partial']}構成は{dirs}方向に満たない：{groups}。これらの柱は対応する方向だけの平均で、"
        "難しい例もその方向の項目だけで数えます。リーダーボードでは対応する方向の数を添えて示します。"
        f"{why}には総合スコアがありません。",
        "",
        f"方向が少ない平均は、同じ試験ではありません。{dirs}方向すべてに対応した{len(facts.ranked())}構成で、"
        f"上の構成と同じ{'・'.join(map(str, sizes))}方向だけに絞ると、COMET-22×100は最大{small:.2f}ポイント"
        f"（平均で{signed(min(means))}〜{signed(max(means))}）動きます。"
        f"{dropped_text}動くため、その構成には総合スコアを付けません。"
        "MetricX-24は別の列として示し、総合スコアには含めません。総合スコアに区間はありません。各構成の柱の値と対応する方向の数は"
        "[`results/v1.1/overall.json`](results/v1.1/overall.json) にあり、`translate-bench verify` が計算し直します。",
        "",
        f"**注意点：** LLMによる判定は{judge}、難しい例の判定は{verifier}が行っています。"
        f"総合スコア上位{len(checked)}構成"
        f"（すべてクラウド）の難しい例は、LTBが使う{second}でも判定し直しました。{items:,}件のうち{100 * agree:.1f}%で"
        f"判定が一致し、合格率の差は{gap:.1f}ポイント以内、{order}でした。LLMによる判定の柱には、このような2つ目の判定はありません。",
    ])


def lead_caption(facts, lang):
    """The lead figure with its alt text and caption: the Overall score and its three pillars."""
    k, n, dirs = len(facts.ranked_overall()), hard_items(facts), len(schema.DIRECTIONS)
    if lang == "en":
        return (f"![The Overall score and its three pillars for the {k} systems with an Overall score]"
                f"(figures/lead.svg)\n\n*The {k} systems with an Overall score, sorted by it (blue: local, orange: "
                f"cloud). Left to right, on one 0–100 scale: the Overall score, then its three pillars: "
                f"COMET-22 × 100, the share of error-free translations, and the pass rate on the {n} hard cases. "
                f"A system below {dirs} directions carries its coverage, such as (16/{dirs}), and is scored over the "
                f"directions it covers.*")
    return (f"![総合スコアを持つ{k}構成の、総合スコアと3つの柱](figures/lead.svg)\n\n"
            f"*総合スコアを持つ{k}構成を、その順に並べた（青：ローカル、橙：クラウド）。左から、同じ0〜100の目盛りで、"
            f"総合スコア、その3つの柱であるCOMET-22×100、誤りのない訳の割合、難しい例{n}件の合格率。"
            f"{dirs}方向に満たない構成には（16/{dirs}）のように対応する方向の数を添え、その方向だけで計算した。*")


def metrics_table(facts, lang):
    full = facts.ranked()
    local = [s for s in full if facts.kind(s) == "local"]
    cloud = [s for s in full if facts.kind(s) == "cloud"]
    en = lang == "en"

    def best(pool, value, low=False):
        """The leaders of a pool; several when they tie on the published value."""
        pool = [s for s in pool if value(s) is not None]
        top = min(map(value, pool)) if low else max(map(value, pool))
        return [s for s in pool if value(s) == top]

    judge = facts.judge
    judge_name = facts.name(judge.model)
    verifier = facts.hard_summary["verifier"]["name"]
    n = hard_items(facts)
    vs = lambda s: (judge.versus_reference(s) or {}).get("preferred")  # noqa: E731
    ef = lambda s: (judge.error_free(s) or {}).get("error_free") if s != REFERENCE else None  # noqa: E731
    done = lambda s: facts.block(s)["completion"]["rate"]  # noqa: E731
    roles = ([f"Mean of COMET-22 × 100, error-free % and hard-case pass % ([Overall score]({ANCHOR['en']}))",
              "Learned metric that compares the output with a reference translation",
              "A second learned metric of the same kind, as an error score",
              f"Share of non-tied items where the LLM judge ({judge_name}) preferred the system to DeepL API",
              "Share of items where the LLM judge marked no error",
              f"Share of {n} hard items (Last Translation Benchmark) that meet all their handwritten rules, checked by "
              f"{verifier}",
              "Character and word overlap with the reference",
              "Share of attempted items that received a score"] if en else
             [f"COMET-22×100、誤りなしの割合、難しい例の合格率の平均（[総合スコア]({ANCHOR['ja']})）",
              "訳文を参照訳と比べる学習済みの指標", "同じ種類のもう1つの学習済み指標（誤りの大きさを表す）",
              f"LLMによる判定（{judge_name}）でDeepL APIより良いとされた割合（引き分けを除く）",
              "LLMによる判定で誤りが1つも付かなかった訳の割合",
              f"難しい例{n}件（Last Translation Benchmark）のうち、手書きの規則をすべて満たした割合"
              f"（{verifier}が判定）",
              "参照訳との文字・単語の重なり", "依頼した項目のうち、スコアが付いた項目の割合"])
    names = [("Overall ↑" if en else "総合 ↑", facts.overall, False, o1),
             ("COMET-22 ↑", lambda s: facts.comet(s), False, c4),
             ("MetricX-24 ↓", lambda s: facts.metricx(s), True, lambda x: f"{x:.3f}"),
             ("Judge vs DeepL API ↑" if en else "判定（対DeepL API）↑", vs, False, pct),
             ("Error-free ↑" if en else "誤りなし ↑", ef, False, pct),
             ("Hard cases ↑" if en else "難しい例 ↑", facts.hard, False, pct1),
             ("chrF++ ↑", lambda s: facts.chrf(s), False, lambda x: f"{x:.2f}")]
    rows = []
    for (name, value, low, fmt), role in zip(names, roles):
        cells = []
        for pool in (local, cloud):
            leaders = best(pool, value, low)
            cells.append(f"{', '.join(facts.name(s) for s in leaders)} ({fmt(value(leaders[0]))})")
        rows.append(f"| {name} | {role} | {cells[0]} | {cells[1]} |")
    cells = []
    for pool in (local, cloud):
        complete = sum(done(s) == 1 for s in pool)
        low = 100 * min(map(done, pool))
        cells.append(f"{complete} of {len(pool)} at 100% (lowest {low:.1f}%)" if en else
                     f"{len(pool)}構成中{complete}構成が100%（最低{low:.1f}%）")
    rows.append(f"| {'Completion ↑' if en else '完了率 ↑'} | {roles[-1]} | {cells[0]} | {cells[1]} |")
    if en:
        head = "| Metric | What it measures | Best local | Best cloud |\n| --- | --- | --- | --- |"
        note = (f"Best among the {len(full)} systems that cover all 18 directions ({len(local)} local, {len(cloud)} "
                f"cloud).")
    else:
        head = "| 指標 | 測っているもの | ローカル首位 | クラウド首位 |\n| --- | --- | --- | --- |"
        note = f"18方向すべてに対応した{len(full)}構成（ローカル{len(local)}、クラウド{len(cloud)}）の中での首位。"
    return head + "\n" + "\n".join(rows) + "\n\n" + note


def more_captions(facts, lang):
    nfam = len({s["family"] for s in facts.summary["size_steps"]})
    local_mem = [s for s in facts.ranked("local") if facts.memory(s) is not None]
    full = facts.ranked()
    top = facts.name(facts.ranked("cloud")[0])
    systems, n = len(facts.hard_summary["systems"]), hard_items(facts)
    verifier = facts.hard_summary["verifier"]["name"]
    if lang == "en":
        return "\n\n".join([
            f"![Pass rate on the {n} hard cases for all {systems} systems](figures/hard-cases.svg)",
            f"*Pass rate on the {n} hard cases from the Last Translation Benchmark for all {systems} systems, with "
            f"its 95% interval over items (blue: local, orange: cloud). {verifier} checks the rules. A system below "
            f"18 directions carries its coverage, such as (16/18), and is scored on the items in the directions it "
            f"covers.*",
            f"![COMET-22 by total parameters for {nfam} local model families](figures/size-quality.svg)",
            f"*COMET-22 by total parameter count (log scale) for the {nfam} local families measured at more than one "
            f"size. Hollow points (PLaMo 3 Translate) average 16 directions, because it has no Brazilian Portuguese. "
            f"The horizontal lines mark {top} and DeepL API.*",
            f"![COMET-22 against peak memory for {len(local_mem)} local systems](figures/quality-memory.svg)",
            f"*COMET-22 against peak memory of the inference process (log scale) for {len(local_mem)} local systems. "
            f"The line is the Pareto frontier. Apple's on-device systems are left out: they run in system services, "
            f"so no peak was measured.*",
            f"![COMET-22 against MetricX-24 for {len(full)} systems](figures/metric-disagreement.svg)",
            f"*COMET-22 against MetricX-24 for the {len(full)} systems that cover all 18 directions. The MetricX-24 "
            f"axis is reversed, so up and right are both better.*",
        ])
    return "\n\n".join([
        f"![全{systems}構成の、難しい例{n}件の合格率](figures/hard-cases.svg)",
        f"*全{systems}構成の、Last Translation Benchmarkの難しい例{n}件の合格率と、項目についての95%区間"
        f"（青：ローカル、橙：クラウド）。規則の判定は{verifier}が行う。18方向に満たない構成には（16/18）のように"
        f"対応する方向の数を添え、その方向の項目だけで計算した。*",
        f"![ローカルモデル{nfam}系列の総パラメータ数とCOMET-22](figures/size-quality.svg)",
        f"*複数のサイズを測ったローカル{nfam}系列の、総パラメータ数（対数軸）とCOMET-22。"
        f"白抜きの点（PLaMo 3 Translate）は、ポルトガル語（ブラジル）に対応しないため16方向の平均。"
        f"横線は{top}とDeepL API。*",
        f"![ローカル{len(local_mem)}構成のピークメモリとCOMET-22](figures/quality-memory.svg)",
        f"*ローカル{len(local_mem)}構成の、推論プロセスのピークメモリ（対数軸）とCOMET-22。線はパレート境界。"
        f"Appleの端末内システムはシステムサービスで動き、ピークメモリを測定していないため除いた。*",
        f"![{len(full)}構成のCOMET-22とMetricX-24](figures/metric-disagreement.svg)",
        f"*18方向すべてに対応した{len(full)}構成の、COMET-22とMetricX-24。MetricX-24の軸は反転してあり、"
        f"上と右がどちらも良い。*",
    ])


README_BLOCKS = {"counts": counts, "top": top_table, "findings": findings, "overall": overall_section,
                 "lead-caption": lead_caption, "metrics": metrics_table, "figures": more_captions}


# Files ----------------------------------------------------------------------------------------------------

def fill(text, render):
    """Replace every generated block of `text`; returns the new text and the block names."""
    names = []

    def sub(m):
        names.append(m.group(2))
        body = render(m.group(2)).rstrip("\n") + "\n"
        return m.group(1) + body + m.group(4)

    return BLOCK.sub(sub, text), names


def blocks(text):
    return {m.group(2): m.group(3) for m in BLOCK.finditer(text)}


def ranks(values, low=False):
    order = sorted((v, i) for i, v in enumerate(values) if v is not None)
    if not low:
        order = sorted(order, key=lambda x: -x[0])
    out = [None] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and order[j + 1][0] == order[i][0]:
            j += 1
        for k in range(i, j + 1):
            out[order[k][1]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    ra, rb = ranks([x for x, _ in pairs]), ranks([y for _, y in pairs])
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den, len(pairs)


def correlations(facts):
    """Spearman rank correlation between the measures over the systems with all 18 directions."""
    full = facts.ranked()
    judge = facts.judge
    ref = facts.name(REFERENCE)
    measures = [
        ("COMET-22", [facts.comet(s) for s in full]),
        ("MetricX-24", [-facts.metricx(s) for s in full]),
        ("MetricX-24 QE", [-facts.metricx(s, "qe") for s in full]),
        ("chrF++", [facts.chrf(s) for s in full]),
        (f"Judge vs {ref}", [None if s == REFERENCE else judge.versus_reference(s)["preferred"] for s in full]),
        ("Error-free", [(judge.error_free(s) or {}).get("error_free") for s in full]),
        *([("Hard cases", [facts.hard(s) for s in full])] if facts.hard_summary else []),
    ]
    head = "| | " + " | ".join(name for name, _ in measures) + " |"
    lines = [head, "| --- |" + " ---: |" * len(measures)]
    for name, a in measures:
        cells = [f"{spearman(a, b)[0]:.2f}" for _, b in measures]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    n = len(full)
    local = sum(facts.kind(s) == "local" for s in full)
    return ("\n".join(lines) + f"\n\n{n} systems ({local} local, {n - local} cloud). The judge column leaves out "
            f"{ref} itself ({n - 1} systems). 1.00 means the same order.")


def passages_metricx(facts):
    full = facts.ranked()
    llms = [s for s in facts.ranked("cloud") if s != REFERENCE]
    mx = lambda s, view: facts.metricx(s, "ref", view)  # noqa: E731
    best_p = min(llms, key=lambda s: mx(s, "passage"))
    best_s = min(llms, key=lambda s: mx(s, "sentence"))
    ahead = sorted((s for s in full if s not in llms and mx(s, "passage") < mx(best_p, "passage")),
                   key=lambda s: mx(s, "passage"))
    require(ahead, "some systems beat every GPT, Claude and Gemini system on passage MetricX-24")
    require(all(mx(s, "sentence") > mx(best_s, "sentence") for s in ahead),
            "on sentences the best GPT, Claude or Gemini system is ahead of those systems")
    names = ", ".join(f"{facts.name(s)} ({mx(s, 'passage'):.3f})" for s in ahead)
    return (f"On the passages, MetricX-24 scores {len(ahead)} systems better than every GPT, Claude and Gemini system "
            f"with all 18 directions (the best of those, {facts.name(best_p)}, scores {mx(best_p, 'passage'):.3f}): "
            f"{names}. On single sentences the order turns: {facts.name(best_s)} ({mx(best_s, 'sentence'):.3f}) is "
            f"ahead of all {len(ahead)}.")


def decoding(system):
    g = system.get("generation") or {}
    if system["kind"] == "cloud":
        return "service default" if g else "none (translation API)"
    if "strategy" in g:
        return f"framework ({g['strategy']})"
    if g.get("sampling") == "greedy" or g.get("temperature") == 0:
        return "greedy"
    parts = [f"T {g['temperature']}"] + [f"{k.replace('_', '-')} {'off' if g[k] == -1 else g[k]}"
                                          for k in ("top_p", "top_k") if k in g]
    return "sampled (" + ", ".join(parts) + ")"


def systems_table(facts):
    lines = ["| System | Kind | Runtime or client | Directions | Not supported | Items per request | "
             "Concurrent requests | Reasoning | Decoding | Completion |",
             "| --- | --- | --- | ---: | --- | --- | ---: | --- | --- | ---: |"]
    for sid, s in facts.systems.items():
        block = facts.block(sid)
        both = block["overall_measured_directions"]
        dirs = {k: len(v) for k, v in block["directions"].items()}
        cover = str(both) if dirs["sentence"] == dirs["passage"] == both else \
            f"{both} (sentences {dirs['sentence']}, passages {dirs['passage']})"
        unsupported = s.get("unsupported_languages")
        if unsupported is None:
            missing = "see note" if s.get("support_note") else "—"
        else:
            missing = ", ".join(schema.LANGUAGE_NAMES[x] for x in unsupported) or "—"
        mode = s.get("request_mode") or {}
        per = mode.get("items_per_request")
        per = f"{per['sentence']} / {per['passage']}" if isinstance(per, dict) else f"{per} / {per}"
        runtime = (s.get("client") or {}).get("name") or (s.get("runtime") or {}).get("name") or ""
        quant = (s.get("weights") or {}).get("quantization")
        if quant:
            runtime += ", " + quant.removeprefix(runtime + " ")
        c = block["completion"]
        share = f"{100 * c['rate']:.1f}" if f"{100 * c['rate']:.1f}" != "100.0" else f"{100 * c['rate']:.2f}"
        done = "100%" if c["rate"] == 1 else f"{share}% ({c['attempted'] - c['scored']} failed)"
        reasoning = s.get("reasoning") or ("none" if s["kind"] == "cloud" else "off")
        lines.append(f"| {s['name']} | {s['kind']} | {runtime} | {cover} | {missing} | {per} | "
                     f"{mode.get('concurrent_requests') or '—'} | {reasoning} | {decoding(s)} | "
                     f"{done} |")
    notes = [f"{facts.name(sid)}: {s['support_note']}" for sid, s in facts.systems.items() if s.get("support_note")]
    for sid, s in facts.systems.items():
        if not facts.block(sid)["directions"]["passage"] and s.get("passage_sets_attempted"):
            sets = " and ".join(s["passage_sets_attempted"])
            notes.append(f"{facts.name(sid)}: passages only from {sets}, so it has no complete 20-passage cell. Its "
                         f"sentences cover {len(facts.block(sid)['directions']['sentence'])} directions.")
    return "\n".join(lines) + ("\n\n" + " ".join(notes) if notes else "")


def render_file(facts, kind):
    if kind == "methodology":
        return lambda name: {"systems": systems_table}[name](facts)
    if kind == "metrics":
        return lambda name: {"correlations": correlations, "passages": passages_metricx}[name](facts)
    return lambda name: README_BLOCKS[name](facts, kind)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="the translate-bench checkout (default: found from here)")
    parser.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    args = parser.parse_args(argv)
    root = schema.find_root(args.root)
    facts = Facts(root)
    stale = []
    for rel, kind in FILES.items():
        path = root / rel
        if not path.is_file():
            stale.append(f"{rel}: missing")
            continue
        old = path.read_text(encoding="utf-8")
        new, names = fill(old, render_file(facts, kind))
        if not names:
            stale.append(f"{rel}: no generated blocks")
        if new != old:
            if args.check:
                before, after = blocks(old), blocks(new)
                changed = [n for n in names if before.get(n) != after.get(n)]
                stale.append(f"{rel}: generated text differs from the results ({', '.join(changed)})")
            else:
                path.write_text(new, encoding="utf-8")
                print(f"updated {rel} ({', '.join(names)})")
    if args.check:
        for line in stale:
            print(line)
        print(f"README numbers: {'differ from the results' if stale else 'match the results'}")
        return 1 if stale else 0
    for line in stale:
        print(line)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
