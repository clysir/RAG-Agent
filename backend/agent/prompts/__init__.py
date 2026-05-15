"""Prompt 模板占位 —— 真实模板放 .txt 或 .jinja 文件,通过 jinja2 加载。

迁移计划:
- agent/prompts/intent.txt      意图分类
- agent/prompts/query_rewrite.txt  query 改写
- agent/prompts/respond.txt     最终回答(带候选商品上下文)
- agent/prompts/clarify.txt     反问澄清
"""
