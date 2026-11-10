"""Replay one frozen validation interval over HTTP, then join labels offline.

No labels are read until the API reports completion. No training, tuning or test
inference takes place. API failures are reported without printing server bodies.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_ID = "3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf"
START = 5600
END = 5859


def checked(response: httpx.Response) -> dict:
    if response.status_code not in {200, 201, 202}:
        raise RuntimeError(f"Replay API returned HTTP {response.status_code}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/replay/demo.json")
    args = parser.parse_args()
    url = urlparse(args.base_url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"} or url.username or url.password:
        parser.error("Use an HTTP loopback API URL without credentials")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "reports/replay").resolve()) or output.suffix != ".json":
        parser.error("Output must be a JSON file under reports/replay")
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        info = checked(client.get("/models/info"))
        request = {"source_instance_id": SOURCE_ID, "start_position": START,
                   "end_position": END, "speed_multiplier": 20.0,
                   "model_version": info["model_version"]}
        key = f"demo-create-{uuid4()}"
        created = checked(client.post("/replays", json=request, headers={"Idempotency-Key": key}))
        again = checked(client.post("/replays", json=request, headers={"Idempotency-Key": key}))
        assert again == created, "Creation retry changed the stored response"
        replay_id = created["replay_id"]

        def snapshot() -> dict:
            return checked(client.get(f"/replays/{replay_id}"))

        def command(name: str, **extra) -> dict:
            current = snapshot()
            return checked(client.post(f"/replays/{replay_id}/commands",
                json={"command": name, "expected_version": current["version"], **extra},
                headers={"Idempotency-Key": f"demo-command-{uuid4()}"}))

        command("start")
        deadline = time.monotonic() + 120
        while snapshot().get("cursor_position") in {None, START - 1}:
            if time.monotonic() > deadline:
                raise RuntimeError("Replay did not begin within the bounded demo timeout")
            time.sleep(0.05)
        command("pause")
        paused = snapshot()
        time.sleep(0.2)
        assert snapshot()["cursor_position"] == paused["cursor_position"], "Pause advanced the cursor"
        command("set_speed", speed_multiplier=10.0)
        command("set_speed", speed_multiplier=20.0)
        command("resume")
        while True:
            final = snapshot()
            if final["state"] == "completed":
                break
            if final["state"] in {"failed", "stopped"}:
                raise RuntimeError(f"Replay ended unexpectedly: {final['state']}")
            if time.monotonic() > deadline:
                raise RuntimeError("Replay did not complete within the bounded demo timeout")
            time.sleep(0.1)

        events = []
        after = 0
        while True:
            page = checked(client.get(f"/replays/{replay_id}/event-history",
                                      params={"after_sequence": after, "limit": 1000}))
            batch = page["items"]
            events.extend(batch)
            if not batch or batch[-1]["sequence"] >= final["last_sequence"]:
                break
            after = batch[-1]["sequence"]
        assert [e["sequence"] for e in events] == list(range(1, final["last_sequence"] + 1))
        # Reconnect to the same committed history: no live buffers or labels.
        watermark = events[len(events) // 2]["sequence"]
        streamed = []
        with client.stream("GET", f"/replays/{replay_id}/events",
                headers={"Last-Event-ID": f"{replay_id}:{watermark}"}) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data:"):
                    streamed.append(json.loads(line[5:].strip()))
        assert streamed == [e for e in events if e["sequence"] > watermark]

    # Retrospective boundary: original class/state are never sent to the API.
    from backend.app.registry import Registry, trusted_selection
    registry = Registry(ROOT)
    registry.startup()
    record = registry.record(SOURCE_ID)
    source = record.source
    raw_root = ROOT / "data/raw/3w"
    raw_path = (raw_root / source.dataset_version / source.dataset_revision / source.source_path).resolve()
    assert raw_path.is_relative_to(raw_root.resolve())
    raw_bytes = raw_path.read_bytes()
    assert hashlib.sha256(raw_bytes).hexdigest() == source.sha256
    labels = pd.read_parquet(BytesIO(raw_bytes), columns=["class", "state"])
    selected = trusted_selection(ROOT)
    saved_path = ROOT / selected["validation_predictions_path"]
    assert hashlib.sha256(saved_path.read_bytes()).hexdigest() == selected["validation_predictions_sha256"]
    saved = pd.read_parquet(saved_path, filters=[("model", "==", selected["candidate_id"])])
    saved = saved[saved.instance_id == SOURCE_ID].set_index("endpoint_position")
    predictions = []
    for event in events:
        if event["event_type"] != "prediction":
            continue
        envelope = event["payload"]
        value = envelope["prediction"]
        position = envelope["source_position"]
        expected = saved.loc[position]
        score = value["abnormal_score"]
        assert abs(score - float(expected.score)) <= 1e-14
        assert (value["alert_status"] == "alert") == bool(expected.predicted)
        assert position - 59 >= START and position <= END and (position - 59) % 10 == 0
        raw_class, raw_state = labels.iloc[position][["class", "state"]]
        predictions.append({"source_position": position, "timestamp": value["provenance"]["source_timestamp"],
            "prediction_id": value["prediction_id"], "score": score, "alert_status": value["alert_status"],
            "offline_score": float(expected.score), "raw_class": None if pd.isna(raw_class) else int(raw_class),
            "raw_state": None if pd.isna(raw_state) else int(raw_state)})
    label_runs = []
    for position in range(START, END + 1):
        label = labels.iloc[position]["class"]
        code = None if pd.isna(label) else int(label)
        if not label_runs or label_runs[-1]["raw_class"] != code:
            label_runs.append({"start_position": position, "end_position": position,
                "start_timestamp": labels.index[position].isoformat(),
                "end_timestamp": labels.index[position].isoformat(), "raw_class": code})
        else:
            label_runs[-1].update(end_position=position, end_timestamp=labels.index[position].isoformat())
    report = {"schema_version": "replay-demo-1.0.0", "mode": "historical_replay",
        "simulated_playback": True, "diagnostic_only": True, "accepted_for_monitoring": False,
        "replay_id": replay_id, "source_instance_id": SOURCE_ID, "source_kind": "real",
        "source_sha256": source.sha256, "dataset_revision": source.dataset_revision,
        "source_time_basis": "source_naive_assumed_utc", "model_version": info["model_version"],
        "threshold": info["threshold"], "request": request, "final_snapshot": final,
        "checks": {"create_retry_exact": True, "pause_no_advance": True,
            "speed_changed_and_resumed": True, "complete_ordered_event_history": True,
            "sse_reconnect_matches_history": True, "offline_validation_scores_match_atol": 1e-14,
            "labels_loaded_only_after_completion": True, "test_data_used": False},
        "event_counts": {kind: sum(e["event_type"] == kind for e in events)
                         for kind in sorted({e["event_type"] for e in events})},
        "ground_truth_label_runs": label_runs,
        "label_meanings": {"0": "normal", "102": "transient spurious closure of DHSV"},
        "retrospective_predictions": predictions,
        "alert_episode_events": [e for e in events if e["event_type"] == "alert_episode"],
        "limitations": ["Validation case chosen retrospectively for demonstration, not a new benchmark",
            "Selected model rejected for monitoring; initial positive is left-censored",
            "Raw class/state remain retrospective targets, never model features or streamed telemetry",
            "No inference of physical causality or verified UTC"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output.relative_to(ROOT)), "state": final["state"],
                      "predictions": len(predictions), "events": len(events)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
