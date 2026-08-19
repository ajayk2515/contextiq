"""Fail if critical production packages lack CPython 3.12 ARM64 wheels."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

CRITICAL_PACKAGES = {
    "asyncpg",
    "numpy",
    "onnxruntime",
    "opencv-python",
    "pypdfium2",
    "scipy",
    "tiktoken",
    "tokenizers",
    "torch",
    "torchvision",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify binary wheels for CPython 3.12 on Linux aarch64."
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "requirements-prod.txt",
    )
    args = parser.parse_args()
    requirements = args.requirements.resolve()
    if not requirements.is_file():
        parser.error(f"requirements file not found: {requirements}")

    pins: list[str] = []
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if "==" in line and line.split("==", 1)[0].lower() in CRITICAL_PACKAGES:
            pins.append(line)
    missing = sorted(CRITICAL_PACKAGES - {pin.split("==", 1)[0].lower() for pin in pins})
    if missing:
        parser.error(f"critical packages are not pinned: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="contextiq-arm64-wheels-") as destination:
        command = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            destination,
            "--only-binary=:all:",
            "--platform=manylinux2014_aarch64",
            "--platform=manylinux_2_27_aarch64",
            "--platform=manylinux_2_28_aarch64",
            "--implementation=cp",
            "--python-version=3.12",
            "--abi=cp312",
            "--no-deps",
            *pins,
        ]
        result = subprocess.run(command, check=False)
    if result.returncode:
        print(
            "ARM64 wheel verification failed. Do not build the release from source; "
            "review the pinned package versions.",
            file=sys.stderr,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
