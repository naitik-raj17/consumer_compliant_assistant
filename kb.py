import logging
import re
from pathlib import Path

import numpy as np
import requests
from pypdf import PdfReader

import config
import db

log = logging.getLogger(__name__)

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
BATCH = 16


class OllamaError(Exception):
    pass


def chunk_text(text: str, size: int = config.CHUNK_SIZE) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start, end)
            if cut > start + size * 0.6:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


def embed(texts: list[str], prefix: str = DOC_PREFIX) -> np.ndarray:
    """Return an (n, d) float32 matrix of L2-normalised embeddings. Raises OllamaError."""
    inputs = [prefix + t for t in texts]
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/embed",
                          json={"model": config.EMBED_MODEL, "input": inputs},
                          timeout=config.EMBED_TIMEOUT)
        if r.ok:
            vecs = r.json().get("embeddings")
        elif r.status_code == 404 and "model" not in r.text.lower():
            vecs = []  # older Ollama: legacy endpoint, one text at a time
            for t in inputs:
                lr = requests.post(f"{config.OLLAMA_URL}/api/embeddings",
                                   json={"model": config.EMBED_MODEL, "prompt": t},
                                   timeout=config.EMBED_TIMEOUT)
                lr.raise_for_status()
                vecs.append(lr.json()["embedding"])
        else:
            raise OllamaError(f"Embedding failed ({r.status_code}): {r.text[:200]}")
    except requests.RequestException as e:
        raise OllamaError(f"Ollama unreachable at {config.OLLAMA_URL}: {e}") from e
    if not vecs or len(vecs) != len(texts):
        raise OllamaError("Embedding response was empty or incomplete")
    return _normalize(np.asarray(vecs, dtype=np.float32))


def _embed_batched(texts: list[str]) -> list[bytes]:
    out: list[bytes] = []
    for i in range(0, len(texts), BATCH):
        out.extend(v.tobytes() for v in embed(texts[i:i + BATCH]))
    return out


def ingest_text(source: str, category: str, text: str) -> tuple[int, bool]:
    """Chunk, try to embed, store. Returns (chunk_count, embedded)."""
    chunks = chunk_text(text)
    if not chunks:
        return 0, False
    try:
        embs: list[bytes | None] = _embed_batched(chunks)
        embedded = True
    except OllamaError as e:
        log.warning("Storing %s without embeddings: %s", source, e)
        embs, embedded = [None] * len(chunks), False
    db.add_chunks([(source, category, c, e) for c, e in zip(chunks, embs)])
    log.info("Ingested %s: %d chunks (embedded=%s)", source, len(chunks), embedded)
    return len(chunks), embedded


def ingest_pdf(path: str | Path, category: str = "general") -> tuple[int, bool]:
    path = Path(path)
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if len(text.strip()) < 20:
        raise ValueError("No extractable text found in this PDF (it may be a scanned image).")
    return ingest_text(path.name, category, text)


def seed_if_empty(seed_dir: Path = config.KB_SEED_DIR) -> int:
    if db.chunk_count() > 0:
        return 0
    files = sorted(Path(seed_dir).glob("*.txt"))
    if not files:
        log.warning("No KB seed files found in %s", seed_dir)
    total = 0
    for f in files:
        n, _ = ingest_text(f.name, "general", f.read_text(encoding="utf-8"))
        total += n
    return total


def reembed_missing() -> int:
    rows = db.chunks_missing_embedding()
    done = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        vecs = embed([r["text"] for r in batch])
        for r, v in zip(batch, vecs):
            db.set_chunk_embedding(r["id"], v.tobytes())
            done += 1
    return done


def startup_sync() -> str:
    seeded = seed_if_empty()
    try:
        fixed = reembed_missing()
    except OllamaError as e:
        log.info("Skipping re-embed: %s", e)
        fixed = 0
    return f"seeded={seeded} reembedded={fixed}"


def stats() -> dict:
    return db.kb_stats()
