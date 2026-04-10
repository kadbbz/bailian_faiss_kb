#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


EMBEDDING_MODEL = "text-embedding-v4"
RERANK_MODEL = "qwen3-rerank"
EMBEDDING_DIMENSIONS = 1024
DEFAULT_ROOT_DIR = "/var/openclaw-kb"
DEFAULT_TOPK = 10
DEFAULT_TOPN = 10
EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
RERANK_URL = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".json",
    ".markdown",
    ".md",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rst",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
    ".yaml",
    ".yml",
}


class KBError(RuntimeError):
    pass


def load_requests():
    try:
        import requests
    except ImportError as exc:
        raise KBError("Missing dependency 'requests'. Run: python3 -m pip install -r requirements.txt") from exc
    return requests


def load_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise KBError("Missing dependency 'numpy'. Run: python3 -m pip install -r requirements.txt") from exc
    return np


def load_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise KBError("Missing dependency 'faiss-cpu'. Run: python3 -m pip install -r requirements.txt") from exc
    return faiss


def load_markitdown():
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise KBError("Missing dependency 'markitdown'. Run: python3 -m pip install -r requirements.txt") from exc
    return MarkItDown


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def collapse_text(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


def stable_id(*parts: str) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_component(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" ._")
    return cleaned or "file"


def trim_text(text: str, limit: int) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def load_api_key() -> str:
    api_key = os.getenv("BAILIAN-SK") or os.getenv("BAILIAN_SK")
    if not api_key:
        raise KBError("Missing API key. Set environment variable BAILIAN-SK or BAILIAN_SK.")
    return api_key


def kb_dir(root_dir: Path, kb_name: str) -> Path:
    safe_kb = sanitize_component(kb_name)
    return root_dir / safe_kb


def kb_paths(root_dir: Path, kb_name: str) -> dict[str, Path]:
    root = kb_dir(root_dir, kb_name)
    return {
        "root": root,
        "config": root / "config.json",
        "manifest": root / "manifest.json",
        "vectors": root / "vectors.jsonl",
        "index": root / "index.faiss",
    }


def ensure_kb_config(
    root_dir: Path,
    kb_name: str,
    *,
    topk: int | None = None,
    topn: int | None = None,
) -> dict:
    paths = kb_paths(root_dir, kb_name)
    paths["root"].mkdir(parents=True, exist_ok=True)
    config = read_json(
        paths["config"],
        default={
            "root_dir": str(root_dir),
            "kb_name": kb_name,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "rerank_model": RERANK_MODEL,
            "topk": DEFAULT_TOPK,
            "topN": DEFAULT_TOPN,
            "updated_at": now_iso(),
        },
    )
    config["root_dir"] = str(root_dir)
    config["kb_name"] = kb_name
    config["embedding_model"] = EMBEDDING_MODEL
    config["embedding_dimensions"] = EMBEDDING_DIMENSIONS
    config["rerank_model"] = RERANK_MODEL
    config["topk"] = normalize_positive(topk or config.get("topk", DEFAULT_TOPK), "topk")
    config["topN"] = normalize_positive(topn or config.get("topN", DEFAULT_TOPN), "topN")
    if config["topN"] > config["topk"]:
        raise KBError("topN must be less than or equal to topk.")
    config["updated_at"] = now_iso()
    write_json(paths["config"], config)
    return config


def convert_source(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix in {".md", ".markdown", ".rst", ".txt"}:
        return normalize_text(input_path.read_text(encoding="utf-8", errors="ignore"))
    if suffix not in SUPPORTED_EXTENSIONS:
        raise KBError(f"Unsupported file extension: {suffix}")
    MarkItDown = load_markitdown()
    converter = MarkItDown()
    result = converter.convert(str(input_path))
    text = getattr(result, "text_content", "") or getattr(result, "markdown", "") or str(result)
    return normalize_text(text)


def write_markdown_output(output_path: Path, markdown: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown + "\n", encoding="utf-8")


def validate_doc_dir(doc_dir: Path, kb_root: Path, kb_name: str) -> Path:
    expected_parent = kb_dir(kb_root, kb_name)
    doc_dir = doc_dir.resolve()
    if doc_dir.parent != expected_parent.resolve():
        raise KBError(f"Document directory must be directly under {expected_parent}")
    return doc_dir


def parse_doc_dir_name(doc_dir: Path) -> tuple[str, str]:
    match = re.match(r"^(\d{12})-(.+)$", doc_dir.name)
    if not match:
        raise KBError("Document directory must match '{ts}-{safe_name}' with ts formatted as yyyyMMddhhmm.")
    return match.group(1), match.group(2)


def find_primary_source_file(doc_dir: Path) -> Path:
    for entry in sorted(doc_dir.iterdir(), key=lambda item: item.name):
        if entry.is_file() and entry.suffix.lower() != ".md" and entry.name != "summary.txt":
            return entry
    raise KBError(f"No source file found in {doc_dir}")


def find_doc_markdown(doc_dir: Path, safe_name: str, raw_file: Path) -> Path:
    preferred = doc_dir / f"{safe_name}.md"
    if preferred.exists():
        return preferred
    fallback = doc_dir / f"{raw_file.stem}.md"
    if fallback.exists():
        return fallback
    raise KBError(f"Markdown file not found in {doc_dir}")


def read_summary(doc_dir: Path) -> str:
    summary_path = doc_dir / "summary.txt"
    if not summary_path.exists():
        return ""
    summary = collapse_text(summary_path.read_text(encoding="utf-8", errors="ignore"))
    if len(summary) > 200:
        raise KBError(f"Summary exceeds 200 characters: {summary_path}")
    return summary


def parse_chunk_id(path: Path) -> str:
    match = re.fullmatch(r"chunk-(\d{5})\.md", path.name)
    if not match:
        raise KBError(f"Invalid chunk filename: {path.name}")
    return match.group(1)


def parse_t2q_name(path: Path) -> tuple[str, str]:
    match = re.fullmatch(r"(\d{5})-q-(\d+)\.md", path.name)
    if not match:
        raise KBError(f"Invalid T2Q filename: {path.name}")
    return match.group(1), match.group(2)


def read_markdown_file(path: Path) -> str:
    return normalize_text(path.read_text(encoding="utf-8", errors="ignore"))


def collect_doc_records(kb_name: str, doc_dir: Path) -> tuple[list[dict], dict]:
    ts, safe_name = parse_doc_dir_name(doc_dir)
    raw_file = find_primary_source_file(doc_dir)
    markdown_path = find_doc_markdown(doc_dir, safe_name, raw_file)
    summary_path = doc_dir / "summary.txt"
    chunks_dir = doc_dir / "chunks"
    t2q_dir = doc_dir / "t2q"
    if not chunks_dir.is_dir():
        raise KBError(f"Chunks directory not found: {chunks_dir}")
    if not t2q_dir.is_dir():
        raise KBError(f"T2Q directory not found: {t2q_dir}")

    summary = read_summary(doc_dir)
    raw_sha1 = file_sha1(raw_file)
    markdown_sha1 = file_sha1(markdown_path)
    total_chunk_count = len(list(chunks_dir.glob("chunk-*.md")))
    chunk_records = []
    chunk_lookup = {}
    for chunk_path in sorted(chunks_dir.glob("chunk-*.md")):
        chunk_id = parse_chunk_id(chunk_path)
        text = read_markdown_file(chunk_path)
        record = {
            "id": stable_id(kb_name, doc_dir.name, "chunk", chunk_id, text),
            "kb": kb_name,
            "doc_id": doc_dir.name,
            "file_name": raw_file.name,
            "uploaded_at": ts,
            "kind": "chunk",
            "chunk_id": chunk_id,
            "q_id": None,
            "path": str(chunk_path),
            "source_md_path": str(markdown_path),
            "source_file_path": str(raw_file),
            "summary_path": str(summary_path),
            "summary": summary,
            "raw_sha1": raw_sha1,
            "markdown_sha1": markdown_sha1,
            "chunk_count": total_chunk_count,
            "target_chunk_path": str(chunk_path),
            "text": text,
        }
        chunk_records.append(record)
        chunk_lookup[chunk_id] = record

    t2q_records = []
    for question_path in sorted(t2q_dir.glob("*.md")):
        chunk_id, q_id = parse_t2q_name(question_path)
        if chunk_id not in chunk_lookup:
            raise KBError(f"T2Q file {question_path.name} references missing chunk {chunk_id}")
        text = collapse_text(question_path.read_text(encoding="utf-8", errors="ignore"))
        if not text:
            continue
        t2q_records.append(
            {
                "id": stable_id(kb_name, doc_dir.name, "t2q", chunk_id, q_id, text),
                "kb": kb_name,
                "doc_id": doc_dir.name,
                "file_name": raw_file.name,
                "uploaded_at": ts,
                "kind": "t2q",
                "chunk_id": chunk_id,
                "q_id": q_id,
                "path": str(question_path),
                "source_md_path": str(markdown_path),
                "source_file_path": str(raw_file),
                "summary_path": str(summary_path),
                "summary": summary,
                "raw_sha1": raw_sha1,
                "markdown_sha1": markdown_sha1,
                "chunk_count": total_chunk_count,
                "target_chunk_path": chunk_lookup[chunk_id]["path"],
                "text": text,
            }
        )

    summary_record = {
        "doc_id": doc_dir.name,
        "file_name": raw_file.name,
        "uploaded_at": ts,
        "source_file_path": str(raw_file),
        "source_md_path": str(markdown_path),
        "summary_path": str(summary_path),
        "summary": summary,
        "chunk_count": len(chunk_records),
        "t2q_count": len(t2q_records),
        "raw_sha1": raw_sha1,
        "markdown_sha1": markdown_sha1,
    }
    return chunk_records + t2q_records, summary_record


def collect_doc_manifest_only(kb_name: str, doc_dir: Path) -> dict:
    _, summary_record = collect_doc_records(kb_name, doc_dir)
    return summary_record


def summarize_documents_from_records(records: list[dict]) -> list[dict]:
    documents = {}
    for item in records:
        document = documents.setdefault(
            item["doc_id"],
            {
                "doc_id": item["doc_id"],
                "file_name": item["file_name"],
                "uploaded_at": item["uploaded_at"],
                "source_file_path": item["source_file_path"],
                "source_md_path": item["source_md_path"],
                "summary_path": item["summary_path"],
                "summary": item.get("summary", ""),
                "chunk_count": 0,
                "t2q_count": 0,
                "raw_sha1": item.get("raw_sha1"),
                "markdown_sha1": item.get("markdown_sha1"),
            },
        )
        if item["kind"] == "chunk":
            document["chunk_count"] += 1
        elif item["kind"] == "t2q":
            document["t2q_count"] += 1
    return sorted(documents.values(), key=lambda item: item["doc_id"])


def list_doc_dirs(kb_root: Path, kb_name: str) -> list[Path]:
    root = kb_dir(kb_root, kb_name)
    if not root.exists():
        return []
    return [
        entry
        for entry in sorted(root.iterdir(), key=lambda item: item.name)
        if entry.is_dir() and re.match(r"^\d{12}-.+", entry.name)
    ]


def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    if not texts:
        return []
    requests = load_requests()
    api_key = load_api_key()
    outputs: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        payload = {
            "model": EMBEDDING_MODEL,
            "input": batch,
            "dimensions": EMBEDDING_DIMENSIONS,
            "encoding_format": "float",
        }
        response = requests.post(
            EMBEDDING_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if response.status_code >= 400:
            raise KBError(f"Embedding request failed: {response.status_code} {response.text}")
        body = response.json()
        if "error" in body:
            raise KBError(f"Embedding request failed: {json.dumps(body['error'], ensure_ascii=False)}")
        outputs.extend(item["embedding"] for item in sorted(body.get("data", []), key=lambda item: item["index"]))
    return outputs


def rerank_documents(query: str, documents: list[str], top_n: int) -> list[dict]:
    if not documents:
        return []
    requests = load_requests()
    api_key = load_api_key()
    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents[:200],
        "top_n": min(top_n, len(documents[:200])),
        "instruct": "Given a user query, rank the most relevant passages for retrieval.",
    }
    response = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        raise KBError(f"Rerank request failed: {response.status_code} {response.text}")
    body = response.json()
    if "error" in body:
        raise KBError(f"Rerank request failed: {json.dumps(body['error'], ensure_ascii=False)}")
    output = body.get("output", {})
    return [
        {"index": item["index"], "relevance_score": item["relevance_score"]}
        for item in output.get("results", body.get("results", []))
    ]


def write_faiss_index(index_path: Path, embeddings: list[list[float]]) -> None:
    np = load_numpy()
    faiss = load_faiss()
    vectors = np.asarray(embeddings, dtype="float32")
    if vectors.ndim != 2 or vectors.shape[1] != EMBEDDING_DIMENSIONS:
        raise KBError(f"Unexpected embedding matrix shape: {vectors.shape}")
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
    index.add(vectors)
    faiss.write_index(index, str(index_path))


def persist_kb_artifacts(paths: dict[str, Path], records: list[dict], manifest: dict) -> None:
    if records:
        write_jsonl(paths["vectors"], records)
        write_faiss_index(paths["index"], embed_texts([item["text"] for item in records]))
    else:
        write_jsonl(paths["vectors"], [])
        if paths["index"].exists():
            paths["index"].unlink()
    write_json(paths["manifest"], manifest)


def load_index_bundle(kb_root: Path, kb_name: str) -> tuple[dict, list[dict], object | None]:
    paths = kb_paths(kb_root, kb_name)
    config = read_json(paths["config"], default=None)
    if config is None:
        raise KBError(f"Knowledge base config not found: {kb_name}")
    vectors = read_jsonl(paths["vectors"])
    index = None
    if paths["index"].exists():
        faiss = load_faiss()
        index = faiss.read_index(str(paths["index"]))
    return config, vectors, index


def index_kb(root_dir: Path, kb_name: str, doc_dir: Path, *, topk: int | None, topn: int | None) -> dict:
    config = ensure_kb_config(root_dir, kb_name, topk=topk, topn=topn)
    doc_dir = validate_doc_dir(doc_dir, root_dir, kb_name)
    paths = kb_paths(root_dir, kb_name)
    doc_records, doc_manifest = collect_doc_records(kb_name, doc_dir)
    existing_records = [item for item in read_jsonl(paths["vectors"]) if item["doc_id"] != doc_manifest["doc_id"]]
    merged_records = existing_records + doc_records
    merged_records.sort(key=lambda item: (item["doc_id"], item["kind"], item["chunk_id"] or "", item["q_id"] or ""))
    document_summaries = summarize_documents_from_records(merged_records)
    manifest = {
        "kb_name": kb_name,
        "root_dir": str(root_dir),
        "indexed_at": now_iso(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "rerank_model": RERANK_MODEL,
        "topk": config["topk"],
        "topN": config["topN"],
        "document_count": len(document_summaries),
        "vector_count": len(merged_records),
        "chunk_count": sum(1 for item in merged_records if item["kind"] == "chunk"),
        "t2q_count": sum(1 for item in merged_records if item["kind"] == "t2q"),
        "documents": document_summaries,
    }
    persist_kb_artifacts(paths, merged_records, manifest)
    return manifest


def delete_from_index(root_dir: Path, kb_name: str, doc_id: str) -> dict:
    paths = kb_paths(root_dir, kb_name)
    config = read_json(paths["config"], default=None)
    if config is None:
        raise KBError(f"Knowledge base config not found: {kb_name}")
    existing_records = read_jsonl(paths["vectors"])
    if not existing_records and not paths["manifest"].exists():
        raise KBError(f"Knowledge base index not found: {kb_name}")

    remaining_records = [item for item in existing_records if item["doc_id"] != doc_id]
    deleted_count = len(existing_records) - len(remaining_records)

    document_summaries = summarize_documents_from_records(remaining_records)

    manifest = {
        "kb_name": kb_name,
        "root_dir": str(root_dir),
        "indexed_at": now_iso(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "rerank_model": RERANK_MODEL,
        "topk": config.get("topk", DEFAULT_TOPK),
        "topN": config.get("topN", DEFAULT_TOPN),
        "document_count": len(document_summaries),
        "vector_count": len(remaining_records),
        "chunk_count": sum(1 for item in remaining_records if item["kind"] == "chunk"),
        "t2q_count": sum(1 for item in remaining_records if item["kind"] == "t2q"),
        "documents": document_summaries,
        "deleted_doc_id": doc_id,
        "deleted_vector_count": deleted_count,
    }
    persist_kb_artifacts(paths, remaining_records, manifest)
    return manifest


def vector_search(records: list[dict], index, query: str, top_k: int) -> list[dict]:
    if not records or index is None:
        return []
    np = load_numpy()
    faiss = load_faiss()
    query_embedding = np.asarray(embed_texts([query]), dtype="float32")
    faiss.normalize_L2(query_embedding)
    scores, indices = index.search(query_embedding, top_k)
    chunk_lookup = {
        (item["doc_id"], item["chunk_id"]): item
        for item in records
        if item["kind"] == "chunk"
    }
    merged = {}
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0:
            continue
        row = dict(records[idx])
        target_chunk_id = row["chunk_id"]
        canonical = chunk_lookup.get((row["doc_id"], target_chunk_id), row)
        key = (canonical["doc_id"], canonical["chunk_id"])
        existing = merged.get(key)
        matched_by = {row["kind"]}
        if existing:
            matched_by.update(existing.get("matched_by", []))
        collapsed = dict(canonical)
        collapsed["vector_score"] = max(float(score), existing["vector_score"] if existing else float(score))
        collapsed["matched_by"] = sorted(matched_by)
        merged[key] = collapsed
    return sorted(merged.values(), key=lambda item: item["vector_score"], reverse=True)


def search_one_kb(
    root_dir: Path,
    kb_name: str,
    query: str,
    *,
    topk: int | None,
    topn: int | None,
    rerank: bool,
) -> list[dict]:
    config, records, index = load_index_bundle(root_dir, kb_name)
    effective_topk = normalize_positive(topk or config.get("topk", DEFAULT_TOPK), "topk")
    effective_topn = normalize_positive(topn or config.get("topN", DEFAULT_TOPN), "topN")
    if effective_topn > effective_topk:
        raise KBError("topN must be less than or equal to topk.")
    candidates = vector_search(records, index, query, top_k=effective_topk if not rerank else max(effective_topk, 20))
    if not candidates:
        return []
    if not rerank:
        return candidates[:effective_topn]
    rerank_candidates = candidates[: max(effective_topk, 20)]
    reranked = rerank_documents(query, [item["text"] for item in rerank_candidates], top_n=effective_topn)
    final = []
    for item in reranked:
        row = dict(rerank_candidates[item["index"]])
        row["rerank_score"] = float(item["relevance_score"])
        final.append(row)
    return final


def list_kb_names(root_dir: Path) -> list[str]:
    if not root_dir.exists():
        return []
    names = []
    for entry in sorted(root_dir.iterdir(), key=lambda item: item.name):
        if entry.is_dir() and (entry / "config.json").exists():
            config = read_json(entry / "config.json", default={})
            names.append(config.get("kb_name", entry.name))
    return names


def search_across_kbs(
    root_dir: Path,
    query: str,
    *,
    topk: int | None,
    topn: int | None,
    rerank: bool,
) -> list[dict]:
    all_candidates = []
    for kb_name in list_kb_names(root_dir):
        try:
            all_candidates.extend(search_one_kb(root_dir, kb_name, query, topk=topk, topn=topn or DEFAULT_TOPN, rerank=False))
        except KBError:
            continue
    all_candidates.sort(key=lambda item: item["vector_score"], reverse=True)
    effective_topk = normalize_positive(topk or DEFAULT_TOPK, "topk")
    effective_topn = normalize_positive(topn or DEFAULT_TOPN, "topN")
    merged = all_candidates[: max(effective_topk, 20 if rerank else effective_topn)]
    if not rerank:
        return merged[:effective_topn]
    reranked = rerank_documents(query, [item["text"] for item in merged], top_n=effective_topn)
    final = []
    for item in reranked:
        row = dict(merged[item["index"]])
        row["rerank_score"] = float(item["relevance_score"])
        final.append(row)
    return final


def render_markdown_results(results: list[dict]) -> str:
    if not results:
        return "No results.\n"
    grouped = {}
    for item in results:
        grouped.setdefault(item["doc_id"], {"file_name": item["file_name"], "uploaded_at": item["uploaded_at"], "summary": item.get("summary", ""), "chunks": []})
        grouped[item["doc_id"]]["total_chunks"] = max(
            item.get("chunk_count", 0),
            grouped[item["doc_id"]].get("total_chunks", 0),
        )
        grouped[item["doc_id"]]["chunks"].append(item)
    sections = []
    for doc_id in sorted(grouped.keys()):
        entry = grouped[doc_id]
        lines = [
            f"## {entry['file_name']}",
            "",
            f"- uploaded at {entry['uploaded_at']}",
            f"- summary: {entry['summary'] or ''}",
            f"- total chunks: {entry.get('total_chunks', 0)}",
            "",
        ]
        seen_chunks = set()
        for chunk in sorted(entry["chunks"], key=lambda item: item["chunk_id"]):
            if chunk["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(chunk["chunk_id"])
            lines.extend(
                [
                    f"### Chunk {chunk['chunk_id']}",
                    "",
                    chunk["text"],
                    "",
                ]
            )
        sections.append("\n".join(lines).rstrip())
    return "\n\n".join(sections) + "\n"


def normalize_positive(value: int, field: str) -> int:
    if value <= 0:
        raise KBError(f"{field} must be positive.")
    return int(value)


def module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def run_doctor(root_dir: Path) -> int:
    python_version = sys.version.split()[0]
    version_parts = tuple(int(part) for part in python_version.split(".")[:2])
    checks = {
        "python": python_version,
        "python_compatible": version_parts >= (3, 10),
        "python_required": ">=3.10",
        "api_key_present": bool(os.getenv("BAILIAN-SK") or os.getenv("BAILIAN_SK")),
        "requests": module_available("requests"),
        "numpy": module_available("numpy"),
        "faiss": module_available("faiss"),
        "markitdown": module_available("markitdown"),
        "root_dir": str(root_dir),
        "root_dir_exists": root_dir.exists(),
        "root_dir_writable": os.access(root_dir, os.W_OK) if root_dir.exists() else os.access(root_dir.parent, os.W_OK),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operate an OpenClaw knowledge base with Bailian + FAISS.")
    parser.add_argument("--root-dir", default=DEFAULT_ROOT_DIR, help="Knowledge-base root directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check runtime and dependency availability.")
    doctor.set_defaults(func=cmd_doctor)

    convert = subparsers.add_parser("convert", help="Convert a source file into Markdown.")
    convert.add_argument("--input", required=True, help="Source file path.")
    convert.add_argument("--output", required=True, help="Markdown output path.")
    convert.set_defaults(func=cmd_convert)

    index = subparsers.add_parser("index", help="Index one document directory into a KB-level FAISS index.")
    index.add_argument("--kb", required=True, help="Knowledge-base name.")
    index.add_argument("--doc-dir", required=True, help="Document directory, e.g. /root/regulation/{ts}-xx")
    index.add_argument("--topk", type=int, help="FAISS recall top-k to store in KB config.")
    index.add_argument("--topN", type=int, help="Rerank top-N to store in KB config.")
    index.set_defaults(func=cmd_index)

    delete = subparsers.add_parser("delete", help="Delete one document from the KB-level index and persist the result.")
    delete.add_argument("--kb", required=True, help="Knowledge-base name.")
    delete.add_argument("--doc-id", required=True, help="Document directory name, e.g. {ts}-xx")
    delete.set_defaults(func=cmd_delete)

    query = subparsers.add_parser("query", help="Query one KB or all KBs and return Markdown.")
    query.add_argument("--kb", help="Knowledge-base name. Omit to search across all KBs.")
    query.add_argument("--query", required=True, help="Question text.")
    query.add_argument("--topk", type=int, help="FAISS recall top-k override.")
    query.add_argument("--topN", type=int, help="Rerank top-N override.")
    query.add_argument("--rerank", action="store_true", help="Enable rerank.")
    query.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    query.set_defaults(func=cmd_query)

    return parser.parse_args()


def cmd_doctor(args: argparse.Namespace) -> int:
    return run_doctor(Path(args.root_dir))


def cmd_convert(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    markdown = convert_source(input_path)
    write_markdown_output(output_path, markdown)
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "source_sha1": file_sha1(input_path),
                "markdown_length": len(markdown),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    manifest = index_kb(
        root_dir=Path(args.root_dir).expanduser(),
        kb_name=args.kb,
        doc_dir=Path(args.doc_dir).expanduser(),
        topk=args.topk,
        topn=args.topN,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    manifest = delete_from_index(
        root_dir=Path(args.root_dir).expanduser(),
        kb_name=args.kb,
        doc_id=args.doc_id,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).expanduser()
    if args.kb:
        results = search_one_kb(root_dir, args.kb, args.query, topk=args.topk, topn=args.topN, rerank=args.rerank)
    else:
        results = search_across_kbs(root_dir, args.query, topk=args.topk, topn=args.topN, rerank=args.rerank)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_results(results), end="")
    return 0


def main() -> int:
    try:
        args = parse_args()
        return args.func(args)
    except KBError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
