"""让 `python -m app` 走到 cli.main —— 必须在所有重 import 之前覆盖模式。"""

from app.core.cli import main

main()
