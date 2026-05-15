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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_snapshots (
            ts          TEXT NOT NULL,
            app_key     TEXT NOT NULL,
            title       TEXT,
            category    TEXT,
            seconds     REAL NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_snapshots(ts)"
    )
    conn.commit()
    return conn


def log_activity_snapshot(app_key: str, title: str, category: str, seconds: float) -> None:
    """Append a 'user spent N seconds on this app since last snapshot' row."""
    if seconds <= 0:
        return
    with _db() as conn:
        conn.execute(
            "INSERT INTO activity_snapshots VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), app_key, title, category, seconds),
        )
        conn.commit()


def daily_activity_summary(day: str = "") -> list[dict]:
    """
    Return today's per-app totals: [{app_key, title, category, total_seconds}, ...]
    sorted by total_seconds desc. `day` is YYYY-MM-DD (defaults to today).
    """
    day = day or datetime.now().strftime("%Y-%m-%d")
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT app_key,
                   MAX(title)      AS title,
                   MAX(category)   AS category,
                   SUM(seconds)    AS total
            FROM   activity_snapshots
            WHERE  substr(ts, 1, 10) = ?
            GROUP  BY app_key
            ORDER  BY total DESC
            """,
            (day,),
        )
        return [
            {"app_key": r[0], "title": r[1], "category": r[2], "total_seconds": r[3]}
            for r in cur.fetchall()
        ]


def daily_category_totals(day: str = "") -> dict[str, float]:
    """Return {category: total_seconds} for the given day (default: today)."""
    day = day or datetime.now().strftime("%Y-%m-%d")
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT category, SUM(seconds)
            FROM   activity_snapshots
            WHERE  substr(ts, 1, 10) = ?
            GROUP  BY category
            """,
            (day,),
        )
        return {row[0] or "other": row[1] for row in cur.fetchall()}


def weekly_daily_totals(days: int = 7) -> list[dict]:
    """
    Return one row per calendar day (oldest first) for the last N days:
        [{"day": "YYYY-MM-DD", "total": seconds, "categories": {cat: seconds}}, ...]
    Days with no activity are included with empty categories.
    """
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    start_iso = start.isoformat()
    rows_by_day: dict[str, dict] = {
        (start + timedelta(days=i)).isoformat(): {"day": (start + timedelta(days=i)).isoformat(),
                                                  "total": 0.0,
                                                  "categories": {}}
        for i in range(days)
    }
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT substr(ts, 1, 10) AS d, COALESCE(category, 'other') AS c, SUM(seconds)
            FROM   activity_snapshots
            WHERE  substr(ts, 1, 10) >= ?
            GROUP  BY d, c
            """,
            (start_iso,),
        )
        for d, c, sec in cur.fetchall():
            if d not in rows_by_day:
                continue
            rows_by_day[d]["categories"][c] = sec
            rows_by_day[d]["total"] += sec
    return [rows_by_day[k] for k in sorted(rows_by_day.keys())]


def weekly_top_apps(days: int = 7, limit: int = 10) -> list[dict]:
    """Top apps over the last N days (today inclusive)."""
    today = datetime.now().date()
    start_iso = (today - timedelta(days=days - 1)).isoformat()
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT app_key,
                   MAX(title)    AS title,
                   MAX(category) AS category,
                   SUM(seconds)  AS total
            FROM   activity_snapshots
            WHERE  substr(ts, 1, 10) >= ?
            GROUP  BY app_key
            ORDER  BY total DESC
            LIMIT  ?
            """,
            (start_iso, limit),
        )
        return [
            {"app_key": r[0], "title": r[1], "category": r[2], "total_seconds": r[3]}
            for r in cur.fetchall()
        ]


def productive_streak(min_seconds: float = 3600.0) -> int:
    """
    Count consecutive days ending today with at least `min_seconds` of
    'productive' category time. 0 if today doesn't meet the bar.
    """
    today = datetime.now().date()
    streak = 0
    with _db() as conn:
        for i in range(0, 365):  # cap at one year for safety
            d = (today - timedelta(days=i)).isoformat()
            cur = conn.execute(
                "SELECT COALESCE(SUM(seconds),0) FROM activity_snapshots "
                "WHERE substr(ts,1,10)=? AND category='productive'",
                (d,),
            )
            total = cur.fetchone()[0] or 0
            if total >= min_seconds:
                streak += 1
            else:
                break
    return streak


def skill_graph(days: int = 30, max_nodes: int = 25) -> dict:
    """
    Build a skill graph from activity_snapshots over the last N days.

    Skills are derived at query time from (app_key, title) — no LLM, no extra
    storage. Two skills are linked if practised on the same calendar day;
    edge weight = number of shared days (the plan's "interlinking skills of
    the same branch").

    Returns {"nodes": [{id, label, seconds}], "edges": [{from, to, weight}],
             "totals": [{skill, seconds}]} — nodes capped at max_nodes by time.
    """
    from itertools import combinations
    from src import skills as _skills

    today = datetime.now().date()
    start_iso = (today - timedelta(days=days - 1)).isoformat()

    skill_seconds: dict[str, float] = {}
    day_skills: dict[str, set[str]] = {}

    with _db() as conn:
        cur = conn.execute(
            """
            SELECT substr(ts,1,10) AS d, app_key, title, SUM(seconds)
            FROM   activity_snapshots
            WHERE  substr(ts,1,10) >= ?
            GROUP  BY d, app_key, title
            """,
            (start_iso,),
        )
        rows = cur.fetchall()

    for day, app_key, title, secs in rows:
        skill = _skills.extract_skill(app_key or "", title or "")
        if not skill:
            continue
        skill_seconds[skill] = skill_seconds.get(skill, 0.0) + (secs or 0.0)
        day_skills.setdefault(day, set()).add(skill)

    # Edge weights = shared-day count between every co-active skill pair
    edge_w: dict[tuple[str, str], int] = {}
    for sk_set in day_skills.values():
        for a, b in combinations(sorted(sk_set), 2):
            edge_w[(a, b)] = edge_w.get((a, b), 0) + 1

    # Keep the top skills by time so the graph stays readable
    top = sorted(skill_seconds.items(), key=lambda kv: kv[1], reverse=True)[:max_nodes]
    keep = {s for s, _ in top}

    nodes = [{"id": s, "label": s, "seconds": round(sec, 1)} for s, sec in top]
    edges = [
        {"from": a, "to": b, "weight": w}
        for (a, b), w in sorted(edge_w.items(), key=lambda kv: kv[1], reverse=True)
        if a in keep and b in keep
    ]
    totals = [{"skill": s, "seconds": round(sec, 1)} for s, sec in top]
    return {"nodes": nodes, "edges": edges, "totals": totals}


def best_day_in_window(category: str = "productive", days: int = 30) -> dict:
    """
    Return {'day': 'YYYY-MM-DD', 'seconds': N} — the day in the last N days
    with the most time spent in `category`. Empty dict if no data.
    """
    today = datetime.now().date()
    start_iso = (today - timedelta(days=days - 1)).isoformat()
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT substr(ts,1,10) AS d, SUM(seconds) AS total
            FROM   activity_snapshots
            WHERE  substr(ts,1,10) >= ? AND category = ?
            GROUP  BY d
            ORDER  BY total DESC
            LIMIT  1
            """,
            (start_iso, category),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"day": row[0], "seconds": row[1]}


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
