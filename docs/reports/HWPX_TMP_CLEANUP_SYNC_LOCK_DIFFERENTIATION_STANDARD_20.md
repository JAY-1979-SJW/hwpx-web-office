# HWPX Tmp Cleanup Sync Lock Differentiation Standard 20

## 1. Current Baseline

- Current HEAD: `7e9d2e7`
- Previous task: `HWPX-TMP-CLEANUP-REPEATED-OBSERVATION-CHECK-19`
- Previous verdict: `PASS_HWPX_TMP_CLEANUP_REPEATED_OBSERVATION_CHECK`

Current evidence state:

- `PROCESS_LOCK_MEDIUM_CANDIDATE`
- `SYNC_LOCK_WEAK_TO_MEDIUM_CANDIDATE`
- `PERMISSION_WEAK`
- repeated observation: `PARTIAL_DRIFT`

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

This standard defines how to differentiate process-lock signals from sync-lock
signals without destructive action.

This task does not authorize:

- sync interruption
- process termination
- tmp cleanup retry
- file deletion
- permission changes

## 3. Process-Lock Leaning Signals

Signals that strengthen the process-lock explanation:

1. tmp artifact cohorts closely align with python process start-time cohorts
2. repeated observation preserves the same core process cohorts
3. tmp artifact sets remain stable while process cohorts remain relevant
4. multiple artifacts cluster around the same process cohort window

Current interpretation:

- process-lock remains the primary working hypothesis

## 4. Sync-Lock Leaning Signals

Signals that strengthen the sync-lock explanation:

1. the workspace remains under OneDrive-managed storage
2. lock symptoms persist even when process cohorts drift
3. artifact sets appear fully stable while access-denied symptoms still persist
4. multiple directories or files share the same refusal pattern without a clear
   single process explanation

Current interpretation:

- sync-lock remains a secondary candidate, not the primary hypothesis

## 5. Mixed-Evidence State Rule

The state is mixed evidence when:

1. process-lock has meaningful time-cohort support
2. sync-lock has contextual support from environment and persistence
3. no direct lock-holder evidence exists

Current state fits mixed evidence, with process-lock still leading.

## 6. OneDrive Factor Rule

The OneDrive path characteristic is interpreted as:

1. a valid background supporting factor for sync-lock
2. not strong evidence by itself
3. insufficient to overrule process-lock proximity evidence

Current interpretation:

- OneDrive is a background support factor, not a decisive factor

## 7. Process-vs-Sync Comparison Rule

Use the following comparison logic:

- if timestamp proximity and cohort stability dominate, process-lock leans
  stronger
- if lock symptoms persist independently of process cohort changes, sync-lock
  gains weight
- if both remain plausible without direct proof, keep the state mixed

Current comparison result:

- `PROCESS_LOCK_STILL_PRIMARY`
- `SYNC_LOCK_BACKGROUND_SUPPORT`
- `MIXED_EVIDENCE_NOT_RESOLVED`

## 8. Sync-Focused Observation Rule

Future sync-focused nondestructive observation may compare:

1. whether lock symptoms persist while process cohorts change
2. whether artifact sets remain frozen across repeated checks
3. whether sync explanation becomes simpler than process explanation over time

These observations may strengthen sync-lock, but they do not do so yet.

## 9. Escalation Rule

Do not escalate to:

- sync interruption
- process termination
- cleanup retry

unless evidence materially improves beyond the current mixed state.

## 10. Security Rule

Reports must remain PII-safe.

Forbidden:

- raw path disclosure
- raw filename disclosure outside approved safe identifiers
- PII patterns

## 11. Completion Criteria

Pass conditions:

1. process-lock leaning signals defined
2. sync-lock leaning signals defined
3. mixed-evidence state defined
4. OneDrive factor interpretation defined
5. sync-focused observation criteria defined
6. no destructive action performed
7. no PII, raw path, or raw filename leak

Final verdict target:

- `PASS_HWPX_TMP_CLEANUP_SYNC_LOCK_DIFFERENTIATION_STANDARD`
