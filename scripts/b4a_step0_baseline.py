#!/usr/bin/env python3
"""PHASE2D-B4A STEP 0: B3 Baseline Verification"""

import json
import sys

def main():
    print("=" * 70)
    print("PHASE2D-B4A STEP 0: B3 Baseline Verification")
    print("=" * 70)
    print()

    # Load registry
    registry_path = "./services/price-classifier/tests/fixtures/alias_registry_seed.json"
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
    except Exception as e:
        print(f"FAIL: Cannot load registry: {e}")
        return False

    print(f"✓ Registry loaded from {registry_path}")
    print()

    # 1. Canonical count
    canonical_count = len(registry)
    expected = 67
    print(f"Canonical count: {canonical_count}")
    if canonical_count != expected:
        print(f"FAIL: Expected {expected}, got {canonical_count}")
        return False
    print(f"✓ Count matches expected: {expected}")
    print()

    # 2. Alias collision check
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

    print(f"Alias collisions: {len(collisions)}")
    if collisions:
        print("FAIL: Alias collisions detected:")
        for col in collisions:
            print(f"  '{col['alias']}' in {col['canonical1']} and {col['canonical2']}")
        return False
    print(f"✓ Zero alias collisions")
    print()

    # 3. Broad alias check (new broad aliases from B3)
    # Expected pre-existing: pipe_insulation_material, gypsum_board, flexible_joint
    broad_aliases_preexist = {
        'pipe_insulation_material': 'pipe_insulation',
        'gypsum_board': 'gypsum',
        'flexible_joint': 'joint'
    }

    new_broad_aliases = []
    for c in registry:
        aliases = c.get('aliases', [])
        for alias in aliases:
            # Check if any alias is very broad (single word or generic term)
            if len(alias.split()) == 1 and not any(
                preexist in c['canonical_item_id'] for preexist in broad_aliases_preexist.keys()
            ):
                # Single-word alias that's not from pre-existing broad aliases
                if c.get('category_middle') in ['관보온재', '석고보드', '플렉시블조인트']:
                    # Only check new B3 categories
                    new_broad_aliases.append({
                        'alias': alias,
                        'canonical': c['canonical_item_id']
                    })

    print(f"New broad aliases (from B3 canonicals): {len(new_broad_aliases)}")
    if new_broad_aliases:
        print("WARN: New broad aliases found:")
        for ba in new_broad_aliases:
            print(f"  '{ba['alias']}' in {ba['canonical']}")
    else:
        print(f"✓ Zero new broad aliases")
    print()

    # 4. Phase 2A/2B integrity check (12 items must be present)
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

    missing_items = []
    for item_id in phase_2ab_items:
        if not any(c['canonical_item_id'] == item_id for c in registry):
            missing_items.append(item_id)

    print(f"Phase 2A/2B items: {len(phase_2ab_items) - len(missing_items)}/{len(phase_2ab_items)}")
    if missing_items:
        print(f"FAIL: Missing Phase 2A/2B items: {missing_items}")
        return False
    print(f"✓ All Phase 2A/2B items present and intact")
    print()

    # 5. B3 new canonicals (11 expected)
    b3_categories = {'관보온재': 2, '석고보드': 4, '플렉시블조인트': 5}
    b3_canonicals_by_cat = {}
    for c in registry:
        cat = c.get('category_middle', 'unknown')
        if cat in b3_categories:
            if cat not in b3_canonicals_by_cat:
                b3_canonicals_by_cat[cat] = []
            b3_canonicals_by_cat[cat].append(c['canonical_item_id'])

    total_b3 = sum(len(items) for items in b3_canonicals_by_cat.values())
    print(f"B3 new canonicals by category:")
    for cat, expected_count in b3_categories.items():
        actual_count = len(b3_canonicals_by_cat.get(cat, []))
        status = "✓" if actual_count == expected_count else "✗"
        print(f"  {status} {cat}: {actual_count}/{expected_count}")

    if total_b3 != 11:
        print(f"FAIL: Expected 11 B3 canonicals, got {total_b3}")
        return False
    print(f"✓ Total B3 canonicals: 11")
    print()

    # 6. Merged canonical check
    merged_c = next((c for c in registry if c['canonical_item_id'] == 'pipe_insulation_al_band_03x30mm'), None)
    if not merged_c:
        print("FAIL: Merged canonical pipe_insulation_al_band_03x30mm not found")
        return False
    print(f"✓ Merged canonical found: {merged_c.get('canonical_name')}")
    print(f"  Aliases: {len(merged_c.get('aliases', []))} (primary + {len(merged_c.get('aliases', [])) - 1} secondary)")
    print()

    print("=" * 70)
    print("✓ STEP 0 BASELINE VERIFICATION: PASS")
    print("=" * 70)
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
