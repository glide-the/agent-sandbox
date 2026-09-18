#!/usr/bin/env python3
"""Verify the documentation package hashes. This is not a service integration test."""
from pathlib import Path
import hashlib
import json
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sums = root / 'SHA256SUMS'
    if not sums.is_file():
        print('FAIL: SHA256SUMS is missing', file=sys.stderr)
        return 1
    count, errors = 0, []
    for line in sums.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, relative = line.split('  ', 1)
        file = (root / relative).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            errors.append('Missing or unsafe path: ' + relative)
            continue
        actual = hashlib.sha256(file.read_bytes()).hexdigest()
        if actual != digest:
            errors.append('SHA256 mismatch: ' + relative)
        count += 1
    print(json.dumps({'checked_files': count, 'passed': not errors, 'errors': errors,
                     'scope': 'documentation-package integrity only; no model/service/plugin runtime test'},
                    ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
