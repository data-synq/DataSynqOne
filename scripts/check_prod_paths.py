#!/usr/bin/env python3
"""Check non-root ownership of production bind mounts without modifying data."""

import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPERLESS_UID = int(os.environ.get("PAPERLESS_UID", "1000"))
PAPERLESS_GID = int(os.environ.get("PAPERLESS_GID", "1000"))
EXPECTED = {
    "data/redis": (999, 999),
    "data/postgres": (999, 999),
    "data/vectordb": (999, 999),
    "data/paperless/data": (PAPERLESS_UID, PAPERLESS_GID),
    "data/paperless/media": (PAPERLESS_UID, PAPERLESS_GID),
    "data/paperless/export": (PAPERLESS_UID, PAPERLESS_GID),
    "data/paperless/consume": (PAPERLESS_UID, PAPERLESS_GID),
}
MAX_REPORTED = 20


def access_bits(metadata: os.stat_result, uid: int, gid: int) -> int:
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid == uid:
        return (mode >> 6) & 0o7
    if metadata.st_gid == gid:
        return (mode >> 3) & 0o7
    return mode & 0o7


def main() -> int:
    errors: list[str] = []
    for relative, identity in EXPECTED.items():
        expected_uid, expected_gid = identity
        root = ROOT / relative
        if not root.is_dir():
            errors.append(f"{relative}: directory is missing")
            continue

        paths = [root]
        for directory, dirs, files in os.walk(root):
            paths.extend(Path(directory) / name for name in dirs)
            paths.extend(Path(directory) / name for name in files)
        for path in paths:
            stat = path.lstat()
            required = 0o7 if path.is_dir() else 0o6
            available = access_bits(stat, expected_uid, expected_gid)
            if stat.st_uid != expected_uid or available & required != required:
                errors.append(
                    f"{path.relative_to(ROOT)}: owner {stat.st_uid}:{stat.st_gid}, "
                    f"mode {stat.st_mode & 0o7777:04o}; expected UID {expected_uid} and "
                    f"{'rwx' if path.is_dir() else 'rw'} access for {expected_uid}:{expected_gid}"
                )
                if len(errors) >= MAX_REPORTED:
                    break
        if len(errors) >= MAX_REPORTED:
            break

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) >= MAX_REPORTED:
            print(f"ERROR: stopped after {MAX_REPORTED} ownership errors", file=sys.stderr)
        return 1

    print("production bind-mount ownership validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
