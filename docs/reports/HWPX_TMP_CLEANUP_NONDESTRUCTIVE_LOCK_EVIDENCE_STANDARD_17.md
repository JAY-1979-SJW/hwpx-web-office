# HWPX Tmp Cleanup Nondestructive Lock Evidence Standard 17

## 1. Current Baseline

- Current HEAD: `397f5a7`
- Previous task: `HWPX-TMP-CLEANUP-TERMINATION-EVIDENCE-CHECK-16`
- Previous verdict: `PASS_HWPX_TMP_CLEANUP_TERMINATION_EVIDENCE_CHECK`

Current evidence state:

- `PROCESS_LOCK_WEAK`
- `SYNC_LOCK_WEAK_TO_MEDIUM_CANDIDATE`
- `PERMISSION_WEAK`
- `EVIDENCE_INSUFFICIENT_FOR_TERMINATION`

Current hold:

- `tmp/`
- `docs/devlog/*.md`

Current tmp top-level:

- `hook_runtime`
- `hook_smoke`
- `hook_smoke_contract`
- `hook_smoke_drift`
- `hook_smoke_new_file`

## 2. Purpose

This standard defines what nondestructive lock evidence may be collected before
any process termination or cleanup retry is considered.

This task does not authorize:

- process termination
- tmp cleanup retry
- file deletion
- sync interruption
- permission changes

## 3. Nondestructive Observation Scope

Allowed observation categories:

1. tmp artifact last-write timestamps
2. python process start-time cohorts
3. artifact-to-process time proximity
4. repeated observation consistency
5. stable hold pattern checks
6. access-denied pattern consistency

## 4. Observation Rules

### 4-1. Timestamp Proximity Rule

Compare:

- tmp artifact last-write times
- python process start times

Interpretation:

- close time proximity may strengthen the process-lock hypothesis
- weak or inconsistent proximity keeps process-lock at weak evidence

### 4-2. Process Cohort Stability Rule

Observe whether the same python process cohorts remain visible across repeated
checks.

Interpretation:

- stable cohorts increase long-lived lock suspicion
- unstable cohorts weaken any direct process attribution

### 4-3. Artifact Cohort Stability Rule

Observe whether tmp artifacts remain unchanged across repeated checks.

Interpretation:

- unchanged artifact cohorts suggest residual lock or sync residue
- changing cohorts imply the area is still active and not ready for retry

### 4-4. Repeated Observation Pattern Rule

Repeat observation without destructive action and compare:

- process cohorts
- artifact cohorts
- hold state
- access-denied consistency

Interpretation:

- repeated consistency may strengthen weak evidence toward medium
- inconsistent results keep the evidence weak

## 5. Process-Lock Evidence Strengthening

Process-lock evidence may be strengthened when multiple nondestructive signals
align:

1. close timestamp proximity between artifact and process cohorts
2. repeated visibility of the same process cohorts
3. stable tmp artifact set
4. repeated access-denied behavior without scope drift

Absent these conditions, process-lock remains weak.

## 6. Sync-Lock Evidence Strengthening

Sync-lock evidence may be strengthened when:

1. the workspace remains under OneDrive
2. access-denied behavior persists independently of process cohort changes
3. artifact cohorts remain unchanged while the lock symptom remains

Without those signals, sync-lock remains weak or weak-to-medium candidate only.

## 7. Permission Evidence Rule

Permission evidence remains weak unless direct nondestructive signs appear, such
as stable attribute or access patterns that fit permission failure better than
process-lock or sync-lock.

Current assumption:

- permission is weaker than process-lock and sync-lock

## 8. Evidence Deficiency Rule

Evidence remains insufficient when:

- process existence is observed without direct linkage
- artifact cohorts do not isolate a specific locking source
- repeated observations do not materially narrow the hypothesis

In that state:

- no termination candidate may be proposed
- no cleanup retry may be justified from evidence alone

## 9. Next-Step Routing Rule

After nondestructive observation, the result should be routed as one of:

1. `PROCESS_LOCK_EVIDENCE_STRENGTHENED`
2. `SYNC_LOCK_EVIDENCE_STRENGTHENED`
3. `STILL_INSUFFICIENT_EVIDENCE`

That routing determines whether the next task should be:

- another evidence check
- sync-focused triage
- termination approval candidate review

## 10. Security Rule

The standard must remain PII-safe.

Forbidden in reports:

- raw path disclosure
- raw filename disclosure outside approved safe identifiers
- PII patterns

## 11. Completion Criteria

Pass conditions:

1. nondestructive observation scope defined
2. timestamp proximity rule defined
3. process cohort stability rule defined
4. artifact cohort stability rule defined
5. repeated observation pattern rule defined
6. process-lock and sync-lock strengthening criteria defined
7. no destructive action performed
8. no PII, raw path, or raw filename leak

Final verdict target:

- `PASS_HWPX_TMP_CLEANUP_NONDESTRUCTIVE_LOCK_EVIDENCE_STANDARD`
