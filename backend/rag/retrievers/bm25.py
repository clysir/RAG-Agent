"""BM25 关键词检索 —— 稀疏召回,补稠密向量的不足(精确匹配、罕见词、品牌名)。

实现策略:
- 内存版 BM25(rank-bm25 库),适合 MVP 和中小规模(几万到几十万 SKU)
- 索引在进程启动时从 MySQL 全量加载一次,后续增量更新或定期刷新
- 大规模生产可换 Elasticsearch / OpenSearch / Tantivy

注意:
- 这里只放检索接口,索引构建由 `build_index_bm25` 在启动或 Celery 任务里完成
"""

import re
from threading import Lock

from loguru import logger


class BM25Index:
    """BM25 内存索引 —— 进程级单例,thread-safe 重建。

    成员变量:
    - product_ids: 文档 id 列表,顺序与 docs 对齐
    - docs: tokenized 文档列表
    - bm25: rank_bm25.BM25Okapi 实例
    """

    def __init__(self) -> None:
        self.product_ids: list[int] = []
        self.docs: list[list[str]] = []
        self.bm25 = None
        self._lock = Lock()

    def rebuild(self, items: list[tuple[int, str]]) -> None:
        """全量重建索引 —— items: [(product_id, full_text), ...]。"""
        from rank_bm25 import BM25Okapi

        with self._lock:
            self.product_ids = [pid for pid, _ in items]
            self.docs = [_tokenize(t) for _, t in items]
            self.bm25 = BM25Okapi(self.docs) if self.docs else None
            logger.info(f"bm25.rebuild docs={len(self.docs)}")

    def search(self, query: str, top_k: int = 30) -> list[dict]:
        """BM25 检索 —— 返回 [{product_id, score}, ...]。"""
        if self.bm25 is None or not self.docs:
            return []
        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)
        # argsort 取 top_k,只保留正分(无匹配的会是 0 或负)
        indexed = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
        indexed.sort(key=lambda x: x[1], reverse=True)
        indexed = indexed[:top_k]
        return [{"product_id": self.product_ids[i], "score": s} for i, s in indexed]


# 进程内单例 —— 不要在业务代码里 new
_index = BM25Index()


def get_bm25_index() -> BM25Index:
    return _index


def _tokenize(text: str) -> list[str]:
    """简化分词 —— 中文按字粒度切 + 英文/数字按空格,适合 MVP。

    生产建议接 jieba 或 lac,但当前不引入额外依赖。
    """
    text = text.lower()
    # 中文逐字 + 英数字串
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
        elif ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf))
                buf = []
    if buf:
        tokens.append("".join(buf))
    # 过滤过短噪声
    return [t for t in tokens if len(t) >= 1]
