"""Acquire a bounded, byte-preserving 3W audit subset from an immutable Git revision.

Standard library only. Importing this module never performs network or file writes.
The saved manifest is the replayable acquisition plan; --offline verifies it locally.
"""

from __future__ import annotations

import argparse
import configparser
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from http.client import IncompleteRead
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "https://github.com/petrobras/3W"
REVISION = "914af287b1cf3e5207dce0da1e9dc08361c9adeb"
VERSION = "2.0.0"
DEFAULT_MANIFEST = "data/manifests/subset.json"
RAW_PREFIX = f"data/raw/3w/{VERSION}/{REVISION}"
MAX_FILES = 30
MAX_BYTES = 100 * 1024 * 1024
METADATA_PATHS = (
    "dataset/dataset.ini", "3W_DATASET_STRUCTURE.md", "README.md",
    "dataset/README.md", "dataset/LICENSE-CC-BY", "LICENSE.md", "CITATION.md",
    "toolkit/ThreeWToolkit/utils/downloader.py",
)
SOURCE_RE = re.compile(
    r"^dataset/([0-9])/(WELL-[0-9]+_[0-9]+|SIMULATED_[0-9]+|DRAWN_[0-9]+)\.parquet$"
)


class AcquisitionError(RuntimeError):
    """An acquisition plan, access attempt or integrity check failed."""


def source_identity(source_path: str) -> dict[str, Any]:
    match = SOURCE_RE.fullmatch(source_path)
    if match is None:
        raise AcquisitionError(f"Unexpected source path: {source_path!r}")
    event_code, stem = match.groups()
    if stem.startswith("WELL-"):
        kind, well = "real", stem.split("_", 1)[0]
    elif stem.startswith("SIMULATED_"):
        kind, well = "simulated", None
    else:
        kind, well = "drawn", None
    identity = hashlib.sha256(f"{REVISION}:{source_path}".encode()).hexdigest()
    return {"source_kind": kind, "event_code": int(event_code),
            "well_identifier": well, "source_instance_id": f"3w:{identity}"}


def safe_path(root: Path, relative: str, required_prefix: str) -> Path:
    """Reject traversal, absolute names and symlink escapes before any write."""
    posix = PurePosixPath(relative)
    if (not relative or "\\" in relative or ":" in relative or posix.is_absolute()
            or any(part in {".", ".."} for part in relative.split("/"))):
        raise AcquisitionError(f"Unsafe relative path: {relative!r}")
    expected = root.joinpath(*PurePosixPath(required_prefix).parts).resolve()
    target = root.joinpath(*posix.parts).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_relative_to(expected):
        raise AcquisitionError(f"Path leaves its allowed directory: {relative!r}")
    return target


def file_hashes(path: Path) -> tuple[int, str, str]:
    size = path.stat().st_size
    blob = hashlib.sha1(f"blob {size}\0".encode())
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            blob.update(chunk)
            sha256.update(chunk)
    return size, blob.hexdigest(), sha256.hexdigest()


def check_bytes(path: Path, entry: dict[str, Any]) -> str:
    size, blob, sha256 = file_hashes(path)
    if size != entry["size_bytes"] or blob != entry["git_blob_sha1"]:
        raise AcquisitionError(f"Conflicting bytes; refusing overwrite: {entry['source_path']}")
    if entry.get("sha256") is not None and sha256 != entry["sha256"]:
        raise AcquisitionError(f"SHA-256 mismatch: {entry['source_path']}")
    return sha256


def fetch_bytes(url: str, *, limit: int, timeout: float, retries: int) -> bytes:
    """Bound response size and retry only transport/temporary HTTP failures."""
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "OilWell-AI-Phase1-Audit/1.0"})
            with urlopen(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                if length is not None and int(length) > limit:
                    raise AcquisitionError(f"Response exceeds byte limit: {url}")
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise AcquisitionError(f"Response exceeds byte limit: {url}")
                return payload
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == retries:
                raise AcquisitionError(f"HTTP {exc.code} accessing {url}") from exc
        except (URLError, TimeoutError, ConnectionError, OSError, IncompleteRead) as exc:
            if attempt == retries:
                raise AcquisitionError(f"Access failed for {url}: {exc}") from exc
        time.sleep(min(2 ** attempt, 8))
    raise AssertionError("unreachable")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def acquire_entry(root: Path, entry: dict[str, Any], *, offline: bool,
                  timeout: float, retries: int) -> str:
    destination = safe_path(root, entry["local_path"], RAW_PREFIX)
    if destination.exists():
        return check_bytes(destination, entry)
    if offline:
        raise AcquisitionError(f"Offline file missing: {entry['local_path']}")
    url = f"https://raw.githubusercontent.com/petrobras/3W/{REVISION}/{entry['source_path']}"
    payload = fetch_bytes(url, limit=entry["size_bytes"], timeout=timeout, retries=retries)
    blob = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    if len(payload) != entry["size_bytes"] or blob != entry["git_blob_sha1"]:
        raise AcquisitionError(f"Downloaded content differs from pinned Git blob: {entry['source_path']}")
    if entry.get("sha256") is not None and sha256 != entry["sha256"]:
        raise AcquisitionError(f"Downloaded SHA-256 mismatch: {entry['source_path']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes complete bytes atomically and fails if the target exists.
        # Unlike os.replace, it never clobbers a concurrent writer's original file.
        try:
            os.link(temporary, destination)
        except FileExistsError:
            return check_bytes(destination, entry)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return sha256


def make_entry(item: dict[str, Any], *, data: bool) -> dict[str, Any]:
    source = item["path"]
    result = {"source_path": source, "local_path": f"{RAW_PREFIX}/{source}",
              "size_bytes": item["size"], "git_blob_sha1": item["sha"], "sha256": None}
    if data:
        result.update(source_identity(source))
    return result


def select_entries(tree: dict[str, Any], *, extra_real_wells: int,
                   max_files: int, max_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if tree.get("truncated") is not False:
        raise AcquisitionError("Git tree is truncated or missing completeness flag")
    if tree.get("sha") != REVISION:
        raise AcquisitionError("Git tree revision differs from the immutable pin")
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    candidates: list[dict[str, Any]] = []
    for item in tree["tree"]:
        if item.get("type") == "blob" and SOURCE_RE.fullmatch(item["path"]):
            entry = make_entry(item, data=True)
            candidates.append(entry)
            groups[(entry["event_code"], entry["source_kind"])].append(entry)
    if not groups or {key[0] for key in groups} != set(range(10)):
        raise AcquisitionError("Pinned tree does not cover the documented ten event directories")
    selected = [min(items, key=lambda x: (x["size_bytes"], x["source_path"]))
                for _, items in sorted(groups.items())]
    if len(selected) > max_files or sum(x["size_bytes"] for x in selected) > max_bytes:
        raise AcquisitionError("Covering each class/origin stratum exceeds the requested audit budget")
    wells = {item["well_identifier"] for item in selected if item["source_kind"] == "real"}
    extras = 0
    for entry in sorted(candidates, key=lambda x: (x["size_bytes"], x["source_path"])):
        if extras >= extra_real_wells or len(selected) >= max_files:
            break
        if entry["source_kind"] != "real" or entry["well_identifier"] in wells:
            continue
        if sum(item["size_bytes"] for item in selected) + entry["size_bytes"] > max_bytes:
            continue
        selected.append(entry)
        wells.add(entry["well_identifier"])
        extras += 1
    selected.sort(key=lambda item: item["source_path"])
    inventory = {"file_count": len(candidates),
                 "bytes": sum(item["size_bytes"] for item in candidates),
                 "by_origin": dict(sorted(Counter(x["source_kind"] for x in candidates).items())),
                 "by_event_directory": dict(sorted(Counter(str(x["event_code"]) for x in candidates).items())),
                 "available_strata": [{"event_code": code, "source_kind": kind, "files": len(items)}
                                      for (code, kind), items in sorted(groups.items())]}
    return selected, inventory


def build_manifest(*, extra_real_wells: int, max_files: int, max_bytes: int,
                   timeout: float, retries: int) -> dict[str, Any]:
    url = f"https://api.github.com/repos/petrobras/3W/git/trees/{REVISION}?recursive=1"
    tree_bytes = fetch_bytes(url, limit=10 * 1024 * 1024, timeout=timeout, retries=retries)
    tree = json.loads(tree_bytes)
    files, inventory = select_entries(tree, extra_real_wells=extra_real_wells,
                                     max_files=max_files, max_bytes=max_bytes)
    by_path = {entry["path"]: entry for entry in tree["tree"] if entry.get("type") == "blob"}
    missing = set(METADATA_PATHS) - set(by_path)
    if missing:
        raise AcquisitionError(f"Pinned source metadata missing: {sorted(missing)}")
    metadata = [make_entry(by_path[path], data=False) for path in METADATA_PATHS]
    if sum(x["size_bytes"] for x in files + metadata) > max_bytes:
        raise AcquisitionError("Data plus provenance documents exceed audit byte budget")
    return {
        "schema_version": "1.0.0", "status": "planned",
        "dataset": {"repository": REPOSITORY, "revision": REVISION, "version": VERSION,
                    "license": "CC-BY-4.0", "code_license": "Apache-2.0",
                    "attribution": "Petrobras and the 3W contributors",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/"},
        "selection": {"strategy": "smallest_per_available_event_origin_stratum_then_new_real_wells",
                      "version": "1.0.0", "tie_break": "source_path_ascending", "random_seed": None,
                      "extra_real_wells_requested": extra_real_wells,
                      "max_files": max_files, "max_bytes": max_bytes,
                      "selected_file_count": len(files),
                      "selected_data_bytes": sum(x["size_bytes"] for x in files),
                      "inventory": inventory,
                      "limitations": ["Purposive size-biased audit subset, not a prevalence estimate.",
                                      "No train/validation/test partitions; no training suitability claim.",
                                      "Directory/origin coverage does not prove row-label or phase coverage."]},
        "provenance": {"tree_url": url, "tree_response_sha256": hashlib.sha256(tree_bytes).hexdigest(),
                       "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                       "transformations": "None; original downloaded file bytes are retained unchanged."},
        "metadata": metadata, "files": files,
    }


def validate_manifest(manifest: dict[str, Any], root: Path) -> None:
    if not isinstance(manifest, dict):
        raise AcquisitionError("Acquisition manifest must be a JSON object")
    if manifest.get("schema_version") != "1.0.0":
        raise AcquisitionError("Unsupported manifest schema")
    dataset = manifest.get("dataset", {})
    if (dataset.get("repository"), dataset.get("revision"), dataset.get("version")) != (REPOSITORY, REVISION, VERSION):
        raise AcquisitionError("Manifest source/version differs from the pinned dataset")
    files, metadata = manifest.get("files", []), manifest.get("metadata", [])
    if not files or len(files) > MAX_FILES:
        raise AcquisitionError("Manifest exceeds bounded file count or contains no data")
    if {item["source_path"] for item in metadata} != set(METADATA_PATHS):
        raise AcquisitionError("Manifest must contain the exact provenance document set")
    seen: set[str] = set()
    for item in metadata + files:
        source = item["source_path"]
        if source in seen:
            raise AcquisitionError(f"Duplicate manifest source: {source}")
        seen.add(source)
        if item["local_path"] != f"{RAW_PREFIX}/{source}":
            raise AcquisitionError(f"Manifest destination differs from derived source path: {source}")
        safe_path(root, item["local_path"], RAW_PREFIX)
        if not isinstance(item["size_bytes"], int) or not 0 < item["size_bytes"] <= MAX_BYTES:
            raise AcquisitionError(f"Invalid file size: {source}")
        if not re.fullmatch(r"[0-9a-f]{40}", item["git_blob_sha1"]):
            raise AcquisitionError(f"Invalid Git blob hash: {source}")
        if item.get("sha256") is not None and not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise AcquisitionError(f"Invalid SHA-256: {source}")
    for item in files:
        identity = source_identity(item["source_path"])
        if any(item.get(key) != value for key, value in identity.items()):
            raise AcquisitionError(f"Manifest identity mismatch: {item['source_path']}")
    if sum(item["size_bytes"] for item in metadata + files) > MAX_BYTES:
        raise AcquisitionError("Manifest exceeds the hard 100 MiB audit ceiling")


def parse_registry(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    ini = next(item for item in manifest["metadata"] if item["source_path"] == "dataset/dataset.ini")
    path = safe_path(root, ini["local_path"], RAW_PREFIX)
    check_bytes(path, ini)
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    if parser["VERSION"]["DATASET"] != VERSION:
        raise AcquisitionError("Downloaded dataset.ini has an unexpected dataset version")
    properties = dict(parser["PARQUET_FILE_PROPERTIES"])
    sensors = [{"name": name, "description": description,
                "unit_or_domain": description.rsplit("[", 1)[-1].rstrip("]")}
               for name, description in properties.items() if name not in {"timestamp", "class", "state"}]
    events = []
    for name in parser["EVENTS"]["NAMES"].replace("\n", "").split(","):
        name = name.strip()
        code = parser.getint(name, "LABEL")
        transient = parser.getboolean(name, "TRANSIENT", fallback=False)
        events.append({"name": name, "label": code, "description": parser[name]["DESCRIPTION"],
                       "transient": transient,
                       "transient_label": code + parser.getint("EVENTS", "TRANSIENT_OFFSET") if transient else None})
    return {"schema_version": "1.0.0", "dataset_version": VERSION, "dataset_revision": REVISION,
            "source_path": ini["source_path"], "source_sha256": ini["sha256"],
            "sensor_columns": sensors, "target_columns": ["class"],
            "auxiliary_label_columns": ["state"], "index_columns": ["timestamp"],
            "excluded_feature_metadata": ["class", "state", "timestamp", "source_path", "source_kind",
                                          "event_code", "well_identifier", "source_instance_id"],
            "events": events,
            "state_semantics": {"description": properties["state"],
                                "code_mapping": None,
                                "limitation": "dataset.ini does not define state code meanings; see independent audit of descriptor."},
            "source_timezone": None, "transformations": "None"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Repository-relative acquisition manifest")
    parser.add_argument("--dry-run", action="store_true", help="Show saved/planned selection; never write or download telemetry")
    parser.add_argument("--offline", action="store_true", help="Verify saved manifest and files with no network or writes")
    parser.add_argument("--extra-real-wells", type=int, default=4, help="Extra distinct real well IDs after stratum coverage")
    parser.add_argument("--max-files", type=int, default=MAX_FILES)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if not (0 <= args.extra_real_wells <= MAX_FILES and 1 <= args.max_files <= MAX_FILES
                and 1 <= args.max_bytes <= MAX_BYTES and 0 < args.timeout <= 120 and 0 <= args.retries <= 5):
            raise AcquisitionError("Invalid bounds: <=30 files, <=100MiB, timeout (0,120], retries 0..5")
        root = args.root.resolve()
        manifest_path = safe_path(root, args.manifest, "data/manifests")
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        elif args.offline:
            raise AcquisitionError("Offline acquisition manifest does not exist")
        else:
            manifest = build_manifest(extra_real_wells=args.extra_real_wells, max_files=args.max_files,
                                      max_bytes=args.max_bytes, timeout=args.timeout, retries=args.retries)
        validate_manifest(manifest, root)
        total = sum(item["size_bytes"] for item in manifest["files"] + manifest["metadata"])
        if len(manifest["files"]) > args.max_files or total > args.max_bytes:
            raise AcquisitionError("Saved manifest exceeds the requested CLI budget")
        if args.dry_run:
            print(json.dumps({"revision": REVISION, "selection": manifest["selection"],
                              "total_bytes_with_metadata": total,
                              "source_paths": [x["source_path"] for x in manifest["files"]]}, indent=2))
            return 0
        if not args.offline:
            atomic_json(manifest_path, manifest)
        for item in manifest["metadata"] + manifest["files"]:
            existing = safe_path(root, item["local_path"], RAW_PREFIX).exists()
            item["sha256"] = acquire_entry(root, item, offline=args.offline, timeout=args.timeout, retries=args.retries)
            print(f"{'verified' if existing else 'downloaded'} {item['source_path']} ({item['size_bytes']} bytes)", flush=True)
            if not args.offline:
                atomic_json(manifest_path, manifest)
        registry = parse_registry(root, manifest)
        if not args.offline:
            manifest["status"] = "complete"
            manifest.setdefault("completed_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
            atomic_json(manifest_path, manifest)
            atomic_json(safe_path(root, "data/manifests/dataset_metadata.json", "data/manifests"), registry)
        print(json.dumps({"status": "verified" if args.offline else "complete", "files": len(manifest["files"]),
                          "data_bytes": sum(x["size_bytes"] for x in manifest["files"]),
                          "metadata_files": len(manifest["metadata"]), "sensor_columns": len(registry["sensor_columns"])}))
        return 0
    except (AcquisitionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
