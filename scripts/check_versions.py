"""Check that Cargo and Python package metadata use the same release version."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def package_versions(cargo_toml: Path, pyproject_toml: Path) -> tuple[str, str]:
    """Read the version fields used by Cargo and Python packaging."""
    cargo = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
    python = tomllib.loads(pyproject_toml.read_text(encoding="utf-8"))
    return cargo["package"]["version"], python["project"]["version"]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cargo_version, python_version = package_versions(
        root / "Cargo.toml", root / "pyproject.toml"
    )
    if cargo_version != python_version:
        print(
            f"Package versions differ: Cargo.toml={cargo_version}, "
            f"pyproject.toml={python_version}",
            file=sys.stderr,
        )
        return 1
    print(f"Package versions agree: {cargo_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
