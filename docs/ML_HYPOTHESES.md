# Testable ML hypotheses

Status: Phase 2 EDA design, 2026-11-10. **Five experiments are proposed below; none has been trained or evaluated.** Their observations describe the acquired 23-file, size-biased development subset. They are not claims of detection accuracy, physical causation or deployment readiness.

Phase 3 authorizes reusable preprocessing and feature implementation under [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md). It does not authorize fitting event detectors or establish any of the five effects below. Statements about Phase 2 implementation scope remain historical.

Phase 4 subsequently authorizes [fixed diagnostic reference models](../reports/baseline/PROTOCOL.md). That comparison supplies baseline observations but does not execute the controlled ablations needed to establish the five hypotheses below. The Phase 2/3 scope statements remain historical.

The [acquisition manifest](../data/manifests/subset.json) fixes 3W v2.0.0 at revision `914af287b1cf3e5207dce0da1e9dc08361c9adeb`. The [measured audit](DATASET_AUDIT.md), [per-file summary](../reports/data_summary.json) and [EDA summary](../reports/eda/eda_summary.json) distinguish actual source measurements from metadata assumptions. The orchestrator's [split strategy](SPLIT_STRATEGY.md) governs all future experiments. All 23 inspected files and their 12 real well IDs are EDA-exposed development data, not a clean final test set.

## Input, target and evaluation boundary

Only the exact 27 sensor columns in the verified registry are candidate sensor inputs. `class` is the observation target; `state` is an auxiliary operational label. Neither is a sensor feature. File/directory names, well/instance IDs, source origin, row number, elapsed time since an annotated event, future label/run duration and partition membership are excluded from deployable inputs. Well IDs and origin may be used outside the model for grouping, diagnostics and reporting.

The eventual task must declare its supported event families before training. Map only the documented transient codes 101, 102, 105, 106, 107, 108 and 109 to their corresponding event families for a family-classification experiment; preserve the original code for separate phase evaluation. Code 0 means normal. Null labels mean unknown and are not normal examples. Do not broadcast a directory label to its rows. None of these mappings changes the saved raw files.

Future feature construction must use a trailing window ending at the prediction timestamp, with no centered window, future interpolation, future fit statistics or cross-instance history. A proposed change/slope feature means a causal past-to-current calculation, not a production feature implemented in Phase 2. Scaling, imputation, feature selection and model fitting use training groups only. Calibration, window/stride choices, alert thresholds and dwell/recovery policy use development validation only. Existing source-system interpolation limits any claim that replay scores predict prospective unprocessed telemetry.

Every experiment must use the same eligible windows, target policy and frozen group partitions for its compared arms. Record exclusions, unavailable predictions and coverage; a method cannot improve its reported score simply by dropping difficult missing-data windows. No particular window length, score, improvement margin or threshold is established here.

## H1: Sensor values provide information beyond availability patterns

**Observation.** Four columns (`P-JUS-BS`, `P-MON-SDV-P`, `PT-P`, `QBS`) are completely missing across the selected subset. Missingness differs strongly by origin: selected simulated and drawn instances lack many of the added variables, while real files have a different availability profile. These facts are recorded by sensor and origin in `aggregate.sensors` and `aggregate.by_origin` of the [summary](../reports/data_summary.json). They make an apparently successful availability-based classifier a plausible shortcut, not proof of undesirable-event detection.

EDA evidence: [source missingness](../reports/eda/02_missing_by_source.png), [real-family missingness](../reports/eda/03_missing_by_real_family.png), and [missingness counts/support by source and raw class](../reports/eda/missing_by_source_class.csv). The class-conditioned diagnostic uses target labels only to audit patterns; it is not an input representation available at inference.

**Hypothesis.** On independent real well groups with comparable sensor coverage, observed sensor values add event-family information beyond a model using only missing/available masks.

**Future test and controls.** Compare a small scikit-learn baseline on (a) sensor availability masks only, (b) causal sensor-value summaries with the same declared missing-data policy, and (c) values plus masks. The mask-only arm is a shortcut diagnostic, not a proposed production detector. Use the same real-only partitions and class support. Repeat with a declared common sensor set and report performance within availability strata so origin/availability differences cannot masquerade as event signal. A separate origin-prediction probe may diagnose domain information but must never be scored as event detection or used to choose a final test set.

**Primary comparison.** Group-balanced event-family macro F1 among supported classes, accompanied by per-class recall, prediction coverage, false-alert episodes per eligible normal hour, and the number of independent real wells/instances contributing to each availability stratum. Report the normal-hour denominator and abstained windows for every arm.

**Falsifying outcome.** The value-based arm does not outperform the availability-only control under the predeclared comparison criterion, or its apparent gain disappears within matched availability strata/fresh real groups. Such an outcome supports a shortcut explanation or insufficient evidence; it does not establish that sensor values are universally useless.

**Current limit.** The sparse selected real cohort cannot establish this generalization test. An entire missing column has no value signal to assess, and missingness can encode both genuine sensor availability and acquisition/source artifacts.

## H2: Past-to-current changes transfer across wells better than absolute levels alone

**Observation.** The selected real sources include the same published `WELL-00002` ID in a normal instance, an event-1 instance and an event-4 instance. Grouping only by file would therefore put one well into several partitions. The normal source `dataset/0/WELL-00002_20131214190030.parquet` and event-1 source `dataset/1/WELL-00002_20140126180030.parquet` provide a concrete within-well comparison; `P-PDG`, `P-TPT` and `T-TPT` are available in both. These are different historical intervals, not a matched causal intervention.

In the event-1 instance, the median `P-TPT` reading is about 17.09 MPa over 4,754 known-normal observations and 14.56 MPa over 9,617 known-abnormal observations (the source table retains Pa). Meanwhile `P-PDG` is exactly zero across the observed conditions in the three selected `WELL-00002` files. Zero is retained as an observed value: this EDA does not establish whether it is physically meaningful or an undocumented placeholder. Availability alone therefore does not guarantee useful variation. See [the same-well time-series comparison](../reports/eda/05_real_normal_vs_event.png), [per-instance condition summaries](../reports/eda/normal_abnormal_summary.csv) and [real-instance comparison chart](../reports/eda/08_normal_abnormal.png). These descriptive level differences do not demonstrate causation or predictive generalization.

**Hypothesis.** Adding trailing changes or variability to level-only sensor summaries improves transfer to unseen real well IDs, rather than merely memorizing well-specific operating levels.

**Future test and controls.** Compare level-only, change/variability-only and combined summaries using the same simple baseline, causal windows, sensors and group assignments. Fit any centering/scaling on training groups only; never normalize by a whole held-out file or by its future median. Keep explicit well identity out of the model. Use within-well plots to diagnose whether between-well offsets dominate, but evaluate the hypothesis on withheld real well groups rather than same-well held-out rows.

**Primary comparison.** Event-family macro F1 with equal total weight per evaluated well, plus per-well/per-class recall and explicit class support. A class absent from a well is not assigned a fictitious recall or silently included as a zero. Also report false-alert episodes per normal hour at the same validation-selected operating rule and the contributing group count. Correlated rows are not independent repeats.

**Falsifying outcome.** Change-based inputs fail to improve fresh-well performance under the predeclared comparison criterion, or apparent gains occur only when the same well appears in training and evaluation. A gain on one known well would not support an unseen-well claim.

**Current limit.** A stable published well pseudonym supports grouping, but no private asset mapping was verified. Most undesirable families in the selected real data have only one well, so operating level, event family and identity remain confounded. The specific examples motivate a test; they do not show that changes already detect an event.

## H3: Multiple available sensors add detection value beyond the best single channel

**Observation.** `P-PDG`, `P-TPT`, `P-MON-CKP` and `T-TPT` have substantially more observed values than many other selected columns, but coverage is still incomplete and source-dependent. Correlations can reflect a common source regime, interpolation, long plateaus or the mixture of event phases. A coefficient alone does not identify a physical mechanism or establish redundant detection information.

For example, within-instance `P-PDG`/`P-TPT` Pearson correlation is defined in only two of 14 real files: the median is -0.3107, with individual values spanning -0.8812 to +0.2599. All seven simulated files have defined coefficients, but they span -0.9707 to +1.0000 despite a median of +0.9868. The two drawn files also have opposite signs. These are descriptive coefficients, not independent replicated effects. See [correlation chart](../reports/eda/04_sensor_correlations.png), [per-instance coefficients](../reports/eda/correlations_within_instance.csv) and [source summaries](../reports/eda/correlation_summary.csv). `pair_count_total` includes paired observations from constant/undefined instances; the median/range use only `valid_instance_count`, with at least 120 paired observations per defined coefficient.

**Hypothesis.** A small multi-sensor model improves event-family discrimination or false-alert control beyond the best single-sensor model on independent real groups, after accounting for coverage and correlated/redundant channels.

**Future test and controls.** Compare each eligible single-channel baseline with a small multi-channel baseline of similar complexity and equal tuning budget. Choose the best single-channel comparator using training/validation only. Add drop-one-channel ablations and a reduced correlated-channel set; choose neither by inspecting final test results. Use pairwise overlap counts and within-instance, within-origin correlations to define diagnostics, not a pooled-source correlation ranking as a final feature-selection rule. Retain identical window eligibility or report and control any coverage difference.

**Primary comparison.** Event-episode recall at a validation-fixed false-alert budget per eligible normal hour, together with family macro F1, coverage and per-well/per-event denominators. An episode must be defined from the declared label policy before running the comparison; repeated adjacent positive windows are not independent detected events.

**Falsifying outcome.** The multi-channel arm does not improve the declared detection/false-alert tradeoff over the validation-chosen single-channel arm, or its gain is explained by different retained windows rather than additional measured values. Highly correlated channels could still differ near events; lack of correlation could still be irrelevant to prediction.

**Current limit.** Pairwise-deletion correlations use different row sets; constant or absent channels have undefined correlations, not zero correlations. A large number of overlapping observations from one source file does not supply independent replication.

## H4: Explicit transient supervision improves detection during annotated transitions

**Observation.** The selected real event-2, event-5 and event-7 instances include transient codes 102, 105 and 107 without their steady codes 2, 5 and 7. The entire selected subset has no steady code 7, although 107 is present. Every selected real file begins with 3,600 unknown `class` rows. Treating these as normal, dropping transients without tracking coverage, or assigning labels from the folder would change the actual supervised question.

The EDA finds 61 within-instance label runs and 38 changes: 24 between known labels and 14 from unknown to known. There are six observed real normal-to-transient boundaries; the real event-3 and two event-4 instances instead start their known segment directly in an event label. Their first labeled row cannot establish onset time. See [transition chart](../reports/eda/07_label_transitions.png), [full-resolution within-file transitions](../reports/eda/transitions.csv) and [runs with censoring indicators](../reports/eda/label_runs.csv). No transition is inferred across file boundaries.

**Hypothesis.** Training a declared event-family classifier with documented transient rows included improves detection during annotated transitions compared with a steady-only training policy, without an unacceptable increase in normal-period false alerts.

**Future test and controls.** Compare family-label training that includes valid transients against steady-only training on the same eligible real event families and group partitions. Keep the architecture, tuning budget, feature policy and evaluation windows fixed, and control training counts/weights so a gain cannot be attributed solely to more examples. Only attempt the comparison where both training policies have adequate independent support. Report transient and steady evaluation slices separately; do not relabel an unobserved steady phase or invent an onset.

**Primary comparison.** Recall on annotated transient episodes and detection delay from an observed normal-to-transient or normal-to-event boundary, at the same validation-fixed false-alert budget. Report the number of eligible boundaries, detected episodes, missed episodes and normal hours. Do not report a mean delay only over detected episodes without the missed-event denominator. Unknown-to-event boundaries and initially abnormal files are left-censored for onset timing and are reported separately, not assigned a fabricated onset time.

**Falsifying outcome.** Including transients does not improve eligible transient detection or delay under the predeclared criterion, or improvements require a higher false-alert rate than the accepted budget. If the steady-only arm has no class support, the comparison is not estimable; it is not evidence that the transient arm wins.

**Current limit.** This is detection at/after an annotated boundary, not forecasting before an event. Label-run lengths, time until the next label and event-aligned positions are evaluation quantities and forbidden model inputs. The missing prefix and limited transition counts constrain any early-warning claim.

## H5: Synthetic augmentation must improve a real-only target evaluation

**Observation.** The acquired sources contain 14 real, seven simulated and two drawn files. Among known-labeled selected rows, real data has 125,940 normal and 146,385 abnormal observations; simulated data has 19,700 normal and 182,194 abnormal; drawn data has 8,331 normal and 49,270 abnormal. In real data, family 8 contributes 86,422 of the 146,385 abnormal rows (59.04%) from one well. The source mixture therefore changes both sensor availability and label proportions; row-level results can be dominated by a single long instance.

EDA evidence: [row balance and real-well support](../reports/eda/01_class_balance.png), [class/family counts and support](../reports/eda/class_balance.csv), [availability by instance](../reports/eda/sensor_availability.csv), and [source-specific time-series examples](../reports/eda/06_source_timeseries.png). The examples are different instances and are not matched real-versus-synthetic counterfactuals.

**Hypothesis.** Carefully limited synthetic augmentation adds useful event information to a real-trained baseline on fresh real groups, rather than improving only a mixed-source score or exploiting source-specific templates.

**Future test and controls.** Compare real-only training, real plus simulated training, and real plus simulated/drawn training while keeping real validation/test groups fixed. Use the same model family, sensor eligibility, real training examples and tuning budget. Declare augmentation weights/caps in advance and report a sensitivity analysis so the much larger abnormal synthetic fraction does not determine the decision rule by itself. Group known related synthetic generator families together; if their relationships are unknown, treat them as potentially dependent and never present their nominal file count as independent replication. Keep the final test entirely real and unexposed.

**Primary comparison.** Per-family recall and family macro F1 on real-only well groups, with group-balanced summaries, false-alert episodes per eligible real normal hour, calibration diagnostics where supported and the number of contributing wells/events. Mixed-source aggregate accuracy is not the acceptance criterion. Report an augmentation arm that harms any supported real slice even when its overall score rises.

**Falsifying outcome.** Augmentation provides no reproducible improvement under the predeclared real-only comparison criterion, worsens a protected real slice/false-alert budget, or gains vanish when availability and training class weights are controlled. If independent real groups are insufficient, the effect is not estimable.

**Current limit.** The subset is purposively size-biased, and all domains have already been inspected. It does not establish natural event prevalence, synthetic-family independence, a validated simulator-to-real transfer mechanism or an appropriate augmentation ratio.

## Recommended modeling sequence after a new approval

1. Establish a fresh, independently grouped real cohort and supported task scope under the split strategy. Reserve unexposed real well IDs for final testing before exploratory plots or tuning. At least three independent groups per desired class is a necessary condition for three partitions, not a guarantee of adequate evaluation.
2. Keep the first experiments small: a majority/context baseline and a regularized scikit-learn baseline on a declared causal sensor representation. A binary normal-versus-supported-undesirable diagnostic may precede family classification, but it must not imply reliable detection of every unseen undesirable condition. A family-classification task needs supported families in each required partition.
3. Run availability, level/change and single/multi-sensor controls before increasing model complexity. Consider XGBoost only after the baseline, data boundary and controls are sound. CatBoost, deep sequence models and learned imputation are not justified by EDA alone.
4. Tune on development groups, freeze the pipeline/class/feature/calibration/alert policy and practical comparison criterion, then evaluate the protected real test cohort once for the declared experiment. Report negative, undefined and unestimable outcomes honestly. Use group-level uncertainty when there are enough groups; do not treat 582,220 serially dependent rows as that many independent samples.

No training command, feature pipeline, fitted preprocessing object, model score, confidence threshold or claimed improvement is produced by this document. The five hypotheses require future authorization and sufficient data support before they can be tested.
