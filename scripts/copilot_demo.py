"""Explain a saved replay prediction, without generating predictions or controlling replay."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEMO = "5a725349-e2c3-42e9-9dd3-4204ddd3ee7c"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-id", default=DEMO)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--use-provider", action="store_true", help="One explicitly requested, budgeted provider attempt")
    parser.add_argument("--question", default="explain this alert",
                        choices=["explain this alert", "show sensor trends", "what data is missing"])
    args = parser.parse_args()
    from llm.schemas import Explanation

    with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=15, trust_env=False) as client:
        rows = client.get(f"/replays/{args.replay_id}/predictions", params={"limit": 100})
        rows.raise_for_status()
        event = rows.json()["items"][-1]
        original = event["payload"]["prediction"]
        path = f"/replays/{args.replay_id}/predictions/{event['sequence']}/explanation"
        start = time.perf_counter()
        response = client.post(path, json={"question": args.question, "use_provider": args.use_provider})
        elapsed = time.perf_counter() - start
        response.raise_for_status()
        result = Explanation.model_validate(response.json())
        assert result.evidence.abnormal_score == original["abnormal_score"]
        assert result.evidence.model_version == original["model_version"]
        assert result.evidence.event_type == original["event_type"]
        for citation in result.citations:
            content = client.get(f"/copilot/sources/{citation.source_id}")
            content.raise_for_status()
            assert content.json() == citation.model_dump(mode="json")
            assert hashlib.sha256(citation.content.encode()).hexdigest() == citation.content_sha256
        repeated = client.post(path, json={"question": args.question, "use_provider": args.use_provider})
        repeated.raise_for_status()
        cached = Explanation.model_validate(repeated.json())
        assert cached.cached and cached.evidence_hash == result.evidence_hash
        assert cached.observations == result.observations
        rejected = client.post(path, json={"question": "Diagnose the physical cause and close the valve"})
        assert rejected.status_code == 200 and rejected.json()["status"] == "abstained"
        evidence = {"replay_id": args.replay_id, "sequence": event["sequence"],
            "prediction_id": original["prediction_id"], "endpoint": event["payload"]["source_position"],
            "http_status": response.status_code, "elapsed_seconds": elapsed,
            "prediction_fields_match": True, "citation_content_hashes_match": True,
            "repeat_cached": cached.cached, "unsupported_control_question": rejected.json()["reason"],
            "explanation": result.model_dump(mode="json"), "new_inference_executed": False}
        output = ROOT / "reports/copilot" / ("provider_smoke.json" if args.use_provider else "api_smoke.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"report": output.relative_to(ROOT).as_posix(), "status": result.status,
            "reason": result.reason, "cached_repeat": cached.cached,
            "usage": result.usage.model_dump() if result.usage else None,
            "elapsed_seconds": round(elapsed, 3)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
