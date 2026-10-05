"""Stage 2: explicit sources -> immutable snapshots -> clean blocks -> two chunk sets.

Run from any directory. All paths are relative to this project, never to cwd.
Sources are untrusted data; no instructions from documents are executed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.metadata
import json
import math
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = DATA / "preparation_config.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def jsonl_write(path, items):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in items), encoding="utf-8", newline="\n")


def jsonl_read(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def normalize(text):
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00ad", "").replace("\xa0", " ").replace("\uf02d", "-")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b\ufeff]", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def words(text):
    return list(re.finditer(r"\S+", text))


def sources():
    with (DATA / "sources.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def safe_path(rel):
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise ValueError(f"Path outside data/: {rel}")
    return path


class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed):
        super().__init__()
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.allowed)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url, allowed):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in allowed or u.username or u.password or u.port not in (None, 443):
        raise ValueError(f"URL/redirect outside exact HTTPS allowlist: {url}")


def fetch():
    """Explicit GET only. No crawling, authentication, JS, forms or external redirects."""
    cfg = read_json(CONFIG)
    opener = urllib.request.build_opener(GuardedRedirect(set(cfg["allowed_hosts"])))
    old = read_json(DATA / "documents/manifest.json") if (DATA / "documents/manifest.json").exists() else {}
    current, events = {}, []
    checked_at = datetime.now(timezone(timedelta(hours=5))).isoformat(timespec="seconds")
    for src in sources():
        doc_id = src["document_id"]
        if src["collection_decision"] != "collect":
            current[doc_id] = {"status": "excluded", "reason": src["notes"]}
            continue
        try:
            check_url(src["source"], cfg["allowed_hosts"])
            req = urllib.request.Request(src["source"], headers={"User-Agent": "AIMGTU-Educational-KB/2.0", "Accept-Encoding": "identity"})
            with opener.open(req, timeout=25) as r:
                check_url(r.url, cfg["allowed_hosts"])
                body = r.read(cfg["max_download_bytes"] + 1)
                if len(body) > cfg["max_download_bytes"]:
                    raise ValueError("Download exceeds configured size limit")
                kind = "pdf" if body.startswith(b"%PDF") else "html"
                ctype = r.headers.get("Content-Type", "")
                if kind != src["format"] or (kind == "html" and "text/html" not in ctype):
                    raise ValueError("Unexpected format/content type")
                if kind == "html":
                    s = BeautifulSoup(body.decode("utf-8", errors="strict"), "html.parser")
                    if not s.select_one(src["content_selector"]):
                        raise ValueError("Expected content selector missing; review markup")
                checksum = sha(body)
                rel = f"data/documents/raw/{doc_id}_{checksum[:16]}.{kind}"
                safe_path(rel).write_bytes(body)
                current[doc_id] = {"status": "downloaded", "raw_path": rel, "raw_sha256": checksum,
                                   "fetched_at": checked_at, "source": src["source"], "resolved_url": r.url,
                                   "content_type": ctype, "bytes": len(body), "http_status": r.status,
                                   "last_modified": r.headers.get("Last-Modified")}
                prev = old.get(doc_id, {})
                action = "unchanged" if prev.get("raw_sha256") == checksum else "changed" if prev.get("raw_sha256") else "added"
                events.append({"document_id": doc_id, "action": action, "old_sha256": prev.get("raw_sha256"), "new_sha256": checksum})
            print(f"downloaded: {doc_id}")
        except Exception as e:
            prev = old.get(doc_id, {})
            current[doc_id] = {"status": "fetch_error", "source": src["source"], "checked_at": checked_at,
                               "reason": str(e), "last_good_snapshot": prev.get("raw_path") or prev.get("last_good_snapshot")}
            # Preserve older raw files on disk, but never silently reclassify them as fresh.
            events.append({"document_id": doc_id, "action": "access_error", "reason": str(e)})
            print(f"access_error: {doc_id}: {e}", file=sys.stderr)
    for doc_id in sorted(set(old) - set(current)):
        events.append({"document_id": doc_id, "action": "removed_from_registry"})
    write_json(DATA / "documents/manifest.json", current)
    write_json(DATA / "reports/refresh_report.json", {"checked_at": checked_at, "events": events})
    return current


def inline(node, base_url):
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in ("script", "style", "form", "input", "button", "iframe", "img", "noscript"):
        return ""
    text = "".join(inline(ch, base_url) for ch in node.children)
    if node.name == "br":
        return "\n"
    if node.name == "a" and node.get("href"):
        url = urllib.parse.urljoin(base_url, node["href"])
        if urllib.parse.urlsplit(url).scheme in ("https", "http", "mailto"):
            return f"{text.strip()} ({url})" if text.strip() else url
    return text


def table_markdown(table, base_url):
    rows = []
    for row in table.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if any(int(c.get("rowspan", 1)) != 1 or int(c.get("colspan", 1)) != 1 for c in cells):
            raise ValueError("Merged table cells need an explicit reviewed conversion")
        if cells:
            rows.append([normalize(inline(c, base_url)).replace("\n", " ").replace("|", "\\|") for c in cells])
    if not rows:
        return ""
    n = max(map(len, rows))
    rows = [r + [""] * (n - len(r)) for r in rows]
    # Without th, do not mistake the first data row for a header.
    header = rows.pop(0) if table.find("th") else [f"Столбец {i+1}" for i in range(n)]
    return "\n".join(["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * n) + " |"] + ["| " + " | ".join(r) + " |" for r in rows])


def html_blocks(raw, src):
    soup = BeautifulSoup(raw.decode("utf-8", errors="strict"), "html.parser")
    root = soup.select_one(src["content_selector"])
    if root is None:
        raise ValueError("Expected content container missing")
    for tag in list(root.select("script,style,nav,form,input,button,iframe,noscript")):
        tag.decompose()
    for a in list(root.select("a[href$='.sig']")):
        # Detached electronic signatures remain linked in the original snapshot.
        # Their duplicate document captions carry no additional answer content.
        parent = a.find_parent("li")
        (parent if parent is not None and parent.find_parent("li") is not None else a).decompose()
    out, path, stopped = [], [src["document_title"]], False
    for selector in src.get("exclude_selectors", "").split(";"):
        if selector.strip():
            for tag in list(root.select(selector.strip())):
                tag.decompose()
    def add(text, kind):
        text = normalize(text)
        if src.get("exclude_text_regex") and re.search(src["exclude_text_regex"], text):
            return
        if text:
            out.append({"text": text, "kind": kind, "section_path": list(path), "pages": []})
    def visit(node):
        nonlocal path, stopped
        if stopped:
            return
        if isinstance(node, NavigableString):
            add(str(node), "paragraph")
            return
        if not isinstance(node, Tag):
            return
        if re.fullmatch(r"h[1-6]", node.name):
            title = normalize(node.get_text(" ", strip=True))
            if title == src.get("stop_heading"):
                stopped = True
                return
            if node.name == "h1" and title == src["document_title"]:
                path = [title]
            elif title:
                level = int(node.name[1])
                path = path[:max(1, level-1)] + [title]
            return
        if node.name == "table":
            add(table_markdown(node, src["source"]), "table")
            return
        if node.name in ("ul", "ol"):
            rows = []
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                prefix = f"{i}. " if node.name == "ol" else "- "
                rows.append(prefix + normalize(inline(li, src["source"])))
            add("\n".join(rows), "list")
            return
        if node.name == "p":
            text = inline(node, src["source"])
            # Some source pages encode numbered procedures as br-separated paragraphs.
            text = re.sub(r"(?<!\n)(?=\b[1-9]\.\s+[А-ЯЁ])", "\n", text)
            add(text, "list" if re.search(r"(?:^|\n)[1-9]\. ", text) else "paragraph")
            return
        if node.name in ("script", "style", "form", "img", "input", "button", "iframe", "noscript"):
            return
        for child in node.children:
            visit(child)
    visit(root)
    return out


def pdf_blocks(path, src):
    """Reviewed body pages only; header is a ruled table above y=138 pt."""
    start, stop = map(int, src["page_range"].split("-"))
    blocks, section, buffer, pages = [], src["document_title"], [], []
    point = ""
    def flush():
        nonlocal buffer, pages
        if buffer:
            lines = []
            for line in buffer:
                if line.startswith("- "):
                    lines.append("\n" + line)
                else:
                    # Keep hard lexical hyphens (e.g. нормативно-правовой).
                    sep = "" if lines and lines[-1].endswith("-") else " "
                    lines.append(sep + line)
            text = normalize("".join(lines))
            blocks.append({"text": text, "kind": "clause" if point else "paragraph",
                           "section_path": [src["document_title"], section] + ([point] if point else []),
                           "pages": sorted(set(pages))})
        buffer, pages = [], []
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) < stop:
            raise ValueError("Reviewed PDF page range no longer exists")
        for i in range(start-1, stop):
            page = pdf.pages[i]
            crop = page.crop((0, 138, page.width, page.height-35))
            if crop.find_tables():
                raise ValueError("New PDF body table detected: explicit conversion required")
            text = crop.extract_text(x_tolerance=2) or ""
            if len(text.strip()) < 80:
                raise ValueError(f"PDF page {i+1} has no reliable text layer; OCR required")
            raw_lines = [normalize(x) for x in text.splitlines() if normalize(x)]
            j = 0
            while j < len(raw_lines):
                line = raw_lines[j]
                # End-of-document author attribution is outside the knowledge scope.
                if line.startswith(src["document_code"] + " Система"):
                    flush()
                    return blocks
                heading = re.match(r"^([1-9])\.\s+(\D.*)", line)
                clause = re.match(r"^(\d+\.\d+\.)\s+", line)
                if heading:
                    flush()
                    title = line
                    # Reviewed section headings wrapped over a second line.
                    while j+1 < len(raw_lines) and not re.match(r"^\d+\.\d+\.", raw_lines[j+1]) and not re.search(r"[.;:]$", title):
                        j += 1
                        title += " " + raw_lines[j]
                    section, point = title, ""
                else:
                    if clause:
                        flush()
                        point = clause.group(1)
                    buffer.append(line)
                    pages.append(i+1)
                j += 1
        flush()
    return blocks


def pack_document(src, entry):
    path = safe_path(entry["raw_path"])
    raw = path.read_bytes()
    if sha(raw) != entry["raw_sha256"]:
        raise ValueError("Raw checksum mismatch")
    blocks = pdf_blocks(path, src) if src["format"] == "pdf" else html_blocks(raw, src)
    # Repeated paragraphs are removed only inside the same section. Distinct legal
    # contexts must not lose a repeated instruction merely because wording matches.
    seen, kept, duplicates = set(), [], 0
    for b in blocks:
        key = (tuple(b["section_path"]), b["text"])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        kept.append(b)
    if not kept:
        raise ValueError("Empty clean document")
    text, pos = "", 0
    for i, b in enumerate(kept):
        if i:
            text += "\n\n"
        b["start_char"] = len(text)
        text += b["text"]
        b["end_char"] = len(text)
        b["block_id"] = f"{src['document_id']}:b{i+1:03d}"
    return {"document_id": src["document_id"], "document_title": src["document_title"],
            "source": src["source"], "date": src["date"] or None,
            "date_basis": src["date_basis"], "document_type": src["document_type"],
            "department": src["department"], "source_priority": int(src["priority"]),
            "validity_status": src["validity_status"], "allowed_use": src["allowed_use"],
            "dynamic": src["dynamic"] == "true", "education_level": src["education_level"],
            "fetched_at": entry["fetched_at"], "raw_path": entry["raw_path"],
            "raw_sha256": entry["raw_sha256"], "clean_sha256": sha(text),
            "text": text, "blocks": kept, "duplicates_removed": duplicates}


def window_ranges(text, start=0, end=None, size=180, overlap=30):
    end = len(text) if end is None else end
    matches = list(re.finditer(r"\S+", text[start:end]))
    for first in range(0, len(matches), size-overlap):
        last = min(first+size, len(matches))
        yield start+matches[first].start(), start+matches[last-1].end()
        if last == len(matches):
            break


def chunk_record(doc, method, n, start, end, fallback=False):
    blocks = [b for b in doc["blocks"] if b["start_char"] < end and b["end_char"] > start]
    pages = sorted({p for b in blocks for p in b["pages"]})
    paths = list(dict.fromkeys(tuple(b["section_path"]) for b in blocks))
    text = doc["text"][start:end]
    fields = ["document_id", "document_title", "source", "date", "date_basis", "document_type", "department",
              "source_priority", "validity_status", "allowed_use", "dynamic", "education_level",
              "fetched_at", "raw_sha256", "clean_sha256"]
    return {**{k: doc[k] for k in fields}, "page": pages[0] if pages else None, "pages": pages,
            "page_precision": "containing_block_page_span" if pages else "not_applicable_html",
            "page_end": pages[-1] if pages else None,
            "chunk_id": f"{doc['document_id']}:{doc['clean_sha256'][:12]}:{method}:{n:04d}",
            "chunking_method": method, "text": text, "text_sha256": sha(text),
            "section_paths": [list(p) for p in paths], "block_ids": [b["block_id"] for b in blocks],
            "start_char": start, "end_char": end, "word_count": len(words(text)),
            "fallback_split": fallback,
            "retrieval_text": doc["document_title"] + "\n" + text}


def make_chunks(doc, method, cfg):
    ranges = []
    if method == "fixed":
        ranges = [(s, e, False) for s, e in window_ranges(doc["text"], size=cfg["target_words"], overlap=cfg["overlap_words"])]
    else:
        pending, pending_words = [], 0
        def flush():
            nonlocal pending, pending_words
            if pending:
                ranges.append((pending[0]["start_char"], pending[-1]["end_char"], False))
            pending, pending_words = [], 0
        for b in doc["blocks"]:
            count = len(words(b["text"]))
            if count > cfg["max_words"]:
                flush()
                ranges.extend((s, e, True) for s, e in window_ranges(doc["text"], b["start_char"], b["end_char"], cfg["max_words"], cfg["overlap_words"]))
                continue
            key = b["section_path"][:-1] if b["kind"] == "clause" else b["section_path"]
            prior_key = (pending[-1]["section_path"][:-1] if pending[-1]["kind"] == "clause" else pending[-1]["section_path"]) if pending else None
            if pending and (key != prior_key or pending_words+count > cfg["max_words"]):
                flush()
            pending.append(b)
            pending_words += count
            if pending_words >= cfg["target_words"]:
                flush()
        flush()
    return [chunk_record(doc, method, i+1, *r) for i, r in enumerate(ranges)]


def build():
    cfg = read_json(CONFIG)
    manifest = read_json(DATA / "documents/manifest.json")
    docs, events, content_seen = [], [], {}
    for src in sorted(sources(), key=lambda x: (int(x["priority"]), x["document_id"])):
        entry = manifest.get(src["document_id"], {})
        if entry.get("status") != "downloaded" or src["index_decision"] != "include":
            events.append({"document_id": src["document_id"], "status": "excluded", "reason": entry.get("reason") or src["notes"]})
            continue
        try:
            if src.get("reviewed_raw_sha256") != entry.get("raw_sha256"):
                raise ValueError("Snapshot hash not reviewed: confirm source, scope and dates before indexing")
            doc = pack_document(src, entry)
            if doc["clean_sha256"] in content_seen:
                events.append({"document_id": doc["document_id"], "status": "duplicate_document", "canonical_id": content_seen[doc["clean_sha256"]]})
                continue
            content_seen[doc["clean_sha256"]] = doc["document_id"]
            docs.append(doc)
            write_json(DATA / f"documents/clean/{doc['document_id']}.json", doc)
            # Human-readable version; canonical offsets refer to JSON text only.
            md = f"# {doc['document_title']}\n\nИсточник: {doc['source']}\n\n"
            last_path = None
            for b in doc["blocks"]:
                if b["section_path"] != last_path:
                    md += "## " + " / ".join(b["section_path"][1:] or ["Основной текст"]) + "\n\n"
                    last_path = b["section_path"]
                if b["pages"]:
                    md += "<!-- PDF: " + ", ".join(map(str, b["pages"])) + " -->\n"
                md += b["text"] + "\n\n"
            (DATA / f"documents/clean/{doc['document_id']}.md").write_text(md, encoding="utf-8", newline="\n")
            events.append({"document_id": doc["document_id"], "status": "included", "blocks": len(doc["blocks"]),
                           "clean_characters": len(doc["text"]), "duplicates_removed": doc["duplicates_removed"]})
        except Exception as e:
            events.append({"document_id": src["document_id"], "status": "quarantined", "reason": str(e)})
    if not docs:
        raise ValueError("No eligible documents; no chunk output created")
    active_ids = {d["document_id"] for d in docs}
    for path in (DATA/"documents/clean").iterdir():
        if path.suffix in (".json", ".md") and path.stem not in active_ids:
            path.unlink()
    jsonl_write(DATA / "documents/clean_documents.jsonl", docs)
    for method in ("fixed", "semantic"):
        chunks = [c for d in docs for c in make_chunks(d, method, cfg["chunking"])]
        jsonl_write(DATA / f"chunks/{method}.jsonl", chunks)
    # Single selected input for later RAG ingestion. It is byte-identical to semantic.
    (DATA / "chunks/final.jsonl").write_bytes((DATA / "chunks/semantic.jsonl").read_bytes())
    write_json(DATA / "reports/cleaning_report.json", {"documents": events, "indexed_documents": len(docs),
                                                       "total_blocks": sum(len(d["blocks"]) for d in docs)})
    versions = {p: importlib.metadata.version(p) for p in ("beautifulsoup4", "pdfplumber", "pdfminer.six", "Pillow", "pypdfium2")}
    write_json(DATA / "reports/build_manifest.json", {"pipeline_version": cfg["pipeline_version"], "python_version": sys.version.split()[0],
                "pipeline_sha256": sha(Path(__file__).read_bytes()),
                "dependency_versions": versions, "config_sha256": sha(CONFIG.read_bytes()), "registry_sha256": sha((DATA/"sources.csv").read_bytes()),
                "snapshot_manifest_sha256": sha((DATA/"documents/manifest.json").read_bytes()),
                "corpus_version": sha("\n".join(json.dumps(d,ensure_ascii=False,sort_keys=True) for d in docs)+sha(CONFIG.read_bytes())),
                "selected_method": "semantic", "counts": {m: len(jsonl_read(DATA/f"chunks/{m}.jsonl")) for m in ("fixed", "semantic")},
                "outputs": {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p.read_bytes()) for p in sorted((DATA/"chunks").glob('*.jsonl'))}})
    return docs


STOP = set("и в во на по от до к с со у за из для о об не или что как где ли а это при его ее их все нужно можно мне мой свою свой когда чем чтобы".split())


def terms(text):
    return [w for w in re.findall(r"[а-яёa-z0-9]+", text.lower().replace("ё", "е")) if len(w)>1 and w not in STOP]


def rank(query, chunks):
    """Deterministic BM25 control, no models/embeddings/LLM required."""
    bags = [collections.Counter(terms(c["retrieval_text"])) for c in chunks]
    df = collections.Counter(t for b in bags for t in b)
    avdl = sum(sum(b.values()) for b in bags) / len(bags)
    scored = []
    for c, b in zip(chunks, bags):
        dl, score = sum(b.values()), 0.0
        for t in set(terms(query)):
            f = b[t]
            if f:
                idf = math.log(1+(len(bags)-df[t]+0.5)/(df[t]+0.5))
                score += idf * (f*2.5) / (f+1.5*(1-0.75+0.75*dl/avdl))
        scored.append((score, c["chunk_id"], c))
    return sorted(scored, key=lambda x:(-x[0], x[1]))


def comparable(text):
    return " ".join(text.lower().replace("ё", "е").split())


def supports(q, c):
    return c["document_id"] == q["document_id"] and all(comparable(p) in comparable(c["text"]) for p in q["evidence"])


def compare():
    docs = jsonl_read(DATA/"documents/clean_documents.jsonl")
    questions = jsonl_read(DATA/"evaluation/questions.jsonl")
    answerable = [q for q in questions if q["expected_decision"] == "answer"]
    by_id = {d["document_id"]:d for d in docs}
    for q in answerable:
        if q["document_id"] not in by_id or not all(comparable(x) in comparable(by_id[q["document_id"]]["text"]) for x in q["evidence"]):
            raise ValueError(f"Gold evidence absent from clean corpus: {q['question_id']}")
    results, details = {}, []
    for method in ("fixed", "semantic"):
        chunks = jsonl_read(DATA/f"chunks/{method}.jsonl")
        hits1, hits3, rr = 0, 0, 0.0
        for q in answerable:
            top = rank(q["question"], chunks)[:5]
            rank_hit = next((i+1 for i,(_,_,c) in enumerate(top) if supports(q,c)), None)
            hits1 += rank_hit == 1
            hits3 += rank_hit is not None and rank_hit <= 3
            rr += 1/rank_hit if rank_hit else 0
            details.append({"method":method, "question_id":q["question_id"], "first_support_rank_at_5":rank_hit,
                            "top5":[{"chunk_id":c["chunk_id"], "score":round(s,6), "supports_evidence":supports(q,c)} for s,_,c in top]})
        complete, eligible, all_complete, all_blocks = 0, 0, 0, 0
        for d in docs:
            cs = [c for c in chunks if c["document_id"]==d["document_id"]]
            for b in d["blocks"]:
                ok = any(c["start_char"]<=b["start_char"] and c["end_char"]>=b["end_char"] for c in cs)
                all_complete += ok
                all_blocks += 1
                if len(words(b["text"])) <= read_json(CONFIG)["chunking"]["target_words"]:
                    eligible += 1
                    complete += ok
        sizes = sorted(c["word_count"] for c in chunks)
        totalchars = sum(len(d["text"]) for d in docs)
        results[method] = {"chunk_count":len(chunks), "min_words":min(sizes), "median_words":sizes[len(sizes)//2], "max_words":max(sizes),
                           "payload_characters":sum(len(c["text"]) for c in chunks),
                           "payload_to_clean_ratio": round(sum(len(c["text"]) for c in chunks)/totalchars,4),
                           "small_blocks_preserved":complete, "small_blocks_total":eligible,
                           "small_block_preservation_rate":round(complete/eligible,4),
                           "all_blocks_preserved":all_complete, "all_blocks_total":all_blocks,
                           "fallback_chunks":sum(c["fallback_split"] for c in chunks),
                           "support_hit_at_1":round(hits1/len(answerable),4), "support_hit_at_3":round(hits3/len(answerable),4),
                           "support_mrr_at_5":round(rr/len(answerable),4), "answerable_questions":len(answerable)}
    write_json(DATA/"reports/chunking_comparison.json", {"retriever":"BM25 exact lowercase terms; k1=1.5, b=0.75; no stemming", "metrics":results,
                "questions_sha256":sha((DATA/"evaluation/questions.jsonl").read_bytes()),
                "pipeline_sha256":sha(Path(__file__).read_bytes()),
                "refusal_cases_not_scored": len(questions)-len(answerable),
                "limitations":"Small corpus, drafted gold requires team review; not RAG answer quality or embedding benchmark.", "selected":"semantic"})
    jsonl_write(DATA/"reports/retrieval_details.jsonl", details)
    lines = ["# Сравнение двух вариантов разбиения", "", "Один корпус, один набор вопросов, одинаковый BM25. Результаты рассчитаны скриптом, без LLM.", "",
             "| Метрика | Фиксированные окна | Смысловые блоки |", "|---|---:|---:|"]
    labels = {"chunk_count":"Количество фрагментов", "median_words":"Медиана слов", "max_words":"Максимум слов", "payload_to_clean_ratio":"Объём фрагментов / объём очищенных текстов",
              "small_block_preservation_rate":"Доля блоков ≤180 слов, целиком сохранённых хотя бы в одном chunk",
              "fallback_chunks":"Фрагменты аварийного разбиения больших блоков", "support_hit_at_1":"Полное подтверждение в одном chunk: Hit@1", "support_hit_at_3":"Полное подтверждение в одном chunk: Hit@3", "support_mrr_at_5":"MRR@5 полного подтверждения"}
    for k,v in labels.items():
        lines.append(f"| {v} | {results['fixed'][k]} | {results['semantic'][k]} |")
    lines += ["", f"Ответимых вопросов: {len(answerable)}. Сценарии отказа ({len(questions)-len(answerable)}) не оцениваются без генератора и политики ответа.", "",
              "Это контролируемый лексический эксперимент на пилотном корпусе. Его нельзя представлять как доказательство качества будущего embedding-поиска или всех ответов RAG.", "",
              "Итоговый метод — смысловое разбиение: сохраняет пункты, списки и связь с разделом. Длинные пункты делятся окнами до 260 слов с перекрытием 30 слов; такие chunks помечены fallback_split.", "",
              "См. покомпонентные результаты в retrieval_details.jsonl; обсуждение ограничений и решение команды — в docs/data_preparation.md.", ""]
    (DATA/"reports/chunking_comparison.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return results


def validate():
    docs = jsonl_read(DATA/"documents/clean_documents.jsonl")
    by_id = {d["document_id"]:d for d in docs}
    issues, count = [], 0
    required = {"document_id","document_title","source","date","document_type","department","page","chunk_id","text"}
    for d in docs:
        if sha(safe_path(d["raw_path"]).read_bytes()) != d["raw_sha256"] or sha(d["text"]) != d["clean_sha256"]:
            issues.append(f"Checksum mismatch: {d['document_id']}")
    for method in ("fixed", "semantic"):
        chunks = jsonl_read(DATA/f"chunks/{method}.jsonl")
        ids = set()
        for c in chunks:
            count += 1
            d = by_id[c["document_id"]]
            if required - set(c) or not c["text"].strip() or c["chunk_id"] in ids:
                issues.append(f"Missing field/empty/duplicate id: {c['chunk_id']}")
            if c["date"] is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["date"]):
                issues.append(f"Invalid document date: {c['chunk_id']}")
            if (c["page"] is None) != (not c["pages"]):
                issues.append(f"Page consistency failure: {c['chunk_id']}")
            ids.add(c["chunk_id"])
            if d["text"][c["start_char"]:c["end_char"]] != c["text"] or sha(c["text"]) != c["text_sha256"]:
                issues.append(f"Offset/checksum mismatch: {c['chunk_id']}")
            if c["word_count"] > read_json(CONFIG)["chunking"]["max_words"]:
                issues.append(f"Oversize: {c['chunk_id']}")
            if "\ufffd" in c["text"] or re.search(r"[\ue000-\uf8ff]", c["text"]):
                issues.append(f"Broken extraction character: {c['chunk_id']}")
            check_url(c["source"], read_json(CONFIG)["allowed_hosts"])
        # Full non-whitespace character coverage. Overlap is permitted.
        for d in docs:
            coverage = bytearray(len(d["text"]))
            for c in chunks:
                if c["document_id"] == d["document_id"]:
                    coverage[c["start_char"]:c["end_char"]] = b"\x01"*(c["end_char"]-c["start_char"])
            if any(not coverage[i] and not ch.isspace() for i,ch in enumerate(d["text"])):
                issues.append(f"Coverage loss: {method}:{d['document_id']}")
    if (DATA/"chunks/final.jsonl").read_bytes() != (DATA/"chunks/semantic.jsonl").read_bytes():
        issues.append("final.jsonl differs from selected semantic method")
    report = {"passed":not issues, "documents":len(docs), "checked_chunks_two_variants":count, "issues":issues}
    write_json(DATA/"reports/validation_report.json", report)
    if issues:
        raise ValueError("Validation failed: "+str(issues))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch","build","compare","validate","all"])
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            fetch()
        elif args.command == "all":
            build(); compare(); print(json.dumps(validate(),ensure_ascii=False))
        else:
            result = {"build":build,"compare":compare,"validate":validate}[args.command]()
            print(json.dumps(result if args.command != "build" else {"documents":len(result)},ensure_ascii=False))
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
