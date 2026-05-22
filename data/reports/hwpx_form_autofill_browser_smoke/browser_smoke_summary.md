# HWPX Form Autofill Browser Smoke 08

- verdict: PASS_HWPX_FORM_AUTO_FILL_WRITER_BROWSER_SMOKE
- browser smoke: PASS
- API/frontend: PASS
- E2E smoke: PASS
- writer chain: PASS
- warnings: WARN_SYNTHETIC_BROWSER_SCENARIO_ONLY, WARN_SANDBOX_ONLY, WARN_REAL_USER_FILE_NOT_TESTED, WARN_DEPLOY_NOT_PERFORMED

## Checks
- PASS A01 browser smoke test exists
- PASS A02 autofill page renders
- PASS A03 recommend section visible
- PASS A04 parser section visible
- PASS A05 autoFillReady section visible
- PASS A06 needsReview section visible
- PASS A07 missingRequired section visible
- PASS A08 requiredAttachments section visible
- PASS A09 SANDBOX_ONLY warning visible
- PASS A10 READY_FOR_WRITER enables button
- PASS A11 blocked statuses disable button
- PASS A12 write-sandbox API called on click
- PASS A13 request mode SANDBOX_ONLY
- PASS A14 sourceMutationAllowed false
- PASS A15 output_path == source_path absent
- PASS A16 success result shown correctly
- PASS A17 readback failure shown as failure
- PASS A18 source mutation shown as failure
- PASS A19 output broken shown as failure
- PASS A20 download status shown
- PASS A21 final export status shown
- PASS A22 no raw path leak
- PASS A23 no raw filename leak
- PASS A24 no PII leak
- PASS A25 AI API not called
- PASS A26 OCR not called
- PASS A27 Hancom not required
- PASS A28 previous API/frontend tests pass
- PASS A29 previous E2E smoke tests pass
- PASS A30 previous writer chain tests pass
