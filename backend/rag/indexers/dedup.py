"""向量 ID 生成与去重 —— 入库幂等的核心。

设计:
- vector_id = sha256(content + source + model_name + model_version + chunk_index)[:16]
- model_name + version 进 hash,换模型时旧 ID 自然失效,不会冲突
- 16 位 hex(64 bit)碰撞概率极低,长度对人类可读且 Milvus 友好
- 入库前先 query Milvus 看主键是否存在,存在则跳过 embedding 调用
"""

import hashlib


def make_vector_id(
    content: str,
    source: str,
    model_name: str,
    model_version: str = "v1",
    chunk_index: int = 0,
) -> int:
    """生成稳定的向量 ID —— 同样的内容+来源+模型,产出同样的 ID。

    Args:
        content: 实际向量化的文本/图片标识(图片用文件路径或 url)
        source: 文档来源,通常是商品 ID 或文件名,加进 hash 避免不同来源相同短文本冲突
        model_name: embedding 模型名,如 BAAI/bge-m3
        model_version: 模型版本 tag,业务可控
        chunk_index: 父子块场景下区分同一文档的不同 chunk

    Returns:
        16 位十六进制截断后转 int64,可作为 Milvus 主键。
    """
    payload = f"{content}|{source}|{model_name}|{model_version}|{chunk_index}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    # Milvus 主键支持 INT64,把 hex 转 int 截断到 63 位以避免符号位
    return int(digest, 16) & 0x7FFFFFFFFFFFFFFF
