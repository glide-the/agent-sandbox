#!/usr/bin/env python3
"""Read-only environment probe. Does not import GPU packages or install anything."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-prefix', required=True)
    parser.add_argument('--package', action='append', default=[])
    args = parser.parse_args()
    errors = []
    if Path(sys.prefix).resolve() != Path(args.expected_prefix).resolve():
        errors.append('sys.prefix does not match the selected environment')
    packages = {}
    for name in args.package:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
            errors.append('Package not installed: ' + name)
    print(json.dumps({'executable': sys.executable, 'prefix': sys.prefix,
                     'base_prefix': sys.base_prefix, 'python_version': sys.version,
                     'packages': packages, 'errors': errors,
                     'gpu_inference_tested': False}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
