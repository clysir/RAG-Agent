"""灌测试数据脚本 —— 从 MUGE 数据集导入商品到 MySQL,图片落对象存储。

数据流:
1. 解压 data/MUGE.zip 到 data/MUGE/
2. 读 valid_texts.jsonl 建 image_id -> queries 映射(text 作为商品"标题候选")
3. 读 valid_imgs.tsv,逐行处理(image_id\\tbase64-image):
   - 跳过没有关联 query 的图片(没标题不入)
   - base64 解码后落 storage(local_fs / MinIO 抽象)
   - 合成 category/price/stock,插 MySQL products
4. 输出统计:成功多少、跳过多少

为什么 MUGE 当电商商品集:
- MUGE 是阿里达摩院发布的中文电商图文检索数据集(淘宝场景)
- text 是用户检索 query,可当商品搜索词 / 短标题
- image 是商品图,直接做多模态检索

用法:
  python -m scripts.seed_data --limit 2000           # 灌 2000 条
  python -m scripts.seed_data --limit 0 --force      # 全量 ~30K,先清空再灌
  python -m scripts.seed_data --no-storage           # 跳过图片落盘(只灌文本)
"""

import argparse
import asyncio
import base64
import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path

from loguru import logger
from sqlalchemy import delete, select, text as sa_text

from db import Product, SessionLocal
from providers import get_storage

# 合成字段用的类目池 —— MUGE 没原生类目,用这几个常见电商大类随机分配
# 真实场景应该用图像分类器或类目规则映射,这里 demo 简化
CATEGORIES = ["服饰", "家居", "3C数码", "美妆个护", "食品零食", "运动户外", "母婴亲子", "鞋包配饰"]


async def _ensure_extracted(zip_path: Path, extract_dir: Path) -> Path:
    """解压 MUGE.zip(若未解压过)。返回实际数据目录(zip 内可能有顶层 MUGE/ 目录)。"""
    if extract_dir.exists() and any(extract_dir.iterdir()):
        logger.info(f"seed.extracted_exists dir={extract_dir}")
    else:
        logger.info(f"seed.extracting {zip_path} -> {extract_dir.parent}")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir.parent)

    # 探测真实数据根 —— MUGE.zip 解开后通常是 MUGE/ 顶层目录
    candidates = [extract_dir, extract_dir.parent / "MUGE"]
    for c in candidates:
        if (c / "valid_texts.jsonl").exists():
            return c
        for sub in c.iterdir() if c.exists() else []:
            if sub.is_dir() and (sub / "valid_texts.jsonl").exists():
                return sub
    raise FileNotFoundError(f"找不到 valid_texts.jsonl, 检查 {extract_dir}")


def _load_text_map(texts_jsonl: Path) -> dict[str, list[str]]:
    """读 valid_texts.jsonl,返回 image_id -> [query, ...]。"""
    image_to_queries: dict[str, list[str]] = defaultdict(list)
    with open(texts_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            query = (row.get("text") or "").strip()
            if not query:
                continue
            for img_id in row.get("image_ids", []):
                image_to_queries[str(img_id)].append(query)
    logger.info(f"seed.texts_loaded queries_for_images={len(image_to_queries)}")
    return image_to_queries


def _synth_attributes(queries: list[str]) -> tuple[str, str, float, int]:
    """根据 queries 合成 title/description/price/stock。

    - title: 第一条 query(通常较短)
    - description: 所有 query 拼接,模拟"商家描述"
    - price/stock: 随机但稳定(用 image_id 不可能这里没有,只能 random)
    """
    title = queries[0][:200]
    if len(queries) > 1:
        # 用换行拼描述,避免重复 query 当 noise
        unique = list(dict.fromkeys(queries))
        description = "本店推荐特点:\n" + "\n".join(f"- {q}" for q in unique[:5])
    else:
        description = title
    price = round(random.uniform(29, 1299), 2)
    stock = random.randint(20, 500)
    return title, description, price, stock


async def _wipe_products() -> None:
    """清空 products 表 —— 仅 demo 用,避免重复灌。"""
    async with SessionLocal() as session:
        await session.execute(delete(Product))
        await session.commit()
        logger.warning("seed.wiped table=products")


async def _bulk_insert(rows: list[dict]) -> int:
    """批量插入 products,返回插入数。"""
    if not rows:
        return 0
    async with SessionLocal() as session:
        for r in rows:
            session.add(Product(**r))
        await session.commit()
    return len(rows)


async def main(
    zip_path: Path,
    limit: int,
    force: bool,
    skip_storage: bool,
    batch_size: int,
    seed: int,
) -> None:
    random.seed(seed)
    extract_root = Path("data/MUGE")
    extract_root.parent.mkdir(parents=True, exist_ok=True)
    data_dir = await _ensure_extracted(zip_path, extract_root)
    logger.info(f"seed.data_dir={data_dir}")

    image_to_queries = _load_text_map(data_dir / "valid_texts.jsonl")
    imgs_tsv = data_dir / "valid_imgs.tsv"
    if not imgs_tsv.exists():
        raise FileNotFoundError(f"缺 {imgs_tsv}")

    if force:
        await _wipe_products()

    storage = get_storage() if not skip_storage else None
    if storage:
        logger.info(f"seed.storage provider={storage.name}")

    seen_ids: set[str] = set()
    inserted = 0
    skipped_no_text = 0
    skipped_dup = 0
    batch: list[dict] = []

    with open(imgs_tsv, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.rstrip("\n")
            if not raw:
                continue
            parts = raw.split("\t", 1)
            if len(parts) != 2:
                logger.warning(f"seed.bad_line lineno={line_no}")
                continue
            img_id, b64 = parts
            img_id = img_id.strip()
            if img_id in seen_ids:
                skipped_dup += 1
                continue
            seen_ids.add(img_id)

            queries = image_to_queries.get(img_id, [])
            if not queries:
                skipped_no_text += 1
                continue

            object_key = f"products/muge/{img_id}.jpg"
            if storage:
                try:
                    img_bytes = base64.b64decode(b64)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"seed.b64_fail img_id={img_id} err={e}")
                    continue
                await storage.put(object_key, img_bytes, content_type="image/jpeg")

            title, description, price, stock = _synth_attributes(queries)
            batch.append({
                "title": title,
                "description": description,
                "category": random.choice(CATEGORIES),
                "price": price,
                "stock": stock,
                "image_object_key": object_key,
                "merchant_id": None,
            })

            if len(batch) >= batch_size:
                inserted += await _bulk_insert(batch)
                batch = []
                logger.info(f"seed.progress inserted={inserted} skipped_no_text={skipped_no_text}")
            if limit and inserted + len(batch) >= limit:
                break

        if batch:
            inserted += await _bulk_insert(batch)

    logger.info(
        f"seed.done inserted={inserted} skipped_no_text={skipped_no_text} "
        f"skipped_dup={skipped_dup}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="灌 MUGE 数据到 MySQL + storage")
    p.add_argument("--zip", default="data/MUGE.zip", help="MUGE.zip 路径")
    p.add_argument("--limit", type=int, default=2000, help="最多灌多少条,0 = 全量")
    p.add_argument("--force", action="store_true", help="先清空 products 表")
    p.add_argument("--no-storage", action="store_true", help="跳过图片落盘,只插 MySQL")
    p.add_argument("--batch-size", type=int, default=200, help="MySQL 批量插入大小")
    p.add_argument("--seed", type=int, default=42, help="随机种子(类目/价格)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        main(
            zip_path=Path(args.zip),
            limit=args.limit,
            force=args.force,
            skip_storage=args.no_storage,
            batch_size=args.batch_size,
            seed=args.seed,
        )
    )
