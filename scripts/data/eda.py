"""Reproducible descriptive EDA on immutable acquired 3W files; no models.

All statistics use complete selected files. Downsampling is used for display only.
The audit subset is size-biased and every inspected instance is development-exposed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd

ORIGINS = ("real", "simulated", "drawn")
CORE = ("P-PDG", "P-TPT", "P-MON-CKP", "T-TPT", "T-JUS-CKP")
ORIGIN_COLORS = {"real": "#23678b", "simulated": "#d27934", "drawn": "#7b589b"}


def label_runs(labels: pd.Series, index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    """Contiguous label runs within ONE instance; unknown/gaps break known runs."""
    if len(labels) != len(index):
        raise ValueError("Label/index length mismatch")
    if not isinstance(index, pd.DatetimeIndex) or index.hasnans or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("EDA requires a unique increasing non-null datetime index")
    if not len(labels):
        return []
    raw = ["unknown" if pd.isna(value) else str(int(value)) for value in labels]
    cuts = [0]
    for position in range(1, len(raw)):
        if raw[position] != raw[position - 1] or (index[position] - index[position - 1]).total_seconds() != 1:
            cuts.append(position)
    cuts.append(len(raw))
    runs = []
    for start, stop in zip(cuts, cuts[1:]):
        left_gap = start > 0 and (index[start] - index[start - 1]).total_seconds() != 1
        right_gap = stop < len(raw) and (index[stop] - index[stop - 1]).total_seconds() != 1
        runs.append({"raw_label": raw[start], "start_pos": start, "end_pos": stop - 1,
                     "rows": stop - start, "duration_seconds": float((index[stop - 1] - index[start]).total_seconds() + 1),
                     "start": index[start].isoformat(), "end": index[stop - 1].isoformat(),
                     "left_censored": start == 0 or left_gap or raw[start - 1] == "unknown",
                     "right_censored": stop == len(raw) or right_gap or raw[stop] == "unknown"})
    return runs


def transitions_between_runs(runs: list[dict[str, Any]], index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    result = []
    for left, right in zip(runs, runs[1:]):
        position = right["start_pos"]
        if left["end_pos"] + 1 != position or (index[position] - index[position - 1]).total_seconds() != 1:
            continue
        if left["raw_label"] == right["raw_label"]:
            continue
        result.append({"from_raw": left["raw_label"], "to_raw": right["raw_label"],
                       "boundary_position": position,
                       "known_labels": "unknown" not in (left["raw_label"], right["raw_label"])})
    return result


def correlation_rows(frame: pd.DataFrame, sensor_names: list[str], min_pairs: int = 120) -> list[dict[str, Any]]:
    """Pairwise-complete within-instance Pearson; no pooling or label inputs."""
    if {"class", "state", "timestamp"} & set(sensor_names):
        raise ValueError("Labels/time are not sensor inputs")
    if min_pairs < 2 or len(set(sensor_names)) != len(sensor_names):
        raise ValueError("Invalid correlation settings")
    sensors = frame.loc[:, sensor_names]
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in sensors.dtypes):
        raise ValueError("Sensor columns must be numeric")
    counts = sensors.notna().astype("int64").T.dot(sensors.notna().astype("int64"))
    correlations = sensors.corr(method="pearson", min_periods=min_pairs)
    result = []
    for i, a in enumerate(sensor_names):
        for b in sensor_names[i + 1:]:
            value = correlations.loc[a, b]
            result.append({"sensor_a": a, "sensor_b": b, "pair_count": int(counts.loc[a, b]),
                           "pearson": float(value) if pd.notna(value) and np.isfinite(value) else None})
    return result


def _read_inputs(root: Path) -> tuple[dict, dict, list[tuple[dict, pd.DataFrame]]]:
    manifest = json.loads((root / "data/manifests/subset.json").read_text(encoding="utf-8"))
    registry = json.loads((root / "data/manifests/dataset_metadata.json").read_text(encoding="utf-8"))
    frames = []
    for entry in manifest["files"]:
        path = (root / entry["local_path"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()) or not path.is_relative_to(root.resolve()):
            raise ValueError("Raw input escapes workspace")
        payload = path.read_bytes()
        if len(payload) != entry["size_bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source integrity failure: {entry['source_path']}")
        frames.append((entry, pd.read_parquet(path, engine="pyarrow")))
    return manifest, registry, frames


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def build_eda(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    out = (root / "reports/eda").resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError("Unsafe EDA output directory")
    out.mkdir(parents=True, exist_ok=True)
    manifest, registry, frames = _read_inputs(root)
    sensor_names = [item["name"] for item in registry["sensor_columns"]]
    if len(sensor_names) != 27 or {"class", "state", "timestamp"} & set(sensor_names):
        raise ValueError("Expected explicit 27-sensor registry")
    label_specs: dict[str, dict] = {"unknown": {"family": "unknown", "phase": "unknown", "name": "Unknown"}}
    for event in registry["events"]:
        label_specs[str(event["label"])] = {"family": str(event["label"]), "phase": "normal" if event["label"] == 0 else "event", "name": event["name"]}
        if event["transient_label"] is not None:
            label_specs[str(event["transient_label"])] = {"family": str(event["label"]), "phase": "transient", "name": event["name"]}
    balances: dict[tuple, dict] = {}
    missing: dict[tuple, dict] = {}
    availability, all_runs, all_transitions, correlations, comparisons = [], [], [], [], []
    for entry, frame in frames:
        origin, instance, well = entry["source_kind"], entry["source_instance_id"], entry["well_identifier"]
        raw_labels = frame["class"].map(lambda x: "unknown" if pd.isna(x) else str(int(x)))
        if set(raw_labels) - set(label_specs):
            raise ValueError("Undocumented raw class encountered")
        for raw, group in frame.groupby(raw_labels, sort=False):
            family = label_specs[raw]["family"]
            for level, code in (("raw", raw), ("family", family)):
                key = (origin, level, code)
                rec = balances.setdefault(key, {"rows": 0, "instances": set(), "wells": set()})
                rec["rows"] += len(group)
                rec["instances"].add(instance)
                if well:
                    rec["wells"].add(well)
            for sensor in sensor_names:
                key = (origin, raw, sensor)
                rec = missing.setdefault(key, {"rows": 0, "missing": 0, "instances": set(), "wells": set(), "available_instances": set(), "available_wells": set()})
                rec["rows"] += len(group)
                rec["missing"] += int(group[sensor].isna().sum())
                rec["instances"].add(instance)
                if well:
                    rec["wells"].add(well)
                if group[sensor].notna().any():
                    rec["available_instances"].add(instance)
                    if well:
                        rec["available_wells"].add(well)
        for sensor in sensor_names:
            values = frame[sensor]
            availability.append({"source_path": entry["source_path"], "source_kind": origin, "well_identifier": well,
                                 "sensor": sensor, "rows": len(frame), "available_rows": int(values.notna().sum()),
                                 "availability_fraction": float(values.notna().mean()), "distinct_values": int(values.nunique()),
                                 "constant_when_observed": bool(values.notna().any() and values.nunique() == 1)})
        runs = label_runs(frame["class"], frame.index)
        for run in runs:
            all_runs.append({"source_path": entry["source_path"], "source_kind": origin, "well_identifier": well,
                             **run, **label_specs[run["raw_label"]]})
        for transition in transitions_between_runs(runs, frame.index):
            all_transitions.append({"source_path": entry["source_path"], "source_kind": origin, **transition})
        for row in correlation_rows(frame, sensor_names):
            correlations.append({"source_path": entry["source_path"], "source_kind": origin, **row})
        for condition, mask in (("normal", frame["class"].eq(0).fillna(False)),
                                ("abnormal", frame["class"].notna() & frame["class"].ne(0).fillna(False))):
            for sensor in CORE:
                values = frame.loc[mask, sensor].dropna()
                if len(values):
                    comparisons.append({"source_path": entry["source_path"], "source_kind": origin,
                                        "well_identifier": well, "condition": condition, "sensor": sensor,
                                        "labelled_rows": int(mask.sum()), "observed_rows": len(values),
                                        "median": float(values.median()), "q25": float(values.quantile(.25)),
                                        "q75": float(values.quantile(.75))})
    balance_rows = []
    for (origin, level, code), rec in sorted(balances.items()):
        balance_rows.append({"source_kind": origin, "level": level, "code": code, "rows": rec["rows"],
                             "instance_count": len(rec["instances"]), "real_well_count": len(rec["wells"]),
                             "real_well_ids": sorted(rec["wells"])})
    missing_rows = []
    for (origin, raw, sensor), rec in sorted(missing.items()):
        missing_rows.append({"source_kind": origin, "raw_class": raw, "family": label_specs[raw]["family"],
                             "sensor": sensor, "rows": rec["rows"], "missing_rows": rec["missing"],
                             "missing_fraction": rec["missing"] / rec["rows"], "instance_count": len(rec["instances"]),
                             "real_well_count": len(rec["wells"]), "available_instance_count": len(rec["available_instances"]),
                             "available_real_well_count": len(rec["available_wells"])})
    corr_frame = pd.DataFrame(correlations)
    corr_summary = []
    for (origin, a, b), group in corr_frame.groupby(["source_kind", "sensor_a", "sensor_b"], sort=True):
        valid = group[group["pearson"].notna()]
        corr_summary.append({"source_kind": origin, "sensor_a": a, "sensor_b": b,
                             "instance_count": len(group), "valid_instance_count": len(valid),
                             "pair_count_total": int(group["pair_count"].sum()),
                             "median_within_instance_pearson": float(valid["pearson"].median()) if len(valid) else None,
                             "minimum_within_instance_pearson": float(valid["pearson"].min()) if len(valid) else None,
                             "maximum_within_instance_pearson": float(valid["pearson"].max()) if len(valid) else None})
    tables = {"class_balance": balance_rows, "missing_by_source_class": missing_rows,
              "sensor_availability": availability, "label_runs": all_runs, "transitions": all_transitions,
              "correlations_within_instance": correlations, "correlation_summary": corr_summary,
              "normal_abnormal_summary": comparisons}
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(out / f"{name}.csv", index=False)
    totals = {origin: {"files": sum(e["source_kind"] == origin for e, _ in frames),
                       "rows": sum(len(f) for e, f in frames if e["source_kind"] == origin)} for origin in ORIGINS}
    known_transitions = [t for t in all_transitions if t["known_labels"]]
    transition_counts = Counter((t["source_kind"], t["from_raw"], t["to_raw"]) for t in all_transitions)
    source_phase_rows = {origin: dict(Counter()) for origin in ORIGINS}
    for row in balance_rows:
        if row["level"] == "raw":
            phase = label_specs[row["code"]]["phase"]
            source_phase_rows[row["source_kind"]][phase] = source_phase_rows[row["source_kind"]].get(phase, 0) + row["rows"]
    summary = {
        "schema_version": "1.0.0", "dataset": manifest["dataset"],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_totals": totals, "total_files": len(frames), "total_rows": sum(len(f) for _, f in frames),
        "sensor_columns": sensor_names, "excluded_inputs": ["class", "state", "timestamp", "source_kind", "source_path", "well_identifier", "source_instance_id"],
        "class_balance": balance_rows, "phase_rows_by_source": source_phase_rows,
        "transition_counts": [{"source_kind": key[0], "from_raw": key[1], "to_raw": key[2], "count": count} for key, count in sorted(transition_counts.items())],
        "runs": {"total": len(all_runs), "known_label_transition_count": len(known_transitions),
                 "unknown_boundary_transition_count": len(all_transitions) - len(known_transitions),
                 "transient_runs": sum(run["phase"] == "transient" for run in all_runs),
                 "censored_transient_runs": sum(run["phase"] == "transient" and (run["left_censored"] or run["right_censored"]) for run in all_runs)},
        "correlation_method": "Pairwise-complete Pearson per instance; minimum120 paired rows; constants/undefined omitted; source summaries are equal-instance medians, not pooled correlations or causality.",
        "correlation_summary": corr_summary,
        "plot_policy": {"maximum_points_per_contiguous_segment": 1500, "method": "deterministic evenly-spaced row positions within finite contiguous segments; label boundaries from full resolution; no statistics use plot decimation", "source_timestamps": "naive source coordinates; x-axis elapsed time not physical UTC"},
        "provenance": {"input_manifest_sha256": hashlib.sha256((root / "data/manifests/subset.json").read_bytes()).hexdigest(),
                       "registry_sha256": hashlib.sha256((root / "data/manifests/dataset_metadata.json").read_bytes()).hexdigest(),
                       "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "requirements_sha256": hashlib.sha256((root / "requirements-eda.txt").read_bytes()).hexdigest(),
                       "dependencies": {name: importlib.metadata.version(name) for name in ("pandas", "numpy", "pyarrow", "matplotlib")},
                       "input_files": [{"source_path": e["source_path"], "sha256": e["sha256"]} for e, _ in frames]},
        "eda_exposure": {"status": "development_exposed_not_clean_final_test",
                         "instances": [{"source_instance_id": e["source_instance_id"], "source_path": e["source_path"]} for e, _ in frames],
                         "real_well_ids": sorted({e["well_identifier"] for e, _ in frames if e["source_kind"] == "real"})},
        "limitations": ["Size-biased23-file subset; distributions are not corpus prevalence.",
                        "Every inspected source is development-exposed; no pristine test data is designated.",
                        "Anonymized well IDs are grouping proxies, not independently verified physical assets.",
                        "Autocorrelated rows are not independent samples; no causal inference or significance claims.",
                        "Known labels, unknown labels, source domains and censored runs remain distinct.",
                        "Descriptive summaries and plot unit scaling are not production preprocessing or feature pipelines."]}
    _plots(out, frames, tables, summary)
    for entry, _ in frames:
        if hashlib.sha256((root / entry["local_path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Raw file changed during EDA")
    summary["raw_hashes_verified_before_and_after"] = True
    summary["charts"] = sorted(path.name for path in out.glob("*.png"))
    _json_write(out / "eda_summary.json", summary)
    return summary


def _plots(out: Path, frames: list, tables: dict, summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "white", "savefig.facecolor": "white"})
    def save(fig, name, subtitle):
        bottom = .65 / fig.get_figheight()
        fig.set_layout_engine("constrained", rect=(0, bottom, 1, 1-bottom))
        fig.text(.01, .01, subtitle + " | 3W v2.0.0 audit subset; descriptive only", fontsize=8, color="#555555")
        fig.savefig(out / (name + ".png"), dpi=150, bbox_inches="tight")
        plt.close(fig)
    balance = pd.DataFrame(tables["class_balance"])
    family_order = [str(i) for i in range(10)] + ["unknown"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
    for ax, metric, title in zip(axes, ["rows", "real_well_count"], ["Rows by event family and source", "Real well-ID support by family"]):
        family = balance[balance.level.eq("family")]
        if metric == "rows":
            bottom = np.zeros(len(family_order))
            for origin in ORIGINS:
                values = family[family.source_kind.eq(origin)].set_index("code")[metric].reindex(family_order, fill_value=0)
                ax.bar(family_order, values, bottom=bottom, label=origin, color=ORIGIN_COLORS[origin])
                bottom += values.to_numpy()
            ax.legend(frameon=False)
            ax.set_ylabel("Observed rows (not independent samples)")
        else:
            values = family[family.source_kind.eq("real")].set_index("code")[metric].reindex(family_order, fill_value=0)
            ax.bar(family_order, values, color=ORIGIN_COLORS["real"])
            ax.set_ylabel("Distinct published real well IDs")
            ax.set_ylim(0, max(values) + 1)
        ax.set_title(title, loc="left", weight="bold")
        ax.set_xlabel("Family (documented transient codes mapped only for this summary)")
        ax.tick_params(axis="x", rotation=35)
    save(fig, "01_class_balance", "Unknown labels remain separate; missing classes are zero, not inferred from directories")
    missing = pd.DataFrame(tables["missing_by_source_class"])
    availability = pd.DataFrame(tables["sensor_availability"])
    sensors = summary["sensor_columns"]
    grouped = availability.groupby(["sensor", "source_kind"])[["rows", "available_rows"]].sum()
    matrix = (1 - grouped.available_rows / grouped.rows).unstack("source_kind").reindex(index=sensors, columns=ORIGINS)
    fig, ax = plt.subplots(figsize=(10, 10), layout="constrained")
    im = ax.imshow(matrix, vmin=0, vmax=1, cmap="YlOrRd", aspect="auto")
    ax.set_yticks(range(len(sensors)), sensors); ax.set_xticks(range(3), ORIGINS)
    for i in range(len(sensors)):
        for j in range(3): ax.text(j, i, f"{100*matrix.iloc[i,j]:.1f}%", ha="center", va="center", fontsize=8, color="white" if matrix.iloc[i,j] > .65 else "black")
    ax.set_title("Missing sensor cells differ strongly by source", loc="left", weight="bold")
    fig.colorbar(im, ax=ax, label="Missing fraction of selected source rows", shrink=.6)
    save(fig, "02_missing_by_source", "Denominators: real322725; simulated201894; drawn57601 rows")
    real = missing[missing.source_kind.eq("real")].groupby(["sensor", "family"])[["rows", "missing_rows"]].sum()
    mat = (real.missing_rows / real.rows).unstack("family").reindex(index=sensors, columns=family_order)
    fig, ax = plt.subplots(figsize=(13, 10), layout="constrained")
    cmap = plt.get_cmap("YlOrRd").copy(); cmap.set_bad("#d8d8d8")
    im = ax.imshow(mat, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    ax.set_yticks(range(len(sensors)), sensors); ax.set_xticks(range(len(family_order)), family_order, rotation=35)
    ax.set_title("Real-source missingness by observed event family", loc="left", weight="bold")
    ax.set_xlabel("Observed row family; gray = no selected real rows, not complete availability")
    fig.colorbar(im, ax=ax, label="Missing fraction within family", shrink=.6)
    save(fig, "03_missing_by_real_family", "Family9 has no real row support; support/denominators in missing_by_source_class.csv")
    correlations = pd.DataFrame(tables["correlation_summary"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    cmap = plt.get_cmap("RdBu_r").copy(); cmap.set_bad("#e1e1e1")
    for ax, origin in zip(axes, ORIGINS):
        matrix = np.full((len(CORE), len(CORE)), np.nan); counts = np.zeros(matrix.shape, dtype=int)
        for row in correlations[correlations.source_kind.eq(origin)].to_dict("records"):
            if row["sensor_a"] in CORE and row["sensor_b"] in CORE:
                i, j = CORE.index(row["sensor_a"]), CORE.index(row["sensor_b"])
                matrix[i,j] = matrix[j,i] = row["median_within_instance_pearson"]
                counts[i,j] = counts[j,i] = row["valid_instance_count"]
        im = ax.imshow(matrix, vmin=-1, vmax=1, cmap=cmap)
        for i in range(len(CORE)):
            for j in range(len(CORE)):
                if np.isfinite(matrix[i,j]): ax.text(j, i, f"{matrix[i,j]:.2f}\nn={counts[i,j]}", ha="center", va="center", fontsize=8)
        ax.set_xticks(range(len(CORE)), CORE, rotation=55, ha="right"); ax.set_yticks(range(len(CORE)), CORE)
        ax.set_title(origin, weight="bold")
    fig.suptitle("Equal-instance median of within-instance sensor correlations", weight="bold")
    fig.colorbar(im, ax=axes, shrink=.7, label="Pearson r (descriptive, not causality)")
    save(fig, "04_sensor_correlations", "n=valid instances; >=120paired rows per instance; undefined/constant pairs and diagonal masked")
    # Plot each contiguous finite segment independently, preserving missing gaps.
    def trace(ax, frame, sensor, scale=1):
        values = frame[sensor].to_numpy(dtype=float)
        x = (frame.index - frame.index[0]).total_seconds().to_numpy() / 3600
        finite = np.isfinite(values)
        gaps = (frame.index[1:] - frame.index[:-1]).total_seconds().to_numpy() != 1
        breaks = np.r_[0, np.flatnonzero((finite[1:] != finite[:-1]) | gaps) + 1, len(values)]
        for start, stop in zip(breaks, breaks[1:]):
            if finite[start]:
                take = np.unique(np.linspace(start, stop - 1, num=min(1500, stop - start), dtype=int))
                ax.plot(x[take], values[take] / scale, lw=.9, color="#23678b")
        ax.set_xlim(0, x[-1]); ax.set_ylabel(sensor + (" (MPa)" if scale == 1e6 else " (deg C)"))
    def shade(ax, frame):
        for run in label_runs(frame["class"], frame.index):
            start=(frame.index[run["start_pos"]] - frame.index[0]).total_seconds()/3600
            stop=((frame.index[run["end_pos"]] - frame.index[0]).total_seconds()+1)/3600
            raw=run["raw_label"]
            color="#cfcfcf" if raw=="unknown" else "#c8e5d0" if raw=="0" else "#ffd280" if int(raw)>=100 else "#f2a0a0"
            ax.axvspan(start,stop,color=color,alpha=.45,lw=0,zorder=-1)
    chosen = [next((e,f) for e,f in frames if e["source_path"]==path) for path in
              ("dataset/0/WELL-00002_20131214190030.parquet", "dataset/1/WELL-00002_20140126180030.parquet")]
    fig, axes = plt.subplots(3,2,figsize=(14,9),sharex="col",sharey="row",layout="constrained")
    for col,(entry, frame) in enumerate(chosen):
        for row,sensor in enumerate(("P-PDG","P-TPT","T-TPT")):
            trace(axes[row,col],frame,sensor,1e6 if sensor.startswith("P-") else 1); shade(axes[row,col],frame)
        axes[0,col].set_title(("Normal instance" if col==0 else "Event1 instance")+" | WELL-00002\n"+Path(entry["source_path"]).name,loc="left",weight="bold",fontsize=10)
        axes[-1,col].set_xlabel("Hours since this instance began")
    fig.suptitle("Same published well ID, different dates: actual sensor traces",weight="bold")
    save(fig,"05_real_normal_vs_event","Shared y-ranges by sensor; gray=unknown, green=normal, amber=transient, red=event. Display-only Pa to MPa scaling")
    chosen = [next((e,f) for e,f in frames if e["source_kind"]==origin and e["event_code"]==1) for origin in ORIGINS]
    fig,axes=plt.subplots(2,3,figsize=(15,7),sharex="col",layout="constrained")
    for col,(entry,frame) in enumerate(chosen):
        for row,sensor in enumerate(("P-TPT","T-TPT")):
            trace(axes[row,col],frame,sensor,1e6 if row==0 else 1); shade(axes[row,col],frame)
        axes[0,col].set_title(entry["source_kind"]+"\n"+Path(entry["source_path"]).name,weight="bold",fontsize=9); axes[-1,col].set_xlabel("Hours since instance began")
    fig.suptitle("Event1 examples across origins: distinct signals and annotation schedules",weight="bold")
    save(fig,"06_source_timeseries","Independent y-ranges; documented Pa scaled to MPa without unit corrections. One example/source, not matched experiments")
    known_order=[str(i) for i in (0,1,2,3,4,5,6,7,8,9,101,102,105,106,107,108,109)]+["unknown"]
    fig,axes=plt.subplots(1,2,figsize=(15,6),layout="constrained")
    transition_matrix=np.zeros((len(known_order),len(known_order)),dtype=int)
    for row in summary["transition_counts"]:
        transition_matrix[known_order.index(row["from_raw"]),known_order.index(row["to_raw"])]+=row["count"]
    im=axes[0].imshow(transition_matrix,cmap="Blues",aspect="auto")
    axes[0].set_xticks(range(len(known_order)),known_order,rotation=65); axes[0].set_yticks(range(len(known_order)),known_order)
    axes[0].set_xlabel("To raw label"); axes[0].set_ylabel("From raw label"); axes[0].set_title("Observed label-change boundaries",loc="left",weight="bold")
    for i,j in zip(*np.where(transition_matrix>0)): axes[0].text(j,i,str(transition_matrix[i,j]),ha="center",va="center",fontsize=8)
    transient=[r for r in tables["label_runs"] if r["phase"]=="transient"]
    for i,origin in enumerate(ORIGINS):
        runs=[r for r in transient if r["source_kind"]==origin]
        axes[1].scatter([i]*len(runs),[r["duration_seconds"]/60 for r in runs],s=45,c=ORIGIN_COLORS[origin],alpha=.7)
        for r in runs:
            if r["left_censored"] or r["right_censored"]: axes[1].scatter([i],[r["duration_seconds"]/60],s=80,facecolors="none",edgecolors="black")
    axes[1].set_xticks(range(3),ORIGINS); axes[1].set_ylabel("Observed contiguous transient run (minutes)")
    axes[1].set_title("Transient runs, not complete event durations",loc="left",weight="bold")
    save(fig,"07_label_transitions","No cross-instance/gap links; unknown boundaries retained; outlined runs touch unknown/file/gap boundaries")
    comparisons=pd.DataFrame(tables["normal_abnormal_summary"])
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout="constrained")
    for ax,sensor in zip(axes,("P-PDG","P-TPT","T-TPT")):
        rows=comparisons[(comparisons.source_kind=="real") & (comparisons.sensor==sensor)]
        scale=1e6 if sensor.startswith("P-") else 1
        for source,group in rows.groupby("source_path"):
            ordered=group.set_index("condition").reindex(["normal","abnormal"])
            vals=ordered["median"].to_numpy()/scale
            ax.plot([0,1],vals,marker="o",alpha=.7,lw=1)
        ax.set_xticks([0,1],["Normal rows","Abnormal rows"])
        ax.set_title(sensor,weight="bold"); ax.set_ylabel("Per-instance median ("+("MPa" if scale==1e6 else "deg C")+")")
    fig.suptitle("Real-source sensor levels vary across instances and label conditions",weight="bold")
    save(fig,"08_normal_abnormal","Each line is one instance with both conditions; isolated dots have one condition; no pooled causal comparison")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args()
    summary=build_eda(args.root)
    print(json.dumps({"files":summary["total_files"],"rows":summary["total_rows"],"charts":len(summary["charts"]),"raw_unchanged":summary["raw_hashes_verified_before_and_after"]}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
