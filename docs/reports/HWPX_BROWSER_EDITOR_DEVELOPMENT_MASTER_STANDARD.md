# HWPX Browser Editor Development Master Standard

## 1. Purpose

This document defines the master development standard for the HWPX browser
editor line.

It fixes:

1. the development target
2. the execution order
3. the boundary between feature work and hardening work
4. the mandatory security floor
5. the structure for subordinate task standards

## 2. Development Target

The browser editor line includes these functional axes:

1. HWPX parse to render payload to browser viewer
2. paragraph editing
3. cell editing
4. format editing
5. save and apply linkage
6. reread and readback verification
7. browser product entry surface

## 3. Core Rules

### RULE-01. Feature First

The line must first determine whether real functions work.

That means:

- real HWPX viewer check first
- paragraph edit check before hardening
- cell edit check before hardening
- save and apply linkage check before hardening

### RULE-02. No Hardening Expansion Without Feature Confirmation

Do not keep expanding hardening tasks for a functional axis that is not yet
confirmed to work.

### RULE-03. Security Floor From Day One

The following are forbidden from the start:

- real user HWPX
- PII-containing HWPX
- production write
- source overwrite
- final deploy
- raw path or raw filename leaks

### RULE-04. Separate Feature Tasks From Hardening Tasks

Every detailed task must be classified as either:

- feature verification or implementation
- hardening, audit, or security work

Do not mix both unnecessarily in one execution unit.

### RULE-05. Hardening Starts After Functional Pass

A functional axis should move into hardening only after it reaches usable or
strong partial status.

## 4. Development Stages

### Stage 1. Functional State Confirmation

Representative detailed tasks:

- real HWPX viewer check
- real HWPX paragraph edit check
- real HWPX cell edit check
- save and apply linkage check

### Stage 2. Function Gap Classification

Representative detailed tasks:

- function gap report
- blocker report
- product entry audit

### Stage 3. Priority Decision

Representative detailed tasks:

- next function priority
- milestone ordering

### Stage 4. Hardening

Representative detailed tasks:

- readback hardening
- verify mismatch report
- UI and contract hardening
- save and apply hardening

## 5. Functional Status Labels

All browser editor tasks must classify outcomes using only:

- `USABLE`
- `PARTIAL`
- `BLOCKED`
- `SMOKE_ONLY`
- `UNCLEAR`

## 6. Safe Sample Rule

Allowed input:

- `samples/*.hwpx`
- `tests/fixtures/hwpx/*`
- synthetic, sanitized, or real-like safe samples

Forbidden input:

- real user HWPX
- PII-containing HWPX
- unknown-origin HWPX

## 7. Required Detailed Task Structure

Every subordinate task standard must define:

1. task name
2. baseline
3. purpose
4. scope
5. exclusions
6. prohibitions
7. execution or check items
8. status classification
9. completion verdict
10. completion report format

## 8. Recommended Execution Order

Recommended next detailed tasks:

1. `HWPX-BROWSER-EDITOR-REAL-HWPX-VIEWER-CHECK-24`
2. `HWPX-BROWSER-EDITOR-REAL-HWPX-PARAGRAPH-EDIT-CHECK-25`
3. `HWPX-BROWSER-EDITOR-REAL-HWPX-CELL-EDIT-CHECK-26`
4. `HWPX-BROWSER-EDITOR-SAVE-APPLY-LINKAGE-CHECK-27`
5. `HWPX-BROWSER-EDITOR-FUNCTION-GAP-REPORT-28`
6. `HWPX-BROWSER-EDITOR-NEXT-FUNCTION-PRIORITY-29`

## 9. Completion Criteria

Pass conditions:

1. feature-first rule documented
2. hardening-after-function rule documented
3. security floor documented
4. stage structure documented
5. safe sample rule documented
6. subordinate task structure documented

Final verdict target:

- `PASS_HWPX_BROWSER_EDITOR_DEVELOPMENT_MASTER_STANDARD`
