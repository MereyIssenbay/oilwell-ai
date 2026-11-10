"""Reproduce grouped diagnostic preprocessing without training an event detector."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
import uuid

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.data_pipeline import (CausalFeaturePipeline, PipelineConfig, SplitConfig,
                              load_exposure, load_instances, make_split)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_path(root: Path, value: Path, boundary: str) -> Path:
    target = (root / value).resolve() if not value.is_absolute() else value.resolve()
    allowed = (root / boundary).resolve()
    if not allowed.is_relative_to(root) or not target.is_relative_to(allowed) or target == allowed:
        raise ValueError(f"Output must be inside repository {boundary}/")
    return target


def _atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        writer(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_write(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    _atomic_write(path, lambda temporary: temporary.write_text(payload, encoding="utf-8"))


def _git_revision(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    output = _output_path(root, args.output_dir, "data/processed")
    split_path = _output_path(root, args.split_output, "data/manifests")
    summary_path = _output_path(root, args.summary_output, "reports")
    if split_path.suffix != ".json" or summary_path.suffix != ".json":
        raise ValueError("Split and summary outputs must be JSON files")
    inputs = {"manifest": (root / args.manifest).resolve(),
              "registry": (root / args.registry).resolve(),
              "exposure_ledger": (root / args.exposure_ledger).resolve()}
    if split_path in inputs.values() or summary_path in inputs.values():
        raise ValueError("Outputs must not overwrite an input manifest, registry or exposure ledger")
    config = PipelineConfig(window_rows=args.window_rows, stride_rows=args.stride_rows,
                            cadence_seconds=args.cadence_seconds,
                            transient_policy=args.transient_policy)
    split_config = SplitConfig(seed=args.seed, ratios=tuple(args.ratios), mode=args.mode,
                               include_synthetic_train=args.include_synthetic_train,
                               required_families=tuple(args.required_families),
                               minimum_groups_per_family=args.minimum_groups_per_family)
    input_hashes = {name: _sha256(path) for name, path in inputs.items()}
    instances = load_instances(root, inputs["manifest"], inputs["registry"])
    exposure = load_exposure(inputs["exposure_ledger"])
    split = make_split(instances, split_config, exposure)
    pipeline = CausalFeaturePipeline(config)
    batch = pipeline.build(instances, split)
    pipeline.fit(batch.subset("train"), split)
    normalized = pipeline.transform(batch, split)
    assert pipeline.state is not None
    if not np.isfinite(normalized.to_numpy()).all():
        raise ValueError("Nonfinite normalized output")

    # Complete all validation before publishing output artifacts.
    for instance in instances:
        if _sha256(root / "data/raw/3w/2.0.0" / instance.metadata.dataset_revision
                   / instance.metadata.source_path) != instance.metadata.sha256:
            raise ValueError("Original source changed during preprocessing")
    if input_hashes != {name: _sha256(path) for name, path in inputs.items()}:
        raise ValueError("Input manifest/registry/exposure changed during preprocessing")

    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "preprocessor.json"
    _atomic_write(state_path, pipeline.save)
    restored = CausalFeaturePipeline.load(state_path)
    if not restored.transform(batch, split).equals(normalized):
        raise ValueError("Saved-state round trip changed normalized features")
    tables = {"features": normalized, "targets": batch.targets,
              "metadata": batch.metadata, "quality": batch.quality}
    artifacts = {"preprocessor": {"path": str(state_path.relative_to(root)).replace("\\", "/"),
                                  "sha256": _sha256(state_path)}}
    for name, table in tables.items():
        path = output / f"{name}.parquet"
        _atomic_write(path, lambda temporary, frame=table: frame.to_parquet(temporary, engine="pyarrow"))
        if not pd.read_parquet(path, engine="pyarrow").equals(table):
            raise ValueError(f"Parquet round trip changed {name}")
        artifacts[name] = {"path": str(path.relative_to(root)).replace("\\", "/"),
                           "sha256": _sha256(path)}

    partitions = {}
    for name in ("train", "validation", "test"):
        assignments = [a for a in split.assignments if a.partition == name]
        mask = batch.metadata.partition.eq(name)
        subset = batch.targets.loc[mask]
        partitions[name] = {
            "source_instances": len(assignments),
            "connected_groups": len({a.group_id for a in assignments}),
            "real_well_ids": sorted({a.source.well_id for a in assignments if a.source.origin == "real"}),
            "windows": int(mask.sum()),
            "supervised_eligible_windows": int(subset.supervised_eligible.sum()),
            "unknown_endpoint_windows": int(subset.raw_class.isna().sum()),
            "transient_endpoint_windows": int(subset.phase.eq("transient").sum()),
            "all_missing_selected_sensor_windows": int(batch.quality.loc[mask, "all_missing"].sum()),
            "endpoint_raw_class_counts": dict(sorted(Counter("unknown" if pd.isna(v) else str(int(v))
                                                             for v in subset.raw_class).items())),
            "eligible_family_counts": dict(sorted(Counter(str(int(v)) for v in
                subset.loc[subset.supervised_eligible, "event_family"].dropna()).items())),
        }
    code_paths = [PROJECT_ROOT / "scripts/prepare_data.py", *sorted((PROJECT_ROOT / "ml/data_pipeline").glob("*.py")),
                  *sorted((PROJECT_ROOT / "ml/features").glob("*.py"))]
    summary = {
        "schema_version": "1.0.0",
        "purpose": "development_diagnostic" if args.mode == "diagnostic" else "protected_preprocessing_checks",
        "model_trained": False,
        "pristine_evaluation_claim": False,
        "configuration": config.model_dump(mode="json"),
        "split_configuration": split_config.model_dump(mode="json"),
        "source": json.loads(inputs["manifest"].read_text(encoding="utf-8"))["dataset"],
        "input_source_instances": len(instances),
        "input_rows": sum(len(i.frame) for i in instances),
        "input_origin_counts": dict(sorted(Counter(i.metadata.origin for i in instances).items())),
        "included_rows": sum(len(i.frame) for i in instances if split.partition_for(i.metadata.instance_id) != "excluded"),
        "excluded_source_instances": sum(a.partition == "excluded" for a in split.assignments),
        "windows": len(batch.features),
        "raw_feature_count": len(batch.features.columns),
        "retained_feature_count": len(normalized.columns),
        "dropped_train_allmissing_features": list(pipeline.state.dropped_features),
        "partitions": partitions,
        "split_fingerprint": split.fingerprint,
        "preprocessor_fingerprint": pipeline.state.fingerprint,
        "training_batch_fingerprint": pipeline.state.training_batch_fingerprint,
        "warnings": list(split.warnings),
        "raw_hashes_verified_before_and_after": True,
        "saved_state_and_parquet_roundtrips_exact": True,
        "resampling": "none; cadence gaps start separate segments",
        "artifacts": artifacts,
        "provenance": {
            "base_git_revision": _git_revision(PROJECT_ROOT),
            "input_sha256": input_hashes,
            "code_sha256": {str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"): _sha256(p) for p in code_paths},
            "requirements_sha256": {name: _sha256(PROJECT_ROOT / name)
                                    for name in ("requirements-data.txt", "requirements-pipeline.txt")},
            "python_version": sys.version.split()[0],
            "dependencies": {name: importlib.metadata.version(name)
                             for name in ("numpy", "pandas", "pyarrow", "pydantic")},
            "input_files": [{"instance_id": i.metadata.instance_id, "sha256": i.metadata.sha256}
                            for i in instances],
        },
        "limitations": [
            "All existing source instances and real well IDs are EDA-exposed; diagnostic test is not a final holdout.",
            "Current multiclass real-group coverage is inadequate for protected three-way evaluation.",
            "Near-duplicate subsequences, upstream interpolation and private physical identity remain unverified.",
            "Finite imputation does not establish adequate measured evidence or a future abstention policy.",
            "Window and stride defaults are reproducibility settings, not tuned or validated detection choices.",
        ],
    }
    _json_write(split_path, split.model_dump(mode="json"))
    _json_write(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/subset.json"))
    parser.add_argument("--registry", type=Path, default=Path("data/manifests/dataset_metadata.json"))
    parser.add_argument("--exposure-ledger", type=Path, default=Path("reports/eda/eda_summary.json"))
    parser.add_argument("--window-rows", type=int, default=60)
    parser.add_argument("--stride-rows", type=int, default=10)
    parser.add_argument("--cadence-seconds", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ratios", type=float, nargs=3, default=(0.6, 0.2, 0.2))
    parser.add_argument("--mode", choices=("diagnostic", "protected"), default="diagnostic")
    parser.add_argument("--transient-policy", choices=("family", "exclude"), default="family")
    parser.add_argument("--include-synthetic-train", action="store_true")
    parser.add_argument("--required-families", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--minimum-groups-per-family", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/phase3"))
    parser.add_argument("--split-output", type=Path, default=Path("data/manifests/development_split.json"))
    parser.add_argument("--summary-output", type=Path, default=Path("reports/preprocessing_summary.json"))
    try:
        summary = prepare(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Preprocessing failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: summary[key] for key in
                      ("purpose", "windows", "retained_feature_count", "excluded_source_instances",
                       "raw_hashes_verified_before_and_after", "saved_state_and_parquet_roundtrips_exact")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
