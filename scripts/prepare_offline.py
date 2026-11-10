"""Online wheelhouse preparation for the SAME Python/OS/architecture as the target."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("offline-bundle"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/prepare_models.py"),
            "--output",
            str(args.output / "models"),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(root),
            "--wheel-dir",
            str(args.output / "wheelhouse"),
        ],
        check=True,
    )
    shutil.copy(root / "docs/offline.md", args.output / "INSTALL.md")
    print("Bundle prepared. Tesseract native runtime is separate; see INSTALL.md.")


if __name__ == "__main__":
    main()
