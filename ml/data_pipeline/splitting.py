"""Single-allocation connected-group splits, never a search over class balance."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math

from .io import validate_instance
from .models import (SENSOR_COLUMNS, TRANSIENT_TO_FAMILY, ClassSupport, ExposureLedger,
                     Instance, SplitAssignment, SplitConfig, SplitManifest,
                     dataframe_fingerprint, fingerprint)


def _group_counts(size: int, ratios: tuple[float, float, float]) -> list[int]:
    if size < 3:
        raise ValueError("At least three independent real connected groups are required")
    desired = [size * ratio for ratio in ratios]
    counts = [max(1, math.floor(value)) for value in desired]
    while sum(counts) > size:
        eligible = [i for i in range(3) if counts[i] > 1]
        index = max(eligible, key=lambda i: (counts[i] - desired[i], -i))
        counts[index] -= 1
    while sum(counts) < size:
        index = max(range(3), key=lambda i: (desired[i] - counts[i], -i))
        counts[index] += 1
    return counts


def make_split(instances: tuple[Instance, ...] | list[Instance],
               config: SplitConfig | None = None,
               exposure: ExposureLedger | None = None) -> SplitManifest:
    config = SplitConfig() if config is None else config
    if not isinstance(config, SplitConfig):
        raise ValueError("Validated SplitConfig required")
    if config.mode == "protected" and exposure is None:
        raise ValueError("Protected evaluation requires an explicit exposure ledger")
    if exposure is not None and not isinstance(exposure, ExposureLedger):
        raise ValueError("Validated ExposureLedger required")
    ordered = sorted(instances, key=lambda item: item.metadata.instance_id)
    if not ordered or len({i.metadata.instance_id for i in ordered}) != len(ordered):
        raise ValueError("Nonempty unique source instance IDs required")
    for instance in ordered:
        validate_instance(instance)
    parent = {i.metadata.instance_id: i.metadata.instance_id for i in ordered}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        a, b = sorted((find(left), find(right)))
        parent[b] = a

    links: dict[tuple[str, str], str] = {}
    for instance in ordered:
        meta = instance.metadata
        # Same well implies one group even for nonoverlapping historical intervals.
        keys = [("bytes", meta.sha256)]
        sensors = [name for name in SENSOR_COLUMNS if name in instance.frame]
        keys.append(("sensor-time-content", dataframe_fingerprint(instance.frame[sensors])))
        if meta.origin == "real":
            keys.append(("published-well", meta.well_id))
        if meta.related_group is not None:
            keys.append(("explicit-related-family", meta.related_group))
        for key in keys:
            if key in links:
                union(meta.instance_id, links[key])
            else:
                links[key] = meta.instance_id
    members: dict[str, list[Instance]] = defaultdict(list)
    for instance in ordered:
        members[find(instance.metadata.instance_id)].append(instance)
    groups = {fingerprint(sorted(i.metadata.instance_id for i in group)): group
              for group in members.values()}
    real_groups = [key for key, group in groups.items()
                   if any(i.metadata.origin == "real" for i in group)]
    rank = lambda group: hashlib.sha256(f"{config.seed}:{group}".encode()).hexdigest()
    ranked = sorted(real_groups, key=rank)
    counts = _group_counts(len(ranked), config.ratios)
    partitions = {}
    cursor = 0
    for partition, count in zip(("train", "validation", "test"), counts):
        for group in ranked[cursor:cursor + count]:
            partitions[group] = partition
        cursor += count
    warnings = []
    if config.mode == "diagnostic":
        warnings.append("Development diagnostic partitions; no pristine final evaluation claim")
    assignments = []
    for group_id, group in sorted(groups.items()):
        has_real = group_id in partitions
        has_synthetic = any(i.metadata.origin != "real" for i in group)
        partition = partitions.get(group_id, "train")
        if config.include_synthetic_train and has_synthetic and has_real and partition != "train":
            partition = "train"
            warnings.append("Cross-origin duplicate/related component forced to training; ratios may deviate")
        for instance in group:
            target = partition
            if instance.metadata.origin != "real" and not config.include_synthetic_train:
                target = "excluded"
            assignments.append(SplitAssignment(source=instance.metadata, group_id=group_id,
                                               partition=target))
    assignments.sort(key=lambda entry: entry.source.instance_id)
    if config.mode == "protected":
        assert exposure is not None
        exposed_groups = {entry.group_id for entry in assignments
                          if entry.source.instance_id in exposure.instance_ids
                          or entry.source.well_id in exposure.real_well_ids}
        if any(entry.partition in ("validation", "test") and entry.group_id in exposed_groups
               for entry in assignments):
            raise ValueError("Protected holdout contains an EDA-exposed instance/well/related group")
    support_sets: dict[tuple[str, int], set[str]] = defaultdict(set)
    by_id = {i.metadata.instance_id: i for i in ordered}
    for entry in assignments:
        if entry.partition == "excluded" or entry.source.origin != "real":
            continue
        for raw in by_id[entry.source.instance_id].frame["class"].dropna().unique():
            family = TRANSIENT_TO_FAMILY.get(int(raw), int(raw))
            support_sets[(entry.partition, family)].add(entry.group_id)
    support = []
    for partition in ("train", "validation", "test"):
        if not any(a.partition == partition and a.source.origin == "real" for a in assignments):
            raise ValueError("Every partition must contain real connected groups")
        for family in config.required_families:
            count = len(support_sets[(partition, family)])
            support.append(ClassSupport(partition=partition, family=family, real_groups=count))
            if count < config.minimum_groups_per_family:
                message = f"{partition}: family {family} has {count} real groups; insufficient declared support"
                if config.mode == "protected":
                    raise ValueError(message)
                warnings.append(message)
    payload = {"version": "1.0.0", "algorithm": "sha256-ranked-connected-groups-v1",
               "config": config.model_dump(mode="json"),
               "assignments": [entry.model_dump(mode="json") for entry in assignments],
               "exposure_sha256": None if exposure is None else exposure.ledger_sha256,
               "support": [record.model_dump(mode="json") for record in support],
               "warnings": warnings}
    return SplitManifest.model_validate({**payload, "fingerprint": fingerprint(payload)})
