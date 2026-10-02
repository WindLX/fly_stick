"""Check that Cargo and Python package metadata use the same release version."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def package_versions(root: Path) -> dict[str, str]:
    """Read release versions from source metadata and both lockfiles."""
    cargo = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
    cargo_lock = tomllib.loads((root / "Cargo.lock").read_text(encoding="utf-8"))
    python = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    uv_lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    cargo_locked = [
        package["version"]
        for package in cargo_lock["package"]
        if package["name"] == "fly_stick"
    ]
    uv_locked = [
        package["version"]
        for package in uv_lock["package"]
        if package["name"] == "fly-stick"
    ]
    if len(cargo_locked) != 1 or len(uv_locked) != 1:
        raise ValueError(
            "Each lockfile must contain exactly one local fly_stick package"
        )
    return {
        "Cargo.toml": cargo["package"]["version"],
        "Cargo.lock": cargo_locked[0],
        "pyproject.toml": python["project"]["version"],
        "uv.lock": uv_locked[0],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    versions = package_versions(root)
    if len(set(versions.values())) != 1:
        print(
            "Package versions differ: "
            + ", ".join(f"{name}={version}" for name, version in versions.items()),
            file=sys.stderr,
        )
        return 1
    print(f"Package versions agree: {next(iter(versions.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
