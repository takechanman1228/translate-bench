"""Recompute the release's frozen selections from the upstream files.

The seed strings in datasets/selection.json are historical: they were fixed before any output
was seen, and the rules below must use them exactly as written to reproduce the selections.
`check` returns a list of differences; prepare refuses to write inputs when it is not empty.
"""

import hashlib
from collections import defaultdict
from itertools import zip_longest

from translate_bench.datasets import build

# Historical seed strings of the frozen selections, as fixed before any output existed. They look like
# names of earlier projects because they are; changing a character changes the selection.
HISTORICAL_SEEDS = {
    "sentences": "open-local-translation/ntrex-v1/2026-11-19",
    "core_passages_from_english": "local-translate/2026-11-19/wmt-v1",
    "core_passages_into_english": "local-translate/wmt-docs/2026-11-19",
    "passages_set_8": "size-sweep-v1/",
    "passages_set_12": "size-sweep-v1/",
}
CORE_LOCALES = ("es", "zh-Hans", "ja")
SET12_LANGUAGES = ("ko", "pt-BR", "fr", "de", "id", "ar")
DOMAINS = ("news", "social", "speech", "literary")


def h(text):
    return hashlib.sha256(text.encode()).digest()


def excerpt(segments, language, limits):
    """First contiguous aligned segments within the length cap: (ids, source, target), or None."""
    unit = "characters" if language in ("ja", "zh-Hans") else "words"
    cap, minimum = limits[unit]["cap"], limits[unit]["minimum"]
    chosen, total = [], 0
    for i, s, t in segments:
        if not s.strip() or not t.strip():
            break
        measure = len(s) if unit == "characters" else len(s.split())
        if total + measure > cap:
            break
        chosen.append((i, s, t))
        total += measure
    if total < minimum:
        return None
    return [x[0] for x in chosen], "\n".join(x[1] for x in chosen), "\n".join(x[2] for x in chosen)


def ntrex_lines(rule, paths):
    seed = rule["seed_string"]
    files = [paths["ntrex-128/DOCUMENT_IDS.tsv"]] + [paths[build.ntrex_key(k)] for k in ("en", *CORE_LOCALES)]
    texts = [build.ntrex_lines(p) for p in files]
    if len({len(t) for t in texts}) != 1:
        raise ValueError("NTREX files are not aligned")
    docs = defaultdict(list)
    for i, doc in enumerate(texts[0]):
        if all(lines[i].strip() for lines in texts):
            docs[doc].append(i)

    def rank(value):
        return h(f"{seed}/{value}")

    order = sorted(docs, key=rank)
    candidates = sorted((offset, rank(doc), i) for doc in order[1::2]
                        for offset, i in enumerate(sorted(docs[doc], key=lambda idx: rank(str(idx + 1)))))
    return [i + 1 for _, _, i in candidates[:rule["count"]]]


def core_english_documents(rule, paths):
    seed = rule["seed_string"]
    by_pair = {}
    for language in CORE_LOCALES:
        documents = build.wmt24pp_documents(paths[build.wmt24pp_key(language)])
        by_pair[language] = {d: rows for d, rows in documents.items()
                             if all(not r["is_bad_source"] and r["target"].strip() for r in rows)}
    first = by_pair[CORE_LOCALES[0]]
    common = set.intersection(*(set(d) for d in by_pair.values()))
    domains = defaultdict(list)
    for doc in common:
        fields = [(r["segment_id"], r["domain"], r["source"]) for r in first[doc]]
        if all([(r["segment_id"], r["domain"], r["source"]) for r in docs[doc]] == fields
               for docs in by_pair.values()):
            domains[fields[0][1]].append(doc)
    held = []
    for domain in DOMAINS:
        docs = sorted(domains[domain], key=lambda d: h(seed + d))
        short = [d for d in docs if sum(len(r["source"].split()) for r in first[d]) <= 120]
        development = short[:1]
        held += [d for d in docs if d not in development][:rule["per_domain"]]
    return held


def core_original_documents(rule, paths, limits):
    seed = rule["seed_string"]
    by_src = defaultdict(dict)
    for year in ("12", "13"):
        source, reference = build.newstest(paths[f"wmt{year}/test.tgz"], year)
        for key, segments in source.items():
            pairs = [(i, s, reference[key].get(i, "")) for i, s in sorted(segments.items())]
            block = excerpt(pairs, "es", limits)
            if block:
                by_src["es"][f"wmt{year}/{key}"] = ("news", block)
    for language in ("zh-Hans", "ja"):
        for docid, (domain, pairs) in build.wmt23_documents(paths[build.wmt23_key(language)],
                                                             build.WMT23_CODES[language]).items():
            block = excerpt(pairs, language, limits)
            if block:
                by_src[language]["wmt23/" + docid] = (domain, block)
    held = {}
    for language, records in by_src.items():
        groups = defaultdict(list)
        for doc, (domain, _) in records.items():
            groups[domain].append(doc)
        balanced = [k for batch in zip_longest(*(sorted(g, key=lambda d: h(f"{seed}/{d}"))
                                                 for _, g in sorted(groups.items()))) for k in batch if k is not None]
        held[language] = [(doc, records[doc][1][0]) for doc in balanced[5:5 + rule["count"]]]
    return held


def set8_documents(rule, core_documents):
    seed = rule["seed_string"]
    return sorted(core_documents, key=lambda d: h(seed + "wmt24pp/" + d))[:8]


def set12_documents(rule, paths, limits):
    seed = rule["seed_string"]
    used = set(rule["excluded_documents"])
    pools = {}
    for language in SET12_LANGUAGES:
        pool = {}
        for document, rows in build.wmt24pp_documents(paths[build.wmt24pp_key(language)]).items():
            doc = "wmt24pp/" + document
            if doc in used or any(r["is_bad_source"] or not r["target"].strip() for r in rows):
                continue
            seq = [(r["segment_id"], r["source"], r["target"]) for r in rows]
            passage = excerpt(seq, "en", limits)
            if passage:
                pool[doc] = (rows[0]["domain"], passage, [(i, s) for i, s, _ in seq])
        pools[language] = pool
    ref = pools["ko"]
    common = set.intersection(*(set(p) for p in pools.values()))
    common = {d for d in common if all(p[d][2] == ref[d][2] and p[d][0] == ref[d][0] and p[d][1][:2] == ref[d][1][:2]
                                       for p in pools.values())}
    return [d.split("/", 1)[1] for d in sorted(common, key=lambda d: h(seed + d))[:rule["count"]]], ref


def needed():
    keys = ["ntrex-128/DOCUMENT_IDS.tsv", *(build.ntrex_key(k) for k in ("en", *CORE_LOCALES)),
            "wmt12/test.tgz", "wmt13/test.tgz", build.wmt23_key("ja"), build.wmt23_key("zh-Hans")]
    keys += [build.wmt24pp_key(k) for k in (*CORE_LOCALES, *SET12_LANGUAGES)]
    return keys


def check(selection, items, paths):
    """Differences between the recomputed selections and the frozen item manifest."""
    problems = [f"{key}: seed string differs from the historical one" for key, seed in HISTORICAL_SEEDS.items()
                if selection[key]["seed_string"] != seed]
    limits = selection["excerpt_limits"]
    lines = ntrex_lines(selection["sentences"], paths)
    if lines != selection["sentences"]["lines"]:
        problems.append("NTREX sentence lines differ from the frozen selection")
    sentence_lines = list(dict.fromkeys(i["origin"]["line"] for i in items if i["type"] == "sentence"))
    if sentence_lines != lines:
        problems.append("datasets/items.jsonl sentences are not the selected NTREX lines in order")
    english = core_english_documents(selection["core_passages_from_english"], paths)
    if english != selection["core_passages_from_english"]["documents"]:
        problems.append("WMT24++ core documents differ from the frozen selection")
    originals = core_original_documents(selection["core_passages_into_english"], paths, limits)
    frozen = selection["core_passages_into_english"]["documents"]
    passages = {i["id"]: i for i in items if i["type"] == "passage"}
    for language, picked in originals.items():
        if [d for d, _ in picked] != frozen[language]:
            problems.append(f"WMT original {language} documents differ from the frozen selection")
        for doc, segments in picked:
            item = passages.get(f"{doc}/{language}-en")
            if item is None or item["origin"]["segments"] != segments:
                problems.append(f"Excerpt segments differ for {doc}/{language}-en")
    set8 = set8_documents(selection["passages_set_8"], english)
    if sorted(set8) != sorted(selection["passages_set_8"]["documents"]):
        problems.append("set-8 documents differ from the frozen selection")
    set12, pool = set12_documents(selection["passages_set_12"], paths, limits)
    manifest12 = list(dict.fromkeys(i["origin"]["document"] for i in items if i.get("subset") == "set-12"))
    if set12 != manifest12:
        problems.append("set-12 documents differ from the frozen selection")
    for document in set12:
        ids = pool["wmt24pp/" + document][1][0]
        for item in (i for i in items if i.get("subset") == "set-12" and i["origin"]["document"] == document):
            if item["origin"]["segments"] != ids:
                problems.append(f"Excerpt segments differ for {item['id']}")
    return problems
