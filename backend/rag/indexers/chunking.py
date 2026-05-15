"""父子块切分 —— 离线入库的第一步。

工业实践:
- 子块小,精度高,用于向量召回
- 父块大,上下文完整,用于喂 LLM
- 子块 metadata 里带 parent_id 指回父块
- 父块内容存 MySQL 或单独 collection(便于回查)

简化策略(MVP):
- 按段落 + 句子 + 固定窗口三级切,优先按语义边界
- 不依赖外部库,纯标准库 + re
"""

import re
from dataclasses import dataclass

from config import settings


@dataclass(slots=True)
class Chunk:
    """切分后的块 —— content 是文本,metadata 由调用方决定。"""

    content: str
    chunk_index: int
    parent_index: int  # 子块属于哪个父块;父块自身 parent_index == chunk_index


def _split_by_sentence(text: str) -> list[str]:
    """按中英文标点切句 —— 保留标点,避免语义断裂。"""
    # 中文句末标点 + 英文句末标点
    pattern = r"(?<=[。!?!?\.])\s*"
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]


def _pack(sentences: list[str], target_size: int, overlap: int) -> list[str]:
    """把句子打包成接近 target_size 的块 —— overlap 用句子粒度实现。"""
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for sent in sentences:
        if buf_len + len(sent) > target_size and buf:
            chunks.append("".join(buf))
            # overlap:回退到上一块末尾若干字符的句子
            if overlap > 0:
                back_len = 0
                back: list[str] = []
                for s in reversed(buf):
                    back.insert(0, s)
                    back_len += len(s)
                    if back_len >= overlap:
                        break
                buf = back
                buf_len = back_len
            else:
                buf = []
                buf_len = 0
        buf.append(sent)
        buf_len += len(sent)
    if buf:
        chunks.append("".join(buf))
    return chunks


def split_parent_child(text: str) -> tuple[list[Chunk], list[Chunk]]:
    """切出父块和子块。

    Returns:
        (parents, children) —— children 的 parent_index 指向对应 parents 的 chunk_index。
    """
    cfg = settings.chunking
    # 短文档直接整段返回,避免过度切分
    if len(text) <= cfg.min_chunk_threshold:
        single = Chunk(content=text, chunk_index=0, parent_index=0)
        return [single], [single]

    sentences = _split_by_sentence(text)
    parent_texts = _pack(sentences, cfg.father_chunk_size, cfg.chunk_overlap)
    parents = [
        Chunk(content=t, chunk_index=i, parent_index=i) for i, t in enumerate(parent_texts)
    ]

    # 在每个父块内部再切子块 —— 这样子块的 parent_index 就是它所在父块的 index
    children: list[Chunk] = []
    global_child_idx = 0
    for parent in parents:
        parent_sentences = _split_by_sentence(parent.content)
        child_texts = _pack(parent_sentences, cfg.child_chunk_size, cfg.chunk_overlap // 2)
        for ct in child_texts:
            children.append(
                Chunk(content=ct, chunk_index=global_child_idx, parent_index=parent.chunk_index)
            )
            global_child_idx += 1

    return parents, children
