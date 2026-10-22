"""零安装入口：python3 <skill>/scripts/transcript_shaker/__main__.py <transcript>。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transcript_shaker.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
