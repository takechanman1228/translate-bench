"""Read the upstream files, assemble each item's source and reference, and write the input TSVs.

Every item in datasets/items.jsonl names its upstream document and segments. A passage joins its
segments with a line feed. The texts are checked against the item's SHA-256 digests before
anything is written.
"""

import csv
import hashlib
import html
import json
import re
import tarfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from translate_bench.schema import parse_direction

FIELDS = ("id", "src", "tgt", "source", "reference", "domain", "doc")
NTREX_CODES = {"en": "src.eng", "es": "ref.spa-MX", "zh-Hans": "ref.zho-CN", "ja": "ref.jpn", "ko": "ref.kor",
               "fr": "ref.fra", "de": "ref.deu", "pt-BR": "ref.por-BR", "ar": "ref.arb", "id": "ref.ind"}
WMT24PP_LOCALES = {"es": "es_MX", "zh-Hans": "zh_CN", "ja": "ja_JP", "ko": "ko_KR", "fr": "fr_FR", "de": "de_DE",
                   "pt-BR": "pt_BR", "ar": "ar_EG", "id": "id_ID"}
WMT23_CODES = {"ja": "ja", "zh-Hans": "zh"}


def ntrex_key(language):
    return f"ntrex-128/newstest2019-{NTREX_CODES[language]}.txt"


def wmt24pp_key(language):
    return f"wmt24pp/en-{WMT24PP_LOCALES[language]}.jsonl"


def wmt23_key(language):
    return f"wmt23/wmttest2023.{WMT23_CODES[language]}-en.all.xml"


def files_for(item):
    src, tgt = parse_direction(item["direction"])
    other = tgt if src == "en" else src
    dataset = item["origin"]["dataset"]
    if dataset == "ntrex-128":
        return [ntrex_key("en"), ntrex_key(other)]
    if dataset == "wmt24pp":
        return [wmt24pp_key(other)]
    if dataset in ("wmt12", "wmt13"):
        return [f"{dataset}/test.tgz"]
    if dataset == "wmt23":
        return [wmt23_key(other)]
    raise ValueError(f"Unknown dataset {dataset!r} for {item['id']}")


@lru_cache(maxsize=None)
def ntrex_lines(path):
    return Path(path).read_bytes().decode("utf-8-sig").splitlines()


@lru_cache(maxsize=None)
def wmt24pp_documents(path):
    documents = {}
    for line in Path(path).read_bytes().splitlines():
        row = json.loads(line)
        documents.setdefault(row["document_id"], []).append(row)
    for rows in documents.values():
        rows.sort(key=lambda r: r["segment_id"])
    return documents


def sgml_documents(data, origlang="es"):
    """Documents of one newstest SGML file: {docid: {segment id: text}} for the given original language.

    The official SGML has unescaped ampersands, so the documented doc/seg boundaries are read with
    regular expressions rather than an XML parser."""
    docs = {}
    for attrs, body in re.findall(r"<doc\s+([^>]+)>(.*?)</doc>", data.decode(), re.I | re.S):
        a = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
        if a["origlang"] == origlang:
            docs[a["docid"]] = {int(i): html.unescape(s.strip()) for i, s in
                                re.findall(r'<seg id="(\d+)">(.*?)</seg>', body, re.S)}
    return docs


@lru_cache(maxsize=None)
def newstest(path, year):
    """(Spanish-original source documents, their English references) of newstest20{year}."""
    with tarfile.open(path) as archive:
        return tuple(sgml_documents(archive.extractfile(f"test/newstest20{year}-src.{lg}.sgm").read())
                     for lg in ("es", "en"))


@lru_cache(maxsize=None)
def wmt23_documents(path, lg):
    """{docid: (domain, [(segment id, original, refA reference)])} for documents originally in `lg`."""
    out = {}
    for doc in ET.parse(path).iter("doc"):
        if doc.get("origlang") != lg or not doc.get("domain"):
            continue
        original = doc.find(f"src[@lang='{lg}']")
        ref = doc.find("ref[@translator='refA']")
        if ref is None or original is None:
            continue
        refs = {el.get("id"): "".join(el.itertext()).strip() for el in ref.iter("seg")}
        out[doc.get("id")] = (doc.get("domain"), [(el.get("id"), "".join(el.itertext()).strip(),
                                                   refs.get(el.get("id"), "")) for el in original.iter("seg")])
    return out


def texts(item, paths):
    """(source, reference) of one item from the downloaded files."""
    src, tgt = parse_direction(item["direction"])
    other = tgt if src == "en" else src
    origin = item["origin"]
    dataset = origin["dataset"]
    if dataset == "ntrex-128":
        line = origin["line"] - 1
        english, translated = ntrex_lines(paths[ntrex_key("en")])[line], ntrex_lines(paths[ntrex_key(other)])[line]
    elif dataset == "wmt24pp":
        rows = {r["segment_id"]: r for r in wmt24pp_documents(paths[wmt24pp_key(other)])[origin["document"]]}
        chosen = [rows[i] for i in origin["segments"]]
        english = "\n".join(r["source"] for r in chosen)
        translated = "\n".join(r["target"] for r in chosen)
    elif dataset in ("wmt12", "wmt13"):
        source, reference = newstest(paths[f"{dataset}/test.tgz"], dataset[-2:])
        doc = origin["document"]
        translated = "\n".join(source[doc][i] for i in origin["segments"])  # Spanish original
        english = "\n".join(reference[doc].get(i, "") for i in origin["segments"])
    elif dataset == "wmt23":
        _, segments = wmt23_documents(paths[wmt23_key(other)], WMT23_CODES[other])[origin["document"]]
        by_id = {i: (s, r) for i, s, r in segments}
        translated = "\n".join(by_id[i][0] for i in origin["segments"])
        english = "\n".join(by_id[i][1] for i in origin["segments"])
    else:
        raise ValueError(f"Unknown dataset {dataset!r}")
    return (english, translated) if src == "en" else (translated, english)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assemble(items, paths):
    """TSV rows of the items, after checking every source and reference digest."""
    rows = []
    for item in items:
        source, reference = texts(item, paths)
        if sha(source) != item["source_sha256"] or sha(reference) != item["reference_sha256"]:
            raise ValueError(f"Text digest mismatch for {item['id']}; the upstream file or the extraction differs")
        src, tgt = parse_direction(item["direction"])
        rows.append(dict(id=item["id"], src=src, tgt=tgt, source=source, reference=reference,
                         domain=item["domain"], doc=item["doc"]))
    return rows


def tsv_bytes(rows):
    """The release's TSV format: CSV quoting with tabs, CRLF line ends, UTF-8."""
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, FIELDS, delimiter="\t", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")
