#!/usr/bin/env python3
"""Run the full pipeline: extract PDF -> build graph JSON."""

import subprocess
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent


def run(script: str) -> None:
    result = subprocess.run([sys.executable, str(PIPELINE / script)], check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> int:
    run("extract.py")
    run("build.py")
    print("\nDone. View the graph:")
    print("  python scripts/serve.py")
    print("  Then open http://localhost:5000/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
