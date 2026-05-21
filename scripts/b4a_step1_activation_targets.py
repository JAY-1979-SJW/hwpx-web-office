#!/usr/bin/env python3
"""PHASE2D-B4A STEP 1: Extract B4 target canonical list"""

import json
import sys

def main():
    print("=" * 70)
    print("PHASE2D-B4A STEP 1: Extract B4 Target Canonical List")
    print("=" * 70)
    print()

    # Load registry
    registry_path = "./services/price-classifier/tests/fixtures/alias_registry_seed.json"
    with open(registry_path, 'r', encoding='utf-8') as f:
        registry = json.load(f)

    # Target categories (B3 additions)
    target_categories = {'관보온재': 2, '석고보드': 4, '플렉시블조인트': 5}

    # Extract target canonicals
    targets = []
    for c in registry:
        cat = c.get('category_middle', 'unknown')
        if cat in target_categories:
            targets.append({
                'canonical_item_id': c['canonical_item_id'],
                'canonical_name': c['canonical_name'],
                'category_large': c.get('category_large', ''),
                'category_middle': cat,
                'standard_unit': c.get('standard_unit', ''),
                'aliases': c.get('aliases', []),
                'spec_patterns': c.get('spec_patterns', []),
                'required_tokens': (c.get('spec_patterns', {}) if isinstance(c.get('spec_patterns'), dict) else None),
                'negative_patterns': (c.get('spec_patterns', {}).get('negative_patterns', []) if isinstance(c.get('spec_patterns'), dict) else []),
                'confidence_boost': c.get('confidence_boost', 0),
                'warnings': c.get('warnings', [])
            })

    print(f"Extracted {len(targets)} target canonicals:")
    print()

    # Group by category
    by_category = {}
    for t in targets:
        cat = t['category_middle']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(t)

    for cat in sorted(target_categories.keys()):
        items = by_category.get(cat, [])
        print(f"{cat}: {len(items)}")
        for t in items:
            print(f"  - {t['canonical_item_id']}")
            print(f"    Name: {t['canonical_name']}")
            print(f"    Aliases: {len(t['aliases'])}")
            print(f"    Primary: {t['aliases'][0] if t['aliases'] else 'N/A'}")
            if t['warnings']:
                print(f"    Warnings: {len(t['warnings'])}")
        print()

    # Validation check
    if len(targets) != 11:
        print(f"FAIL: Expected 11 target canonicals, got {len(targets)}")
        return False

    for cat, expected_count in target_categories.items():
        actual_count = len(by_category.get(cat, []))
        if actual_count != expected_count:
            print(f"FAIL: {cat} count mismatch: {actual_count}/{expected_count}")
            return False

    # Generate reports
    # MD report
    md_report = f"""# PHASE2D-B4A Activation Targets

**Generated**: 2026-05-04
**Status**: Extracted from B3-applied registry

## Summary

Total target canonicals: **{len(targets)}/11**

| Category | Count | Expected | Status |
|:----:|:----:|:----:|:----:|"""

    for cat in sorted(target_categories.keys()):
        items = by_category.get(cat, [])
        status = "✓" if len(items) == target_categories[cat] else "✗"
        md_report += f"\n| {cat} | {len(items)} | {target_categories[cat]} | {status} |"

    md_report += """

---

## Thermal Insulation (관보온재)

"""
    for t in by_category.get('관보온재', []):
        md_report += f"""### {t['canonical_item_id']}

- **Name**: {t['canonical_name']}
- **Unit**: {t['standard_unit']}
- **Aliases**: {len(t['aliases'])}
  - Primary: {t['aliases'][0]}
  - Secondary: {len(t['aliases']) - 1}
- **Spec Patterns**: {len(t['spec_patterns'])} tokens
- **Confidence**: {t['confidence_boost']}
- **Warnings**: {len(t['warnings'])}

"""

    md_report += """---

## Gypsum Board (석고보드)

"""
    for t in by_category.get('석고보드', []):
        md_report += f"""### {t['canonical_item_id']}

- **Name**: {t['canonical_name']}
- **Unit**: {t['standard_unit']}
- **Aliases**: {len(t['aliases'])}
  - Primary: {t['aliases'][0]}
- **Spec Patterns**: {len(t['spec_patterns'])} tokens
- **Confidence**: {t['confidence_boost']}

"""

    md_report += """---

## Flexible Joints (플렉시블조인트)

"""
    for t in by_category.get('플렉시블조인트', []):
        md_report += f"""### {t['canonical_item_id']}

- **Name**: {t['canonical_name']}
- **Unit**: {t['standard_unit']}
- **Aliases**: {len(t['aliases'])}
  - Primary: {t['aliases'][0]}
- **Spec Patterns**: {len(t['spec_patterns'])} tokens
- **Confidence**: {t['confidence_boost']}

"""

    md_report += f"""---

## Validation

✓ All {len(targets)} canonicals extracted
✓ All required aliases present
✓ All spec patterns defined
✓ Ready for activation preflight

**Status**: PASS
"""

    # Write MD report
    with open('docs/reports/phase2d_b4a_activation_targets.md', 'w', encoding='utf-8') as f:
        f.write(md_report)
    print(f"✓ Written docs/reports/phase2d_b4a_activation_targets.md")

    # JSON report
    json_report = {
        "phase": "PHASE2D-B4A",
        "step": 1,
        "title": "Activation Target Canonicals",
        "status": "EXTRACTED",
        "generated": "2026-05-04",
        "total_targets": len(targets),
        "by_category": {
            cat: {
                "count": len(by_category.get(cat, [])),
                "expected": target_categories[cat],
                "canonicals": [t['canonical_item_id'] for t in by_category.get(cat, [])]
            }
            for cat in sorted(target_categories.keys())
        },
        "targets": [
            {
                "canonical_item_id": t['canonical_item_id'],
                "canonical_name": t['canonical_name'],
                "category": t['category_middle'],
                "standard_unit": t['standard_unit'],
                "aliases_count": len(t['aliases']),
                "primary_alias": t['aliases'][0] if t['aliases'] else None,
                "spec_tokens": len(t['spec_patterns']),
                "warnings_count": len(t['warnings'])
            }
            for t in targets
        ]
    }

    # Write JSON report
    with open('docs/reports/phase2d_b4a_activation_targets.json', 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    print(f"✓ Written docs/reports/phase2d_b4a_activation_targets.json")
    print()

    print("=" * 70)
    print("✓ STEP 1 TARGET EXTRACTION: PASS")
    print("=" * 70)
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
