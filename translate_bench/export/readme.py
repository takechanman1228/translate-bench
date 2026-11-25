"""Fill the generated parts of README.md, README.ja.md, docs/metrics.md and docs/methodology.md from results/v1/.

    python -m translate_bench.export.readme          # rewrite the generated blocks
    python -m translate_bench.export.readme --check  # exit 1 if a generated block differs from the results

A generated block sits between `<!-- tb:NAME -->` and `<!-- /tb:NAME -->`; the text around it is
written by hand. Every number in a block comes from the published files through `facts.Facts`, and
a comparison word ("above", "not resolved") follows the paired 95% interval, so a change in the results
either changes the sentence or, for a claim the wording cannot follow, stops the generator.
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
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
                11: "eleven", 12: "twelve"}


# Formatting -----------------------------------------------------------------------------------------------

def c4(x):
    return f"{x:.4f}"


def pct(x):
    return f"{100 * x:.0f}%"


def relation(facts, a, b):
    """"above", "level" or "below": how a compares with b on COMET-22 overall, by the paired 95% interval."""
    lo, hi = facts.paired(a, b)["ci95"]
    return "above" if lo > 0 else "below" if hi < 0 else "level"


def clause(lang, subject, pairs):
    """One sentence on how `subject` compares with each target: "X beats A and B, and ties C."

    `pairs` is [(relation, target)]; a "level" pair (the paired 95% interval includes zero) is a tie."""
    groups = [(rel, [t for r, t in pairs if r == rel]) for rel in ("above", "level", "below")]
    groups = [(rel, ts) for rel, ts in groups if ts]
    if lang == "en":
        verb = {"above": "beats", "level": "ties", "below": "is below"}
        parts = [f"{verb[rel]} {' and '.join(ts)}" for rel, ts in groups]
        joiner = ", and " if any(len(ts) > 1 for _, ts in groups) else " and "
        return f"{subject} {joiner.join(parts)}."
    mid = {"above": "を上回り", "level": "と同等で", "below": "を下回り"}
    end = {"above": "を上回る", "level": "と同等", "below": "を下回る"}
    parts = ["と".join(ts) + (end if i == len(groups) - 1 else mid)[rel] for i, (rel, ts) in enumerate(groups)]
    return f"{subject}は{'、'.join(parts)}。"


# README blocks --------------------------------------------------------------------------------------------

def counts(facts, lang):
    n, full = facts.count_systems(), len(facts.ranked())
    local, cloud = facts.count_systems("local"), facts.count_systems("cloud")
    dirs = len(schema.DIRECTIONS)
    sent, pas = schema.CELL_SIZE["sentence"], schema.CELL_SIZE["passage"]
    items = dirs * (sent + pas)
    if lang == "en":
        return "\n".join([
            f"- **Systems:** {n} configurations ({local} local, {cloud} cloud). {full} cover all {dirs} directions.",
            f"- **Test set:** {dirs} directions between English and 9 languages. Each has {sent} news sentences and "
            f"{pas} longer passages ({items:,} items in total).",
            "- **Hardware:** local models ran on one Apple M6 with 32 GiB of memory.",
            "- **Quality:** COMET-22, MetricX-24 and an LLM judge, reported side by side. There is no combined score.",
        ])
    return "\n".join([
        f"- **構成：** {n}（ローカル{local}、クラウド{cloud}）。うち{full}構成が{dirs}方向すべてに対応。",
        f"- **評価データ：** 英語と9言語の間の{dirs}方向。各方向にニュース文{sent}文と長めの文章{pas}件"
        f"（合計{items:,}件）。",
        "- **実行環境：** ローカルモデルはメモリ32 GiBのApple M6 1台で実行。",
        "- **品質の指標：** COMET-22、MetricX-24、LLMによる判定。1つのスコアにはまとめず、並べて示す。",
    ])


def top_table(facts, lang, n=5):
    """The first rows of the leaderboard: the top `n` cloud and local systems by COMET-22."""
    judge = facts.judge
    en = lang == "en"
    rows = []
    for kind in ("cloud", "local"):
        for s in facts.ranked(kind)[:n]:
            vs = judge.versus_reference(s)
            ef = judge.error_free(s)
            mem, sec = facts.memory(s), facts.seconds(s)
            local = kind == "local"
            cells = [facts.name(s),
                     {"cloud": "Cloud" if en else "クラウド", "local": "Local" if en else "ローカル"}[kind],
                     c4(facts.comet(s)), f"{facts.metricx(s):.3f}",
                     ("baseline" if en else "基準") if s == REFERENCE else pct(vs["preferred"]) if vs else "—",
                     pct(ef["error_free"]) if ef else "—",
                     f"{mem:.2f} GiB" if local and mem is not None else "—",
                     f"{sec:.2f} s" if local and sec is not None else "—"]
            rows.append("| " + " | ".join(cells) + " |")
    full = len(facts.ranked())
    total = facts.count_systems()
    url = "https://takechanman1228.github.io/translate-bench/"
    if en:
        head = ("| System | Type | COMET-22 ↑ | MetricX-24 ↓ | Judge vs DeepL API ↑ | Error-free ↑ | Peak memory | "
                "Per sentence |\n| --- | --- | --- | --- | --- | --- | --- | --- |")
        intro = (f"The top {NUMBER_WORDS[n]} cloud and top {NUMBER_WORDS[n]} local systems by COMET-22, among the "
                 f"{full} that cover all 18 directions. All {total} are on the [leaderboard]({url}).")
        note = ("Cloud systems received up to 25 sentences or 5 passages per request, and local models one item per "
                "request. Memory and time per sentence are shown for local systems only.")
    else:
        head = ("| 構成 | 種類 | COMET-22 ↑ | MetricX-24 ↓ | 判定（対DeepL API）↑ | 誤りなし ↑ | ピークメモリ | "
                "1文あたり |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- |")
        intro = (f"18方向すべてに対応した{full}構成のうち、COMET-22の上位{n}構成を"
                 f"クラウドとローカルそれぞれで示します。"
                 f"全{total}構成は[リーダーボード]({url})にあります。")
        note = ("クラウド構成には1回の依頼で最大25文または文章5件をまとめて渡し、ローカルモデルには1件ずつ渡しました。"
                "メモリと1文あたりの時間はローカル構成だけに示します。")
    return intro + "\n\n" + head + "\n" + "\n".join(rows) + "\n\n" + note


def finding_small_models(facts, lang):
    small, small2 = "index-translate-2b", "hy-mt2-7b"
    general_small = ["qwen3.5-9b", "gemma-4-e4b-it"]
    general_large = ["qwen3.5-27b", "gemma-4-31b-it"]
    cloud = "claude-haiku-5-5"
    pairs = [(small, g) for g in general_small] + [(small2, g) for g in general_large]
    for a, b in pairs:
        require(relation(facts, a, b) != "below", f"{facts.name(a)} is not below {facts.name(b)} on COMET-22")
    ratios = [facts.systems[b]["parameters"] / facts.systems[a]["parameters"] for a, b in pairs]
    lo, hi = min(ratios), max(ratios)
    require(lo >= 2, "the general models are at least twice the size")
    en = lang == "en"
    t = {s: f"{facts.name(s)} ({c4(facts.comet(s))})" if en else f"{facts.name(s)}（{c4(facts.comet(s))}）"
         for s in [small, small2, *general_small, *general_large, cloud]}
    first = clause(lang, t[small], [(relation(facts, small, g), t[g]) for g in [*general_small, cloud]])
    second = clause(lang, t[small2], [(relation(facts, small2, g), t[g]) for g in general_large])
    if en:
        return (f"**Small translation models match general models {lo:.1f} to {hi:.1f} times their size.** "
                f"On COMET-22, {first} {second[:-1]} ([figure](figures/size-quality.svg)).")
    return (f"**翻訳専用の小さなモデルは、{lo:.1f}〜{hi:.1f}倍大きい汎用モデルに並ぶ。** "
            f"COMET-22で、{first}{second[:-1]}（[図](figures/size-quality.svg)）。")


def finding_measures(facts, lang):
    """COMET-22, MetricX-24 and the judge on the local-to-cloud gap: only what the intervals support."""
    local, cloud = facts.ranked("local")[0], facts.ranked("cloud")[0]
    ref = REFERENCE
    gap = facts.paired(cloud, local)
    require(gap["ci95"][0] > 0, "the top cloud system is above the top local system on COMET-22")
    mx_local, mx_cloud = facts.metricx(local), facts.metricx(cloud)
    require(facts.paired_metricx(local, cloud)["ci95"][1] < 0,
            "MetricX-24 puts the top local system ahead of the top cloud system, beyond the paired interval")
    judge = facts.judge
    pref = {s: judge.versus_reference(s) for s in facts.systems if s != ref}
    pref = {s: v for s, v in pref.items() if v}
    clouds = [s for s in pref if facts.kind(s) == "cloud"]
    locals_ = sorted((s for s in pref if facts.kind(s) == "local"), key=lambda s: -pref[s]["preferred"])
    above = [s for s in clouds if pref[s]["net_95"][0] > 0]
    require(len(above) >= 2, "several cloud systems are preferred to DeepL API")
    require(all(pref[s]["net_95"][1] < 0 for s in locals_), "every local system's net interval is below zero")
    full = set(facts.ranked())
    top_local = next(s for s in locals_ if s in full)
    require(pref[cloud]["net_95"][0] > 0, "the top cloud system is preferred to DeepL API")
    nm = facts.name
    d = f"{abs(gap['delta']):.4f}"
    share = {s: pct(pref[s]["preferred"]) for s in (cloud, local, top_local)}
    if lang == "en":
        return (f"**The best local model is within {d} COMET-22 of the best cloud model, but far behind it on the "
                f"LLM judge.** {nm(local)} scores {c4(facts.comet(local))} against {c4(facts.comet(cloud))} for "
                f"{nm(cloud)}, and is ahead on MetricX-24 ({mx_local:.3f} against {mx_cloud:.3f}, lower is better). "
                f"The judge preferred {nm(cloud)} to {nm(ref)} on {share[cloud]} of non-tied items, and {nm(local)} "
                f"on {share[local]}. {NUMBER_WORDS.get(len(above), len(above)).capitalize()} cloud systems beat "
                f"{nm(ref)} on the judge. No local system does. Among those with all 18 directions, "
                f"{nm(top_local)} comes closest at {share[top_local]}.")
    return (f"**ローカル首位は、COMET-22でクラウド首位と{d}差。ただしLLMによる判定では大きく離される。** "
            f"{nm(local)}は{c4(facts.comet(local))}、{nm(cloud)}は{c4(facts.comet(cloud))}。"
            f"MetricX-24では{nm(local)}が上（{mx_local:.3f}対{mx_cloud:.3f}、低いほど良い）。"
            f"判定で{nm(ref)}より良いとされた割合（引き分けを除く）は、{nm(cloud)}が{share[cloud]}、"
            f"{nm(local)}が{share[local]}。{nm(ref)}を上回ったのはクラウドの{len(above)}構成で、ローカルにはない。"
            f"18方向すべてに対応したローカル構成で最も近いのは、{nm(top_local)}の{share[top_local]}。")


def finding_memory(facts, lang):
    four, eight, top = (facts.choice(r) for r in ("within-4-gib", "within-8-gib", "any-memory"))
    require(four["versus_leader"]["ci95"][1] < 0 and eight["versus_leader"]["ci95"][1] < 0,
            "the 4 and 8 GiB choices are below the leader")
    share = eight["memory"] / top["memory"]
    require(0.30 <= share <= 0.37, "the 8 GiB choice uses about a third of the leader's memory")
    n = {c["rule"]: facts.name(c["system"]) for c in (four, eight, top)}
    d8 = f"{abs(eight['versus_leader']['delta']):.4f}"
    if lang == "en":
        return (f"**{n['within-8-gib']} comes within {d8} COMET-22 of the best local model on about a third of the "
                f"memory.** It scores {c4(eight['score'])} at a peak of {eight['memory']:.2f} GiB, against "
                f"{c4(top['score'])} at {top['memory']:.2f} GiB for {n['any-memory']}. Under 4 GiB, "
                f"{n['within-4-gib']} scores {c4(four['score'])} at {four['memory']:.2f} GiB "
                f"([figure](figures/quality-memory.svg)).")
    return (f"**{n['within-8-gib']}は、約3分の1のメモリでローカル首位とCOMET-22が{d8}差。** "
            f"ピーク{eight['memory']:.2f} GiBで{c4(eight['score'])}。首位の{n['any-memory']}は"
            f"{top['memory']:.2f} GiBで{c4(top['score'])}。4 GiB以内では{n['within-4-gib']}が"
            f"{four['memory']:.2f} GiBで{c4(four['score'])}（[図](figures/quality-memory.svg)）。")


def finding_moe(facts, lang):
    moe, dense = "hy-mt2-30b-a3b", "hy-mt2-7b"
    require(facts.systems[moe]["mixture_of_experts"], "Hy-MT2 30B-A3B is a mixture-of-experts model")
    require(not facts.systems[dense].get("mixture_of_experts"), "Hy-MT2 7B is a dense model")
    s = {k: (facts.seconds(moe, k), facts.seconds(dense, k)) for k in schema.TYPES}
    require(all(1.8 <= b / a <= 2.2 for a, b in s.values()),
            "the mixture-of-experts model is about twice as fast per sentence and per passage")
    ratio = facts.memory(moe) / facts.memory(dense)
    total = facts.systems[moe]["parameters"] / 1e9
    n = {x: facts.name(x) for x in (moe, dense)}
    sent = s["sentence"]
    if lang == "en":
        return (f"**The {total:.0f}B mixture-of-experts model is about twice as fast as the 7B dense model.** "
                f"{n[moe]} activates about 3B of its {total:.0f}B parameters per token. It translates a sentence in "
                f"{sent[0]:.2f} s, against {sent[1]:.2f} s for {n[dense]}, and uses {ratio:.1f} times the memory.")
    return (f"**{total:.0f}BのMixture-of-Expertsモデルは、MoEではない7Bのモデルより約2倍速い。** "
            f"{n[moe]}が1トークンあたりに使うのは、{total:.0f}Bのパラメータのうち約3B。"
            f"1文の翻訳は{sent[0]:.2f}秒で、{n[dense]}は{sent[1]:.2f}秒。メモリは{ratio:.1f}倍使う。")


def findings(facts, lang):
    parts = [finding_small_models, finding_measures, finding_memory, finding_moe]
    body = "\n".join(f"{i}. {fn(facts, lang)}" for i, fn in enumerate(parts, 1))
    note = ("\"Ties\" means the paired 95% interval of the difference includes zero "
            "([Reading the metrics](docs/metrics.md)). Results by direction are on the "
            "[leaderboard](https://takechanman1228.github.io/translate-bench/)." if lang == "en" else
            "「同等」は、差の対応のある95%区間がゼロを含むことを指します（[指標の読み方](docs/metrics.md)）。"
            "方向別の結果は[リーダーボード](https://takechanman1228.github.io/translate-bench/)にあります。")
    return body + "\n\n" + note


def lead_caption(facts, lang):
    n = len(facts.ranked())
    ref = facts.name(REFERENCE)
    if lang == "en":
        return (f"*The {n} systems that cover all 18 directions, sorted by COMET-22 (blue: local, orange: cloud). "
                f"Left to right: COMET-22 (higher is better), MetricX-24 (lower is better), and the share of "
                f"non-tied items where the LLM judge preferred the system to {ref}.*")
    return (f"*18方向すべてに対応した{n}構成を、COMET-22の順に並べた（青：ローカル、橙：クラウド）。左から、COMET-22"
            f"（高いほど良い）、MetricX-24（低いほど良い）、LLMによる判定で{ref}より良いとされた割合（引き分けを除く）。*")


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
    vs = lambda s: (judge.versus_reference(s) or {}).get("preferred")  # noqa: E731
    ef = lambda s: (judge.error_free(s) or {}).get("error_free") if s != REFERENCE else None  # noqa: E731
    done = lambda s: facts.block(s)["completion"]["rate"]  # noqa: E731
    roles = (["Learned metric that compares the output with a reference translation",
              "A second learned metric of the same kind, as an error score",
              f"Share of non-tied items where the LLM judge ({judge_name}) preferred the system to DeepL API",
              "Share of items where the LLM judge marked no error",
              "Character and word overlap with the reference",
              "Share of attempted items that received a score"] if en else
             ["訳文を参照訳と比べる学習済みの指標", "同じ種類のもう1つの学習済み指標（誤りの大きさを表す）",
              f"LLMによる判定（{judge_name}）でDeepL APIより良いとされた割合（引き分けを除く）",
              "LLMによる判定で誤りが1つも付かなかった訳の割合",
              "参照訳との文字・単語の重なり", "依頼した項目のうち、スコアが付いた項目の割合"])
    names = [("COMET-22 ↑", lambda s: facts.comet(s), False, c4),
             ("MetricX-24 ↓", lambda s: facts.metricx(s), True, lambda x: f"{x:.3f}"),
             ("Judge vs DeepL API ↑" if en else "判定（対DeepL API）↑", vs, False, pct),
             ("Error-free ↑" if en else "誤りなし ↑", ef, False, pct),
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
    rows.append(f"| {'Completion ↑' if en else '完了率 ↑'} | {roles[5]} | {cells[0]} | {cells[1]} |")
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
    if lang == "en":
        return "\n\n".join([
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


README_BLOCKS = {"counts": counts, "top": top_table, "findings": findings, "lead-caption": lead_caption,
                 "metrics": metrics_table, "figures": more_captions}


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
