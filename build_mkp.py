#!/usr/bin/env python3
"""Build a reproducible MKP from the checked-in metadata and plugin files."""
import ast
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent


def add_bytes(archive, name, data):
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    entry.mode = 0o644
    archive.addfile(entry, io.BytesIO(data))


def build():
    metadata = json.loads((ROOT / "info.json").read_text())
    if ast.literal_eval((ROOT / "info").read_text()) != metadata:
        raise ValueError("info and info.json must match")
    output = ROOT / f"{metadata['name']}-{metadata['version']}.mkp"
    # MKP is an uncompressed outer tar with one tar per installation category.
    with tarfile.open(output, "w") as archive:
        for name in ("info", "info.json"):
            add_bytes(archive, name, (ROOT / name).read_bytes())
        for category, files in metadata["files"].items():
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w") as inner:
                for name in sorted(files):
                    add_bytes(inner, name, (ROOT / category / name).read_bytes())
            add_bytes(archive, category + ".tar", payload.getvalue())
    print(output)


if __name__ == "__main__":
    build()
