"""Dump the FastAPI OpenAPI schema to a JSON file.

CI calls this script then ``git diff --exit-code`` the produced file to
catch undocumented endpoint changes. The schema file is committed so
reviewers see the contract change in the diff.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from apps.api.main import create_app


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: export_openapi.py <output.json>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    app = create_app()
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"[export_openapi] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
