"""Run the diagnostic API and historical replay on loopback; never trains or evaluates test data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--local-config", type=Path, default=ROOT / ".local/phase6/runtime.json")
    parser.add_argument("--llm-config", type=Path,
                        help="Optional ignored server-only JSON environment mapping; never put keys in CLI arguments")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a local port in 1024..65535")
    if not os.environ.get("DATABASE_URL") and args.local_config.exists():
        config = json.loads(args.local_config.read_text(encoding="utf-8"))
        os.environ["DATABASE_URL"] = config["database_url"]
    os.environ.setdefault("OILWELL_ROOT", str(ROOT))
    if args.llm_config is not None:
        allowed = {"LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "LLM_MAX_CALLS"}
        try:
            provider_config = json.loads(args.llm_config.read_text(encoding="utf-8"))
            if not isinstance(provider_config, dict) or set(provider_config) - allowed:
                raise ValueError("Unsupported configuration fields")
            if any(not isinstance(value, str) for value in provider_config.values()):
                raise ValueError("Configuration values must be strings")
            for name, value in provider_config.items():
                os.environ.setdefault(name, value)
        except (OSError, ValueError):
            parser.error("Invalid server-side provider configuration; contents withheld")
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=args.port,
                workers=1, access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
