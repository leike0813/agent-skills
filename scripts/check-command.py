"""Check availability of git and gh on system PATH.

Output: JSON to stdout. Never installs or configures tools.
"""

import json
import shutil
import sys


def main():
    git_path = shutil.which("git")
    gh_path = shutil.which("gh")

    output = {
        "ok": True,
        "git": {"available": git_path is not None, "path": git_path},
        "gh": {"available": gh_path is not None, "path": gh_path},
    }

    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
