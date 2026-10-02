"""Package metadata version guard tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_package_version_files_agree() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/check_versions.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.startswith("Package versions agree: ")
