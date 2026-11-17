"""Alohida jarayon. 60 soniyadan oshsa butun jarayon o'chiriladi."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from services.errors import UserFacingError
from services.runner import execute_sync


def main() -> None:
    result_path = Path(sys.argv[1])
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    try:
        output = execute_sync(
            action=payload["action"],
            inputs=[Path(item) for item in payload["inputs"]],
            out_dir=Path(payload["out_dir"]),
            original_name=payload["original_name"],
            pages=payload.get("pages"),
            angle=payload.get("angle"),
            watermark=bool(payload.get("watermark")),
        )
        data = {
            "ok": True,
            "filename": output.filename,
            "stored_name": output.path.name,
            "before": output.before,
            "after": output.after,
        }
    except UserFacingError as exc:
        data = {"ok": False, "error": exc.key, "params": exc.params}
    except Exception:
        traceback.print_exc()
        data = {"ok": False, "error": "error_generic", "params": {}}
    result_path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    main()
