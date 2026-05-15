"""RRF 融合 —— Reciprocal Rank Fusion,把多路召回合并成一个排好序的候选列表。

公式: score(doc) = sum_{q in queries} 1 / (k + rank_q(doc))
- k 一般取 60(论文推荐)
- rank 从 1 开始;未命中的 query 不贡献分数
- 优点:不依赖各路原始分数的尺度,鲁棒性强
"""

from collections import defaultdict


def rrf_fuse(
    rank_lists: list[list[dict]], k: int = 60, top_k: int = 30
) -> list[dict]:
    """融合多路结果。

    Args:
        rank_lists: 每路召回的结果列表,每项 dict 必须有 product_id 字段
        k: RRF 常数
        top_k: 融合后返回的条数

    Returns:
        [{product_id, score, sources}],按 score 降序。sources 记录命中了哪几路。
    """
    aggregated: dict[int, float] = defaultdict(float)
    sources: dict[int, list[int]] = defaultdict(list)
    payload: dict[int, dict] = {}

    for path_idx, hits in enumerate(rank_lists):
        for rank, item in enumerate(hits, start=1):
            pid = item.get("product_id")
            if pid is None:
                continue
            aggregated[pid] += 1.0 / (k + rank)
            sources[pid].append(path_idx)
            # 保留第一次见到的额外字段(text/parent_index 等),便于后续 rerank/展示
            if pid not in payload:
                payload[pid] = {kk: vv for kk, vv in item.items() if kk != "score"}

    fused = [
        {**payload[pid], "product_id": pid, "score": s, "sources": sources[pid]}
        for pid, s in aggregated.items()
    ]
    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused[:top_k]
