"""Recall past observations relevant to the current screen context."""
from loguru import logger
from src import memory, llm


def recall_context(current_text: str, n: int = 5) -> str:
    """
    Semantic search for past observations related to current_text.
    Returns a formatted string of past notes to inject into LLM context.
    """
    results = memory.semantic_search(current_text, n=n)
    if not results:
        return ""

    lines = ["### Related past observations:"]
    for r in results:
        ts_short = r["ts"][:16] if r["ts"] else "?"
        app = f" ({r['app']})" if r["app"] else ""
        lines.append(f"- [{ts_short}{app}] {r['document'][:200]}")
    return "\n".join(lines)


def answer_recall_query(query: str) -> str:
    """
    Answer a natural-language recall question using stored observations.
    E.g. "What did I read about Python last week?"
    """
    results = memory.semantic_search(query, n=5)
    if not results:
        return "No related observations found in memory."

    context_block = "\n".join(
        f"[{r['ts'][:16]}] {r['document']}" for r in results
    )
    prompt = (
        f"The user asked: {query}\n\n"
        f"Based on these past screen observations:\n{context_block}\n\n"
        "Answer the question concisely based only on the information above. "
        "If the answer is not in the observations, say so."
    )
    return llm.generate(prompt)
