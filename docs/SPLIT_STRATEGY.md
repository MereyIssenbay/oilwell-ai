# Split strategy and modeling readiness

Phase 2 EDA recommendation, 2026-11-10, retained as the evaluation policy. Phase 3 now authorizes implementation of reusable grouped splitting and preprocessing; see [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md). The existing subset may be partitioned for development diagnostics only. The current 23-file subset is development-exposed. A valid final evaluation requires a separately approved cohort and protected test data; relabeling existing files as test does not erase the information already learned from them.

The user subsequently authorized Phase 4 baseline fitting on the frozen diagnostic split. The [baseline protocol](../reports/baseline/PROTOCOL.md) defines binary detection, fixed model settings and validation-only comparison. The existing test partition is not scored or used for model selection. This limited experiment does not satisfy the protected-cohort requirements below.

Phase 5 subsequently authorizes bounded boosted-model search and validation threshold selection, followed by **one selected-model evaluation on the existing diagnostic test partition**. The [Phase 5 protocol](../reports/experiments/PROTOCOL.md) freezes the search and access gate. This supersedes Phase 4's no-test-scoring rule only after selection is locked; it does not make previously EDA-exposed groups pristine. Split membership, source/feature policy and preprocessing remain unchanged. No test outcome may drive another model or threshold choice.

## Decision

Use **disjoint published real well IDs**, strengthened by duplicate/overlap relationships, as the primary partition unit. Retain all observations and instances of a group in one partition before generating any windows. Keep simulated and hand-drawn sources out of the primary real validation and test sets. Use them only in a later explicitly compared training-augmentation arm, with generator-family limitations documented.

The current subset cannot support the planned normal-plus-two-event-family three-way evaluation while preserving real-well independence and event support in every partition. No undesirable family has three distinct real well IDs in the inspected cohort. Three is only a necessary minimum for one group per partition, not evidence of adequate statistical power or robust representativeness. More groups and multiple episodes would be preferable; required support must be set before model selection.

## Is physical-well grouping possible?

The primary author manuscript says that a real well has one unique identifier regardless of event directory; timestamps distinguish its instances. This establishes a defensible grouping key in the public data: the `WELL-<digits>` prefix. See [3W manuscript, section 3.2](https://arxiv.org/html/2507.01048v1#S3.SS2). The project has no independently verified private mapping to physical assets, so report results as generalization to **held-out published well IDs**, and disclose reliance on the publisher's identity convention.

This is stronger than instance-only splitting and is available for the inspected real data. Do not use instance-only splitting simply to improve class balance. `WELL-00002`, for example, appears in three selected instances across directories 0, 1 and 4; assigning those instances independently would reuse a well across partitions even without timestamp overlap.

For simulated/drawn data, numeric suffixes restart across directories and do not identify physical wells. Revision plus full source path provides unique instance identity, but does not establish independent simulation scenarios or drawing families. A synthetic filename is not a well-group substitute. Unknown generator relationships are a limitation, not permission to split their windows randomly.

## Measured support in the acquired subset

Source: per-row labels in [data_summary.json](../reports/data_summary.json), reconciled in the [Phase 1 audit](DATASET_AUDIT.md), and the current [EDA artifacts](../reports/eda/README.md). Counts below combine only documented base/transient codes for each family; directory presence alone is insufficient.

| Family | Distinct real well IDs with observed family rows | Published IDs |
| --- | ---: | --- |
| 0 Normal | 10 | 00002, 00004, 00005, 00006, 00008, 00011, 00016, 00024, 00029, 00036 |
| 1 Abrupt increase of BSW | 1 | 00002 |
| 2 Spurious closure of DHSV | 1 | 00011 |
| 3 Severe slugging | 1 | 00001 |
| 4 Flow instability | 2 | 00002, 00010 |
| 5 Rapid productivity loss | 1 | 00016 |
| 6 Quick restriction in PCK | 1 | 00004 |
| 7 Scaling in PCK | 1 | 00024 |
| 8 Hydrate in production line | 1 | 00029 |
| 9 Hydrate in service line | 0 | None observed in selected real rows |

Prefixes `WELL-` are omitted in this table only. Across all selected real instances there are 12 distinct published well IDs. Normal observations can occur in an undesirable-event instance and are not restricted to directory 0. Steady code 7 is absent even though transient 107 is present; real family 9 is absent even though directory 9 is represented. This matters for evaluation support and phase reporting.

The subset was selected partly by compressed file size. It is not a prevalence sample, and its 582,220 autocorrelated rows are not 582,220 independent examples. The absence of overlapping same-well intervals or identical full-frame fingerprints in this subset does not prove absence of near-duplicates or shared signal segments in a larger cohort.

## Protocol for a future approved cohort

1. **Freeze the intended claim before allocating test data.** Specify supported families, source domain, sensors/availability criteria, label policy, detection versus onset objective, and minimum independent groups/episodes. The recommended first claim is closed-set event-family detection on real data from held-out published well IDs. Do not claim unknown-event detection from low confidence alone.
2. **Maintain an exposure ledger.** All 23 current instances and their 12 real well IDs have influenced EDA/hypotheses and belong to development. Future files from an already-explored well remain in that development group. New final-test groups must use as-yet-unexplored real well IDs and have no duplicate/overlap links to development sources. The EDA summary records the inspected source IDs and manifest hash; preserve it as an exposure record.
3. **Build connected groups before windows.** Link every real instance sharing a published well ID; also link byte-identical, demonstrably duplicated or overlapping copies and any documented same-asset aliases. Review suspicious near-duplicate subsequences. Merge linked groups transitively even if that makes a desired class split impossible. Record which links are proven and which require conservative quarantine.
4. **Choose a feasible cohort from row-level support.** A dataset custodian may check schema, integrity, necessary class/phase counts and group coverage under a fixed eligibility rule, without providing test sensor distributions, plots or performance to the model developer. Expand or narrow event scope if independent class support is insufficient. Do not repeatedly inspect test curves or scores to find a favorable split.
5. **Allocate real groups once using a documented deterministic policy.** A starting planning target is approximately 60% train, 20% validation, 20% test by group count, with a declared seed such as 42. These are proposed ratios, not an executed split or measured optimum. Nonoverlap and adequate class/phase/episode support take priority over exact ratios; log deviations. Stratification must be group-aware and validated, not assumed from row percentages.
6. **Freeze the final test manifest and access boundary.** Record source revision, full paths, checksums, connected-group IDs, exposure status, eligibility rules, seed, algorithm/version and class/episode/group counts. The model-development team uses only train and validation; open final test outcomes after the pipeline, calibration, thresholds and acceptance criteria are fixed. A test-driven change becomes a new development iteration requiring a fresh final evaluation claim.
7. **Use development data for selection only.** Within training, use grouped cross-validation when support permits. Use the real validation groups for decisions such as window length, model selection, calibration and alert thresholds, with additional cross-fitting or separated calibration folds if needed. Do not fit imputation/scaling/feature selection on the combined train+validation+test data.
8. **Evaluate once with explicit denominators.** Report per-family/phase/source metrics, unique wells, source instances, event episodes, observed normal hours and misses. For the held-out-well claim, estimate uncertainty by well clusters, preserving dependence among episodes within each well; a hierarchical well/episode procedure may be appropriate when group counts permit it. Do not treat separate episodes from one well or overlapping windows as independent. With too few wells, disclose that uncertainty is not reliably estimable. Undefined or unsupported metrics remain undefined.

Standard scikit-learn grouped splitters can enforce group separation, but a splitter name alone does not guarantee every class appears in every partition. `GroupShuffleSplit` proportions refer to groups, and repeated random splits can reuse test groups across repetitions. The proposed final holdout is a single frozen allocation, not a repeated split search. See [grouped cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data) and [GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html). No splitter was executed in Phase 2. Phase 3 implements its own deterministic group allocation without requiring an estimator library; the development partition must not be described as the protected holdout above.

## Time, labels and window boundaries

- Never create a window across source instances, partition boundaries, invalid timestamp gaps or unrelated wells. All overlapping windows derived from one source remain in its group/partition.
- Retain source time separately from processing time. Source timestamps are naive and their true timezone is unverified; do not interpret absolute calendar position or start offset as a sensor feature.
- Use only measurements available at the prediction timestamp. No centered windows, future interpolation, backward-fill or future-window normalization. Upstream historical interpolation remains a source limitation even if project code is causal.
- Preserve `class` and `state` as labels. `class` defines evaluation targets; `state` is an auxiliary operational label, not an input sensor. The 27 named sensors are the only candidate sensor fields; missingness indicators, if tested later, require explicit shortcut controls.
- Map only documented transients 101, 102, 105, 106, 107, 108 and 109 to their event families. Report transient and base-label results separately. Unknown labels are excluded from supervised target scoring and remain visible in denominators/quality reports; they are never converted to normal.
- The first hour of every selected real instance is unlabeled. A transition from unknown to a known abnormal label is **not a verified event onset**. For delay metrics, require an eligible observed boundary and state how left-censored events, already-active events and misses are handled. Do not join events across null segments or file boundaries.
- If a separate future objective uses chronological prediction within known wells, state that different claim explicitly. Purge windows sharing observations across time cutoffs, with a gap at least covering the maximum lookback and label horizon; apply any longer event/recovery exclusion rule defined by the task. That protocol does not establish generalization to unseen well IDs.

## If only instance-level identity is available

The current real subset has a published well key, so this fallback is not recommended here. For another source lacking stable well IDs, whole-instance/duplicate-family grouping is the minimum acceptable boundary. It prevents direct overlapping-window leakage but cannot prevent the same physical well or generator from appearing under different IDs in train and test. Describe the result as held-out-instance performance under unknown asset dependence. Do not relabel it unseen-well generalization, and do not use it to satisfy the well-disjoint acceptance gate.

## Shortcut risks and required controls

| Risk | Why it matters here | Required future control |
| --- | --- | --- |
| Targets/status included in numeric features | Both class and state are numeric; upstream loader can retain state | Explicit sensor allowlist and automated exclusion assertion |
| Filenames/directories/IDs or time offset | Metadata carries event, origin and source identity; initial unknown interval repeats | Exclude identifiers, directory labels and file-start offset from predictor inputs |
| Missingness identifies source or well | Four sensors are globally missing in the subset; availability differs sharply by origin | Real-only baseline, missingness-only diagnostic and value/availability ablations on identical groups |
| Absolute levels identify wells | Multiple instances share a well; pooled ranges/correlations mix well and operating conditions | Well-disjoint evaluation; compare causal within-window changes against absolute levels in a later controlled experiment |
| Source or event mixtures distort correlations | Different origins have different support and generating mechanisms | Report within-source and per-instance correlations, pair counts, constants and missingness; no causal claims |
| Reused samples or event fragments | Adjacent 1 Hz readings/windows are strongly dependent | Group before windowing; prohibit duplicate/overlapping segments across partitions |
| EDA/test contamination | Current files already informed sensor and hypothesis choices | Keep them in development; reserve fresh real groups for final testing |
| Synthetic family dependence | Generator/drawing-family relationships are not fully documented | Synthetic/drawn training-only experimental arms; separate domain reporting and family-aware grouping when known |
| Label-derived event alignment | True transitions are available offline but not to a live detector | Use labels only for analysis/evaluation; no true-boundary alignment or future onset indicators in inputs |

## Recommended modeling sequence after approval

First obtain a feasible real cohort and protect its holdout. Then establish a simple causal scikit-learn baseline using a small sensor subset chosen from training availability, with explicit abstention for insufficient inputs. Compare value, missingness and combined-input controls, and per-window change summaries versus absolute levels under identical grouped partitions. Compare XGBoost only after a reproducible baseline; treat any synthetic augmentation as a separate arm with the real holdout unchanged. Test the hypotheses in [ML_HYPOTHESES.md](ML_HYPOTHESES.md) without converting exploratory correlations into physical explanations.

An explicitly scoped binary normal-versus-undesirable prototype could use the current data for **development-only** grouped diagnostics after approval; its mixture of event families must be reported, and it would still have no untouched final test. It is not a substitute for the originally proposed multiclass acceptance claim. No model, metric target, split outcome or successful detection result is asserted by this recommendation.

**Phase 2 ended at EDA and recommendations.** Later approvals authorized Phase 3 preprocessing and Phase 4 diagnostic baseline fitting. Cohort expansion, advanced model search and protected-test readiness remain outside the completed data phases; each requires an explicit subsequent scope.
