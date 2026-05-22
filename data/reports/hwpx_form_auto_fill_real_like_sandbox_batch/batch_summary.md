# HWPX Form Auto Fill Real-Like Sandbox Batch 10

- verdict: PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_SANDBOX_BATCH
- limit=1: PASS_REAL_LIKE_SANDBOX_BATCH
- limit=5: PASS_REAL_LIKE_SANDBOX_BATCH
- limit=10: PASS_REAL_LIKE_SANDBOX_BATCH
- warnings: WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY, WARN_SANDBOX_ONLY, WARN_SOME_FILES_BLOCKED, WARN_REAL_USER_FILE_NOT_TESTED, WARN_DEPLOY_NOT_PERFORMED, WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED

## Checks
- PASS A01 batch runner exists
- PASS A02 sanitized real-like sample policy enforced
- PASS A03 limit=1 supported
- PASS A04 limit=5 supported
- PASS A05 limit=10 supported
- PASS A06 SANDBOX_ONLY enforced
- PASS A07 READY_FOR_SANDBOX_WRITE only written
- PASS A08 blocked files not written
- PASS A09 blocked reasons recorded
- PASS A10 output_path == source_path absent
- PASS A11 per-file source sha256 unchanged
- PASS A12 per-file source mtime unchanged
- PASS A13 readbackFail zero required
- PASS A14 unexpectedMutation zero required
- PASS A15 sourceMutation zero required
- PASS A16 final export requires ACCEPTED_BY_USER
- PASS A17 no raw path leak
- PASS A18 no raw filename leak
- PASS A19 no PII leak
- PASS A20 AI API not called
- PASS A21 OCR not called
- PASS A22 Hancom not required
- PASS A23 previous real file preflight tests pass
- PASS A24 previous browser/API/E2E tests pass
- PASS A25 previous writer chain tests pass
- PASS A26 dirty baseline documented
