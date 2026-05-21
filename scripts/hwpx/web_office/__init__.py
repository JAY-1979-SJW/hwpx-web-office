"""HWPX Web Office Editor — Phase 1 RO-VIEW.

설계서: docs/architecture/hwpx_web_office_editor_deep_architecture.md
공정: WEB-OFFICE-RO-VIEW-MVP-01

본 패키지는 read-only viewer 만 제공한다. writer 호출, output HWPX
생성, edit command 생성은 금지된다 (Phase 2 이상에서만 도입).
"""
SCHEMA_VERSION = "web-office-doc-1.0"
ENGINE_VERSION = "ro-view-mvp-01"
