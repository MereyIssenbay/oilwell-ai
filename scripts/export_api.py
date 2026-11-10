"""Export reviewed runtime contracts without startup, inference or network access."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from backend.app.main import create_app
    from llm.schemas import Explanation, EvidencePacket

    (ROOT / "docs/openapi.json").write_text(
        json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, model in (("explanation", Explanation), ("copilot_evidence", EvidencePacket)):
        payload = {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}
        (ROOT / f"docs/contracts/{name}.schema.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Exported OpenAPI and two additive copilot schemas; no model execution")


if __name__ == "__main__":
    main()
