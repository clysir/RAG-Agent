"""模型预下载 —— 绕开 hf-mirror 不支持的 resolve-cache 接口。

策略:
- 用 snapshot_download + ignore_patterns 跳过 imgs/、.DS_Store 等无关文件
- 走 HF_ENDPOINT 镜像
- 下载完成后,FlagEmbedding / transformers 直接从本地缓存加载,不再触发网络请求

运行:
    .venv/bin/python -m scripts.download_models
"""

import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 关闭 xet 协议(走老的 resolve 接口,镜像兼容性更好)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
# 不打 telemetry
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from huggingface_hub import snapshot_download
from loguru import logger

# 只下载推理必需的文件,跳过仓库里的截图/示例/metadata
_ALLOW = [
    "*.json",
    "*.txt",
    "*.safetensors",
    "*.bin",
    "*.model",
    "tokenizer*",
    "vocab*",
    "merges*",
    "special_tokens*",
    "added_tokens*",
    "config*.json",
    "preprocessor_config.json",
    "*.py",  # 部分模型自带 modeling_xxx.py(动态加载)
]
_IGNORE = [
    "imgs/*",
    "images/*",
    "*.DS_Store",
    "*.md",
    "*.png",
    "*.jpg",
    "*.gif",
    "*.bmp",
    "*.svg",
    "onnx/*",
    "openvino/*",
    "1_Pooling/*.bin",  # sentence-transformers 老格式,我们走 safetensors
]

MODELS = [
    "BAAI/bge-m3",
    "OFA-Sys/chinese-clip-vit-base-patch16",
    "BAAI/bge-reranker-v2-m3",
]


def main():
    for repo in MODELS:
        logger.info(f"start downloading {repo}")
        path = snapshot_download(
            repo_id=repo,
            allow_patterns=_ALLOW,
            ignore_patterns=_IGNORE,
            max_workers=4,
        )
        logger.info(f"done {repo} -> {path}")
    logger.info("all done")


if __name__ == "__main__":
    main()
