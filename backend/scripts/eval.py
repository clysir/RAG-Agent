"""离线评估脚本 —— 算 Recall@K / MRR / 平均 latency,RAG 质量监控线。

数据格式:eval_queries.jsonl,每行
    {"query": "适合通勤的双肩包", "expected_product_ids": [123, 456], "category": "服饰" (可选)}

跑法:
    python -m scripts.eval                          # 默认读 tests/eval_queries.jsonl
    python -m scripts.eval --file other.jsonl       # 指定其他文件
    python -m scripts.eval --top-k 20               # K 取 20
    python -m scripts.eval --concurrent 4           # 并发查询数
    python -m scripts.eval --output report.json     # 把结果落盘

输出:
- Recall@1 / @5 / @10 / @20
- MRR(Mean Reciprocal Rank)
- 平均、p50、p95 latency
"""

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from loguru import logger

from db import SessionLocal
from rag.retrievers import hybrid_search


async def _run_one(
    query: str,
    expected: set[int],
    top_k: int,
    category: str | None,
    max_price: float | None,
) -> dict:
    """跑一条评估 query,返回 hit 位置 / 命中数 / latency 等。"""
    t0 = time.perf_counter()
    async with SessionLocal() as session:
        try:
            candidates = await hybrid_search(
                query=query, session=session, category=category, max_price=max_price
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"eval.search_fail query={query!r} err={e}")
            return {"query": query, "hits": [], "elapsed_ms": -1, "error": str(e)}
    elapsed_ms = (time.perf_counter() - t0) * 1000

    ranked_ids = [c.product_id for c in candidates[:top_k]]
    # hit 位置(1-based),取每个 expected 的最佳排名
    best_rank: int | None = None
    matched: list[int] = []
    for rank, pid in enumerate(ranked_ids, start=1):
        if pid in expected:
            matched.append(pid)
            if best_rank is None:
                best_rank = rank
    return {
        "query": query,
        "expected": list(expected),
        "ranked": ranked_ids,
        "matched": matched,
        "best_rank": best_rank,
        "elapsed_ms": elapsed_ms,
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _summarize(results: list[dict], top_k_list: list[int]) -> dict:
    """汇总 Recall@K / MRR / latency。"""
    valid = [r for r in results if r.get("error") is None]
    n = len(valid)
    summary: dict = {"total": len(results), "succeeded": n}

    # Recall@K: 至少一个 expected 出现在前 K
    for k in top_k_list:
        hits = 0
        for r in valid:
            top_k_ids = set(r["ranked"][:k])
            if top_k_ids & set(r["expected"]):
                hits += 1
        summary[f"recall@{k}"] = round(hits / n, 4) if n else 0.0

    # MRR: 每个 query 的 1/best_rank 取平均(没命中算 0)
    rr = []
    for r in valid:
        if r["best_rank"]:
            rr.append(1.0 / r["best_rank"])
        else:
            rr.append(0.0)
    summary["mrr"] = round(sum(rr) / n, 4) if n else 0.0

    # latency
    lats = [r["elapsed_ms"] for r in valid if r["elapsed_ms"] >= 0]
    if lats:
        summary["latency_ms_avg"] = round(statistics.mean(lats), 1)
        summary["latency_ms_p50"] = round(_percentile(lats, 0.5), 1)
        summary["latency_ms_p95"] = round(_percentile(lats, 0.95), 1)
        summary["latency_ms_max"] = round(max(lats), 1)
    return summary


async def main(file: Path, top_k: int, concurrent: int, output: Path | None) -> None:
    if not file.exists():
        raise FileNotFoundError(f"评估文件不存在: {file}")

    rows: list[dict] = []
    with open(file, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(f"eval.bad_line lineno={line_no} err={e}")
                continue
            if "query" not in r or "expected_product_ids" not in r:
                logger.warning(f"eval.missing_fields lineno={line_no}")
                continue
            rows.append(r)
    logger.info(f"eval.loaded queries={len(rows)} file={file}")

    sem = asyncio.Semaphore(concurrent)

    async def _bounded(r: dict) -> dict:
        async with sem:
            return await _run_one(
                query=r["query"],
                expected=set(r["expected_product_ids"]),
                top_k=top_k,
                category=r.get("category"),
                max_price=r.get("max_price"),
            )

    results = await asyncio.gather(*[_bounded(r) for r in rows])

    summary = _summarize(results, [1, 5, 10, 20])
    summary["top_k_used"] = top_k
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "details": results}, f, ensure_ascii=False, indent=2)
        logger.info(f"eval.saved file={output}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="跑 RAG 评估")
    p.add_argument("--file", type=Path, default=Path("tests/eval_queries.jsonl"))
    p.add_argument("--top-k", type=int, default=10, help="评估 top-K(用于 Recall@K 的上界)")
    p.add_argument("--concurrent", type=int, default=4, help="并发 query 数")
    p.add_argument("--output", type=Path, default=None, help="输出 JSON 报告路径")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.file, args.top_k, args.concurrent, args.output))
