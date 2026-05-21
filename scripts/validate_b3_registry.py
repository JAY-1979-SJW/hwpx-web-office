#!/usr/bin/env python3
"""PHASE2D-B3-RETRY STEP 6: Validate 67-canonical registry and merged canonical"""

import json
import sys

def main():
    # Load registry
    registry_path = "./services/price-classifier/tests/fixtures/alias_registry_seed.json"
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load registry: {e}")
        return False

    print(f"Registry loaded: {len(registry)} canonicals\n")

    # 1. Count check
    if len(registry) != 67:
        print(f"FAIL: Expected 67 canonicals, got {len(registry)}")
        return False
    print(f"✓ Total canonicals: 67")

    # 2. Merged canonical check
    merged_found = False
    merged_c = None
    for c in registry:
        if c.get('canonical_item_id') == 'pipe_insulation_al_band_03x30mm':
            merged_found = True
            merged_c = c
            break

    if not merged_found:
        print("FAIL: Merged canonical not found")
        return False

    print(f"✓ Merged canonical found: {merged_c.get('canonical_name')}")
    print(f"  Unit: {merged_c.get('standard_unit')}")
    print(f"  Category: {merged_c.get('category_large')}")

    # 3. Alias collision check
    alias_map = {}
    collisions = []
    for c in registry:
        for alias in c.get('aliases', []):
            if alias in alias_map:
                collisions.append({
                    'alias': alias,
                    'canonical1': alias_map[alias],
                    'canonical2': c['canonical_item_id']
                })
            else:
                alias_map[alias] = c['canonical_item_id']

    if collisions:
        print(f"FAIL: {len(collisions)} alias collision(s) detected:")
        for col in collisions:
            print(f"  '{col['alias']}' in both {col['canonical1']} and {col['canonical2']}")
        return False
    print(f"✓ Alias collisions: 0")

    # 4. Duplicate key check
    ids = [c['canonical_item_id'] for c in registry]
    dup_ids = [id for id in set(ids) if ids.count(id) > 1]
    if dup_ids:
        print(f"FAIL: Duplicate keys: {dup_ids}")
        return False
    print(f"✓ Duplicate keys: 0")

    # 5. Category distribution (using category_middle for Korean names)
    categories = {}
    for c in registry:
        cat = c.get('category_middle', 'unknown')
        categories[cat] = categories.get(cat, 0) + 1

    expected = {'관보온재': 2, '석고보드': 4, '플렉시블조인트': 5}
    for cat, count in expected.items():
        if categories.get(cat, 0) < count:
            print(f"FAIL: Category '{cat}' has {categories.get(cat, 0)}, expected at least {count}")
            return False

    print(f"✓ Category distribution (Korean): {expected}")
    print(f"  Full registry categories: {dict(sorted(categories.items()))}")

    # 6. Merged canonical metadata
    notes = merged_c.get('notes', {})
    price_buckets = notes.get('price_buckets', {})

    if 'price_buckets' not in notes:
        print("WARN: No price_buckets metadata in merged canonical")
    else:
        print(f"✓ Price buckets metadata:")
        for bucket_name, bucket_info in price_buckets.items():
            if isinstance(bucket_info, dict) and 'rows' in bucket_info:
                print(f"  {bucket_name}: {bucket_info.get('rows')} rows")

    # 7. Validate Phase 2A/2B integrity (12 existing canonicals)
    phase_2ab_items = [
        'structural_carbon_steel_pipe',
        'flange',
        'eps_insulation_board',
        'pipe_shoe',
        'gate_valve',
        'check_valve',
        'cable_tray_linear',
        'cable_tray_piece',
        'steel_plate_weight',
        'steel_plate_piece',
        'wire_connector_kit',
        'wire_connector_piece'
    ]

    missing = []
    for item_id in phase_2ab_items:
        if not any(c['canonical_item_id'] == item_id for c in registry):
            missing.append(item_id)

    if missing:
        print(f"FAIL: Missing Phase 2A/2B items: {missing}")
        return False
    print(f"✓ Phase 2A/2B integrity: 12/12 items present")

    print("\n" + "="*60)
    print("✓ STEP 6 VALIDATION COMPLETE - ALL CHECKS PASSED")
    print("="*60)
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
