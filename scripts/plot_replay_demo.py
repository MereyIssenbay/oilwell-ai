"""Plot the observed replay report and immutable sensor data; no inference."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.app.registry import Registry


def main() -> int:
    report = json.loads((ROOT / "reports/replay/demo.json").read_text(encoding="utf-8"))
    registry = Registry(ROOT)
    registry.startup()
    record = registry.record(report["source_instance_id"])
    assert record.source.sha256 == report["source_sha256"]
    request = report["request"]
    data = record.frame.iloc[request["start_position"]:request["end_position"] + 1]
    predictions = report["retrospective_predictions"]
    times = pd.to_datetime([p["timestamp"] for p in predictions])
    sensor = "P-PDG"
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True, layout="constrained")
    axes[0].plot(data.index, data[sensor], color="#007d88", linewidth=1.4)
    axes[0].set_ylabel(f"{sensor}\n{registry.units[sensor]}")
    axes[0].set_title("Historical replay | real source WELL-00011 | diagnostic model rejected for monitoring", fontsize=12)
    scores = [p["score"] for p in predictions]
    axes[1].plot(times, scores, marker="o", markersize=3, color="#7050a0", label="Saved-model score")
    axes[1].axhline(report["threshold"], color="#b33a3a", linestyle="--", label="Frozen threshold")
    axes[1].set_yscale("symlog", linthresh=1e-16)
    axes[1].set_ylim(0, 1.5)
    axes[1].set_yticks([0, 1e-14, 1e-10, 1e-6, 1e-2, 1], ["0", "1e-14", "1e-10", "1e-6", "1e-2", "1"])
    axes[1].set_ylabel("Abnormal score\nsymlog scale")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[2].step(times, [int(p["alert_status"] == "alert") for p in predictions], where="post",
                 color="#b33a3a", linewidth=1.8, label="Predicted positive (10 s grid)")
    for run in report["ground_truth_label_runs"]:
        if run["raw_class"] == 102:
            start = pd.Timestamp(run["start_timestamp"])
            for ax in axes:
                ax.axvspan(start, pd.Timestamp(run["end_timestamp"]), color="#e6ad36", alpha=.17)
                ax.axvline(start, color="#ad7600", linestyle=":", linewidth=1)
            axes[2].plot([], [], linewidth=7, alpha=.4, color="#e6ad36", label="Retrospective transient 102")
    for event in report["alert_episode_events"]:
        if event["payload"]["transition"] == "opened":
            timestamp = pd.Timestamp(event["payload"]["timestamp"]).tz_localize(None)
            axes[2].scatter(timestamp, 1, color="#b33a3a", marker="^", s=65, zorder=4)
    axes[2].set_yticks([0, 1], ["normal", "alert"])
    axes[2].set_ylim(-.15, 1.25)
    axes[2].set_ylabel("Diagnostic decision")
    axes[2].legend(loc="lower left", fontsize=8)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    axes[2].set_xlabel("Original source time, 2014-05-30 (timezone unverified); shaded labels joined only after completion")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(ROOT / "reports/replay/demo.png", dpi=150)
    plt.close(fig)
    print("Wrote reports/replay/demo.png from actual saved replay and raw sensors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
