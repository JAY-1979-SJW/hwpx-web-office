# HWPX-BACKEND-READ-WRITE-EDIT-VERIFICATION-BASELINE-38

## 1. Purpose

This baseline fixes the commercial-grade verification scope for backend HWPX
read / write / edit capability.

This step does not add frontend wiring or deploy behavior. It fixes what must
be verified, how it is verified, and how PASS/FAIL is decided.

## 2. Scope

Included:

- HWPX read correctness
- Paragraph edit correctness
- Cell edit correctness
- Output write correctness
- Source immutability
- Verify/readback consistency
- Package reopen integrity
- Failure safety

Excluded:

- Frontend UI verification
- Browser save/apply wiring
- Production deployment

## 3. Required Verification Scenarios

### SCENARIO-G01. Read Baseline

- Open a safe HWPX sample
- Confirm paragraph / table / cell counts
- Confirm representative visible text samples

### SCENARIO-G02. Paragraph Replace

- Apply one paragraph replace edit
- Confirm `outputCreated`
- Confirm `sourceUnchanged`
- Confirm readback PASS
- Confirm verify PASS

### SCENARIO-G03. Cell Replace

- Apply one cell text edit
- Confirm `outputCreated`
- Confirm `sourceUnchanged`
- Confirm readback PASS
- Confirm verify PASS

### SCENARIO-G04. Multi-Cell Write

- Apply two or more cell edits
- Confirm coordinate accuracy
- Confirm no cross-leak

### SCENARIO-G05. Input Validation

- Reject wrong source hash
- Reject expected-before mismatch
- Reject invalid target
- Reject output equals source

### SCENARIO-G06. Failure Safety

- Block writer execution when dry-run applied count is zero
- Never upgrade failed verification to PASS
- Never treat broken output as success

### SCENARIO-G07. Reopen Integrity

- Reopen output HWPX successfully
- Confirm reread target values
- Confirm no package breakage in verified scope

### SCENARIO-G08. Verification Consistency

- Summary verdict must agree with detail/readback verdicts
- No PASS/FAIL mismatch is allowed in final baseline verdict

## 4. Script Topology

### SCRIPT-01

`scripts/ops/verify_hwpx_backend_paragraph_edit.py`

Responsibility:

- Paragraph read/write/edit verification
- Paragraph readback/verify consistency verification

### SCRIPT-02

`scripts/ops/verify_hwpx_backend_cell_edit.py`

Responsibility:

- Cell read/write/edit verification
- Cell coordinate/text/header verification
- Cell readback/verify verification

### SCRIPT-03

`scripts/ops/verify_hwpx_backend_rwedit_baseline.py`

Responsibility:

- Execute paragraph verification
- Execute cell verification
- Aggregate common PASS/FAIL state
- Emit final baseline verdict

## 5. Script Management Rules

- Paragraph, cell, and integration responsibilities stay separate
- The integration runner emits the final baseline verdict
- Only safe fixtures or sanitized samples are allowed
- Output must stay under tmp or approved sandbox scope
- Real user HWPX inputs are forbidden

## 6. PASS Criteria

The integrated baseline is PASS only if all of the following are true:

- Read baseline PASS
- Paragraph edit PASS
- Cell edit PASS
- `outputCreated == true`
- `sourceUnchanged == true`
- Readback PASS
- Verify PASS
- Reopen integrity PASS
- Failure safety PASS
- Consistency PASS

Final verdict name:

`PASS_HWPX_BACKEND_READ_WRITE_EDIT_VERIFICATION_BASELINE`

## 7. Implementation Order

1. Create `verify_hwpx_backend_paragraph_edit.py`
2. Create `verify_hwpx_backend_cell_edit.py`
3. Create `verify_hwpx_backend_rwedit_baseline.py`
4. Run integrated baseline and report final verdict

## 8. Expected Reporting

Each run should report at minimum:

- Scenario set executed
- Script verdicts
- Output creation status
- Source immutability status
- Readback/verify summary
- Final baseline verdict
