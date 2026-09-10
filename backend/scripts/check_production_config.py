#!/usr/bin/env python3
"""Fail fast when the Stage 20 production environment is unsafe."""
from ops.runtime import validate_production_environment


def main() -> int:
    result = validate_production_environment()
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if result.ok:
        print("Production configuration validation: PASS")
        return 0
    print("Production configuration validation: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
