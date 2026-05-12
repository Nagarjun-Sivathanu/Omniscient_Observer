"""
Long-term memory: SQLite for structured log + ChromaDB for semantic search.
All embeddings generated via nomic-embed-text (Ollama).
"""
import uuid
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import chromadb
from loguru import logger

from src.config import DB_PATH, CHROMA_PATH, PRUNE_DAYS
from src import llm

# ── SQLite ────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            id        TEXT PRIMARY KEY,
            ts        TEXT NOT NULL,
            source    TEXT,
            app       TEXT,
            ocr_text  TEXT,
            summary   TEXT
        )
    """)
    conn.commit()
    return conn


def log_observation(ocr_text: str, summary: str = "", app: str = "", source: str = "poll") -> str:
    """Insert a raw observation into SQLite. Returns the new row id."""
    oid = str(uuid.uuid4())
    ts  = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "INSERT INTO observations VALUES (?,?,?,?,?,?)",
            (oid, ts, source, app, ocr_text[:8000], summary),
        )
        conn.commit()
    return oid


def prune_old_observations() -> int:
    """Delete observations older than PRUNE_DAYS. Returns count deleted."""
    cutoff = (datetime.now() - timedelta(days=PRUNE_DAYS)).isoformat()
    with _db() as conn:
        cur = conn.execute("DELETE FROM observations WHERE ts < ?", (cutoff,))
        conn.commit()
        return cur.rowcount


# ── ChromaDB ──────────────────────────────────────────────────────────────────

def _collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name="observations",
        metadata={"hnsw:space": "cosine"},
    )


def store_embedding(text: str, summary: str, app: str = "", obs_id: str = "") -> bool:
    """Embed `summary` and store in ChromaDB with metadata."""
    embedding = llm.embed(summary or text)
    if not embedding:
        return False
    oid = obs_id or str(uuid.uuid4())
    try:
        col = _collection()
        col.add(
            ids=[oid],
            embeddings=[embedding],
            documents=[summary or text[:1000]],
            metadatas=[{
                "ts":  datetime.now().isoformat(),
                "app": app,
            }],
        )
        return True
    except Exception as e:
        logger.error(f"ChromaDB store failed: {e}")
        return False


def semantic_search(query: str, n: int = 5) -> list[dict]:
    """
    Return top-n semantically similar observations.
    Each result: {id, document, app, ts, distance}
    """
    q_embed = llm.embed(query)
    if not q_embed:
        return []
    try:
        col = _collection()
        res = col.query(query_embeddings=[q_embed], n_results=n)
        results = []
        for i, doc in enumerate(res["documents"][0]):
            results.append({
                "id":       res["ids"][0][i],
                "document": doc,
                "app":      res["metadatas"][0][i].get("app", ""),
                "ts":       res["metadatas"][0][i].get("ts", ""),
                "distance": res["distances"][0][i],
            })
        return results
    except Exception as e:
        logger.error(f"ChromaDB search failed: {e}")
        return []
