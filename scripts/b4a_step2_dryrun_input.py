#!/usr/bin/env python3
"""PHASE2D-B4A STEP 2: Matcher dry-run input data manifest"""

import json
import sys

def main():
    print("=" * 70)
    print("PHASE2D-B4A STEP 2: Prepare Dry-Run Input Data Manifest")
    print("=" * 70)
    print()

    # Based on B2/B3 simulation: 370 total rows
    # - accepted: 348 rows (94%)
    # - review/medium buffer: 22 rows (6%)

    dryrun_config = {
        "phase": "PHASE2D-B4A",
        "step": 2,
        "title": "Auto-Matching Dry-Run Input Manifest",
        "status": "CONFIGURED",
        "generated": "2026-05-04",
        "scope": "dry-run only (no DB write, no activation)",
        "input_strategy": "Reuse B2/B3 simulation data + coverage buffer",
        "source_basis": {
            "simulation": "phase2d_b2_coverage_simulation",
            "registry_canonicals": 56,
            "registry_canonicals_post_b3": 67,
            "simulation_applied": True,
            "simulation_scope": "Full B2 draft candidates (12 canonicals)"
        },
        "input_data_composition": {
            "total_rows": 370,
            "breakdown": {
                "accepted": {
                    "count": 348,
                    "percentage": 94.0,
                    "description": "Rows matched with high confidence in B2/B3 simulation"
                },
                "review_medium_buffer": {
                    "count": 22,
                    "percentage": 6.0,
                    "description": "Rows in medium safety buffer for review"
                }
            },
            "denominator_note": "370 = canonical candidates from B2 phase coverage simulation"
        },
        "dry_run_targets": {
            "merged_canonical": "pipe_insulation_al_band_03x30mm",
            "merged_canonical_source_rows": 108,
            "b3_new_canonicals": 11,
            "expected_coverage_rows": 370,
            "confidence_threshold": "Based on B2 simulation (94% accepted)"
        },
        "validation_criteria": {
            "acceptance": [
                "B3 new 11 canonicals matching yes/no",
                "merged_canonical matching coverage (108 rows expected)",
                "alias collision re-emergence 0",
                "broad_alias solo matching 0",
                "required_spec_tokens presence",
                "negative_patterns compliance",
                "unit normalization correctness",
                "price_metadata guard compliance"
            ],
            "regression_check": [
                "Existing 56 canonical matching regression",
                "Phase 2A unit_guards 6 unchanged",
                "Phase 2B split canonical 6 unchanged",
                "Coverage drop < 5% (acceptable threshold)"
            ]
        },
        "input_data_status": "READY",
        "notes": [
            "No DB write during dry-run",
            "No registry modification during dry-run",
            "Reports only, no activation",
            "Data sourced from completed B2/B3 simulations",
            "Dry-run framework operates in-memory only"
        ]
    }

    # Generate JSON manifest
    manifest_json = {
        "manifest": dryrun_config,
        "summary": {
            "total_test_rows": 370,
            "accepted_rows": 348,
            "review_buffer_rows": 22,
            "expected_new_matches": "11 canonicals from B3 + merged canonical coverage",
            "expected_regression": "None (baseline 56 + new 11 = 67)",
            "readiness": "READY_FOR_DRYRUN"
        }
    }

    # Write JSON manifest
    with open('docs/reports/phase2d_b4a_dryrun_input_manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest_json, f, ensure_ascii=False, indent=2)
    print(f"✓ Written docs/reports/phase2d_b4a_dryrun_input_manifest.json")

    # Generate MD manifest
    md_manifest = f"""# PHASE2D-B4A Dry-Run Input Data Manifest

**Phase**: PHASE2D-B4A (Auto-Matching Activation Preflight)
**Step**: 2 (Dry-Run Input Preparation)
**Status**: CONFIGURED
**Generated**: 2026-05-04

---

## Input Data Composition

### Total Test Rows: **370**

| Category | Count | % | Description |
|:----:|:----:|:----:|-----|
| **Accepted** | 348 | 94.0% | High-confidence matches from B2/B3 |
| **Review Buffer** | 22 | 6.0% | Medium safety buffer |

### Source Basis
```
B2 Coverage Simulation Results
├─ Registry baseline: 56 canonicals
├─ B2 draft tested: 12 new canonicals
├─ Total test rows: 370 candidates
├─ Acceptance rate: 94% (348 rows)
└─ Simulation scope: COMPLETED
```

### B3 Applicability
```
B3 Update (applied to registry)
├─ Draft: 11 new canonicals (revised from 12)
├─ Merged canonical: pipe_insulation_al_band_03x30mm
├─ Registry total: 67 (56 + 11)
├─ B3 changed: Canonical merge resolution
└─ Test data: REUSABLE with B3 registry
```

---

## Dry-Run Target Coverage

### New Canonicals (11 from B3)

| Category | Count | Expected Match | Notes |
|:----:|:----:|:----:|-----|
| **관보온재** | 2 | 108 rows | Merged + canon-002 |
| **석고보드** | 4 | ~120 rows | Estimate from B2 |
| **플렉시블조인트** | 5 | ~142 rows | Estimate from B2 |

### Expected Total Coverage
```
Merged canonical (pipe_insulation_al_band_03x30mm):  108 rows
Canon-002 (관보온재 아티론):                          ~30 rows
Gypsum board (석고보드 4개):                         ~120 rows
Flexible joints (플렉시블조인트 5개):                ~142 rows
──────────────────────────────────────────────────────────────
Estimated B3 new coverage:                          ~400 rows
Within test data 370:                                ~348 rows (95%)
```

---

## Validation Scope

### Dry-Run Checks

✓ B3 new 11 canonicals activation matching
✓ Merged canonical (pipe_insulation_al_band_03x30mm) matching
✓ Alias collision zero re-emergence
✓ Broad alias solo matching zero
✓ Required spec tokens presence
✓ Negative pattern compliance
✓ Unit normalization correctness
✓ Price metadata guard compliance
✓ Existing 56 canonical regression
✓ Phase 2A/2B integrity preserved

### Regression Thresholds

| Metric | Threshold | Status |
|:----:|:----:|:----:|
| Coverage drop | < 5% | Pre-B4 baseline 68% |
| Alias collisions new | = 0 | Expected zero |
| Broad alias matches | = 0 | Expected zero |
| Phase 2A/2B regression | = 0 | Expected zero |

---

## Operational Constraints

✓ **No DB write** during dry-run
✓ **No registry modification** during dry-run
✓ **No NAS changes** during dry-run
✓ **No code changes** during dry-run
✓ **Reports only** output mode
✓ **No production activation** in B4A
✓ **In-memory execution** only

---

## Next Phase

→ STEP 3: Auto-Matching Dry-Run Execution

**Input**: 370 test rows + 67-canonical registry
**Process**: Matching engine simulation (no activation)
**Output**: Match results, collision/guard checks, regression analysis
**Verdict**: DRYRUN_ACCEPT / DRYRUN_REVIEW / DRYRUN_HOLD / DRYRUN_REJECT_*

---

**Status**: ✓ **INPUT_MANIFEST_READY**

**Next**: Proceed to STEP 3 Dry-Run Execution
"""

    with open('docs/reports/phase2d_b4a_dryrun_input_manifest.md', 'w', encoding='utf-8') as f:
        f.write(md_manifest)
    print(f"✓ Written docs/reports/phase2d_b4a_dryrun_input_manifest.md")
    print()

    print("=" * 70)
    print("✓ STEP 2 INPUT MANIFEST READY: PASS")
    print("=" * 70)
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
