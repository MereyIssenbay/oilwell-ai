"""Bounded acquisition and immutable-file behavior; uses only synthetic bytes."""

from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "download_data.py"
SPEC = importlib.util.spec_from_file_location("download_data_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)


def entry(payload: bytes = b"synthetic Parquet fixture bytes") -> dict:
    source = "dataset/0/WELL-00001_20000101000000.parquet"
    result = {
        "source_path": source,
        "local_path": f"{downloader.RAW_PREFIX}/{source}",
        "size_bytes": len(payload),
        "git_blob_sha1": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    result.update(downloader.source_identity(source))
    return result


def test_source_identity_is_revision_and_full_path_scoped() -> None:
    first = downloader.source_identity("dataset/1/SIMULATED_00001.parquet")
    second = downloader.source_identity("dataset/2/SIMULATED_00001.parquet")
    assert first["source_instance_id"] != second["source_instance_id"]
    assert first["well_identifier"] is None
    assert first["source_kind"] == "simulated"
    assert downloader.source_identity("dataset/7/DRAWN_00001.parquet")["source_kind"] == "drawn"


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/absolute", "data/raw/../../escape", "data\\raw\\bad"])
def test_path_traversal_is_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(downloader.AcquisitionError):
        downloader.safe_path(tmp_path, path, downloader.RAW_PREFIX)


def test_verified_file_is_reused_without_network_or_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = b"synthetic Parquet fixture bytes"
    record = entry(data)
    path = tmp_path / record["local_path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    before = path.stat().st_mtime_ns
    monkeypatch.setattr(downloader, "fetch_bytes", lambda *a, **kw: pytest.fail("Network used for existing file"))
    assert downloader.acquire_entry(tmp_path, record, offline=False, timeout=1, retries=0) == record["sha256"]
    assert path.read_bytes() == data and path.stat().st_mtime_ns == before


def test_corrupt_existing_file_is_not_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = entry()
    path = tmp_path / record["local_path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt")
    monkeypatch.setattr(downloader, "fetch_bytes", lambda *a, **kw: pytest.fail("Network used after corruption"))
    with pytest.raises(downloader.AcquisitionError, match="refusing overwrite"):
        downloader.acquire_entry(tmp_path, record, offline=False, timeout=1, retries=0)
    assert path.read_bytes() == b"corrupt"


def test_download_rejects_wrong_pinned_blob_without_partial_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = entry()
    monkeypatch.setattr(downloader, "fetch_bytes", lambda *a, **kw: b"wrong")
    with pytest.raises(downloader.AcquisitionError, match="differs from pinned"):
        downloader.acquire_entry(tmp_path, record, offline=False, timeout=1, retries=0)
    assert not (tmp_path / record["local_path"]).exists()


def test_new_file_is_published_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = b"synthetic Parquet fixture bytes"
    record = entry(data)
    monkeypatch.setattr(downloader, "fetch_bytes", lambda *a, **kw: data)
    downloader.acquire_entry(tmp_path, record, offline=False, timeout=1, retries=0)
    path = tmp_path / record["local_path"]
    assert path.read_bytes() == data
    assert list(path.parent.glob("*.partial")) == []


def test_offline_missing_file_never_fetches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(downloader, "fetch_bytes", lambda *a, **kw: pytest.fail("Offline network call"))
    with pytest.raises(downloader.AcquisitionError, match="Offline file missing"):
        downloader.acquire_entry(tmp_path, entry(), offline=True, timeout=1, retries=0)


def synthetic_tree() -> dict:
    items = []
    for event in range(10):
        for well, size in [(1, 100), (2, 50)]:
            items.append({"type": "blob", "path": f"dataset/{event}/WELL-{well:05d}_20000101000000.parquet",
                          "size": size, "sha": "a" * 40})
    return {"sha": downloader.REVISION, "truncated": False, "tree": items}


def test_selection_is_deterministic_and_covers_strata() -> None:
    tree = synthetic_tree()
    first, _ = downloader.select_entries(tree, extra_real_wells=1, max_files=30, max_bytes=10000)
    tree["tree"].reverse()
    second, _ = downloader.select_entries(tree, extra_real_wells=1, max_files=30, max_bytes=10000)
    assert first == second
    assert len(first) == 11
    assert {item["event_code"] for item in first} == set(range(10))
    assert len({item["well_identifier"] for item in first}) == 2


def test_selection_refuses_silent_loss_of_stratum_coverage() -> None:
    with pytest.raises(downloader.AcquisitionError, match="exceeds"):
        downloader.select_entries(synthetic_tree(), extra_real_wells=0, max_files=9, max_bytes=10000)


def test_truncated_tree_is_rejected() -> None:
    tree = synthetic_tree()
    tree["truncated"] = True
    with pytest.raises(downloader.AcquisitionError, match="truncated"):
        downloader.select_entries(tree, extra_real_wells=0, max_files=30, max_bytes=10000)


def test_interrupted_http_response_uses_bounded_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def interrupted(*args: object, **kwargs: object) -> None:
        calls.append(1)
        raise IncompleteRead(b"partial", 10)

    monkeypatch.setattr(downloader, "urlopen", interrupted)
    monkeypatch.setattr(downloader.time, "sleep", lambda seconds: None)
    with pytest.raises(downloader.AcquisitionError, match="Access failed"):
        downloader.fetch_bytes("https://example.invalid", limit=10, timeout=1, retries=2)
    assert len(calls) == 3


def test_dry_run_does_not_write_manifest_or_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use the real plan as metadata only; no source bytes are read or fetched.
    manifest = json.loads((SCRIPT.parents[1] / "data/manifests/subset.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(downloader, "build_manifest", lambda **kw: manifest)
    assert downloader.main(["--root", str(tmp_path), "--dry-run"]) == 0
    assert list(tmp_path.iterdir()) == []
