# HWPX Document Engine Boundary

- Date: 2026-05-15
- Scope: P3 HWPX document automation engine boundary

## Purpose

This document locks where HWPX package editing, XML editing, template rendering, schedule/safety document generation, validation, and local HWP/Hancom conversion boundaries belong. P3 does not add large HWPX features; it fixes structural ownership and audit gates.

## HWPX Package Layer

Allowed responsibilities:

- ZIP read/write
- HWPX manifest handling
- metadata handling
- section XML discovery
- preview, bindata, media inventory
- package-level read-only inspection

Current path signals:

- `scripts/hwpx/hwpx_package.py`
- `scripts/hwpx/hwpx_package_inspector.py`
- `scripts/hwpx/hwpx_manifest_ops.py`
- `scripts/hwpx/hwpx_metadata_ops.py`
- `scripts/hwpx/hwp_full_fidelity_package.py`

## HWPX XML Edit Layer

Allowed responsibilities:

- paragraph editing
- table/cell/row editing
- style and border/fill operations
- image and chart insertion policy
- section update helpers

Current path signals:

- `scripts/hwpx/hwpx_table_cell_address_style.py`
- `scripts/hwpx/hwpx_style_ops.py`
- `scripts/hwpx/hwpx_list_style_ops.py`
- `scripts/hwpx/hwpx_image_ops.py`
- `scripts/hwpx/hwpx_image_policy.py`
- `scripts/hwpx/hwpx_chart_png.py`
- `scripts/hwpx/hwp_full_fidelity_section_updates.py`

## HWPX Template Layer

Allowed responsibilities:

- placeholder resolution
- template rendering
- safety document builder
- schedule builder
- report builder
- compose/generate job orchestration

Current path signals:

- `scripts/hwpx/hwpx_template_engine.py`
- `scripts/hwpx/hwpx_template_render.py`
- `scripts/hwpx/hwpx_document_builder.py`
- `scripts/hwpx/hwpx_composer.py`
- `scripts/hwpx/hwpx_schedule_diagrams.py`
- `scripts/hwpx/hwpx_compose_schema_reference.py`

## HWPX Validation Layer

Allowed responsibilities:

- package validation
- XML parse validation
- roundtrip validation
- golden validation
- delivery verification

Current path signals:

- `scripts/hwpx/hwpx_validation.py`
- `scripts/hwpx/hwpx_delivery_auto_verify.py`
- `scripts/hwpx/hwpx_compose_regression.py`
- `scripts/hwpx/hwpx_api_smoke.py`
- `scripts/hwpx/*audit*.py`
- `scripts/hwpx/test_*.py`

## Adapter Boundary

Allowed responsibilities:

- filesystem adapter
- Java/Python bridge
- local Hancom/HWP converter adapter
- external converter provider adapter

Rules:

- Native `.hwp` conversion is `LOCAL_WORKER_REQUIRED`.
- Hancom/HWP GUI automation must not run as an unguarded server action.
- Java HTTP handlers may route to a conversion adapter, but must not own desktop automation details.
- Server-side HWPX XML/ZIP editing is allowed when it does not require Hancom, browser automation, login, certificate, OTP, password, bid, payment, transfer, or submission.

## Forbidden Coupling

- HWPX engine must not directly call Excel parser internals.
- Excel engine must not directly call HWPX internal XML writer.
- HWP/Hancom conversion must not run directly from server runtime without a local worker gate.
- HWPX package editor must not directly couple to `scripts/local-gui`.
- API handlers must not contain detailed HWPX XML manipulation logic.
- HWPX runtime changes require focused tests.

## P3 Lock Result

- HWPX cycle audit is required before closeout.
- HWPX/HWP/local worker gate warnings remain visible until P4 usecase wiring.
- Upload/package validation warnings are tracked but not all fixed in P3.
