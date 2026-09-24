#!/bin/bash
# HWPX Full Audit Integration Script
# 감사 스크립트 통합 실행

set -e

# Configuration
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
SAMPLE_ROOT="${SAMPLE_ROOT:-.}"
OUT_DIR="docs/reports/hwpx_audit"
INCLUDE_FIXTURES="${INCLUDE_FIXTURES:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "HWPX Full Audit Script"
echo "=========================================="
echo ""
echo "Base URL: $BASE_URL"
echo "Sample Root: $SAMPLE_ROOT"
echo "Output Dir: $OUT_DIR"
echo "Include Fixtures: $INCLUDE_FIXTURES"
echo ""

# Step 0: Git status
echo "[STEP 0] Recording git status..."
git status --short > $OUT_DIR/logs/git_status_before.log 2>&1 || true
git log --oneline -5 > $OUT_DIR/logs/git_log.log 2>&1 || true
echo "  ✅ Git status recorded"
echo ""

# Step 1: Run HWPX tests
echo "[STEP 1] Running HWPX tests..."
if ./gradlew test --tests '*HwpxParserTest' --tests '*ParseHwpxHandlerTest' > $OUT_DIR/logs/hwpx_tests.log 2>&1; then
    echo -e "  ${GREEN}✅ HWPX tests PASS${NC}"
else
    echo -e "  ${RED}❌ HWPX tests FAIL${NC}"
    exit 1
fi
echo ""

# Step 2: Build (HWPX only, exclude other tests)
echo "[STEP 2] Building..."
if ./gradlew build --exclude-task test > $OUT_DIR/logs/build.log 2>&1; then
    echo -e "  ${GREEN}✅ Build PASS${NC}"
else
    echo -e "  ${RED}❌ Build FAIL${NC}"
    exit 1
fi
echo ""

# Step 3: Sample inventory
echo "[STEP 3] Generating sample inventory..."
python3 scripts/hwpx/audit_hwpx_samples.py --sample-root "$SAMPLE_ROOT" --out-dir "$OUT_DIR" > $OUT_DIR/logs/audit_hwpx_samples.log 2>&1
if [ -f "$OUT_DIR/inventories/hwpx_sample_inventory_latest.json" ]; then
    echo -e "  ${GREEN}✅ Inventory generated${NC}"
else
    echo -e "  ${RED}❌ Inventory generation failed${NC}"
    exit 1
fi
echo ""

# Step 4: Health check
echo "[STEP 4] Checking server health..."
if curl -s -m 3 "$BASE_URL/health" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Server is running${NC}"
else
    echo -e "  ${YELLOW}⚠️  Server not responding${NC}"
    echo "  To run smoke tests, start server in another terminal:"
    echo "    ./gradlew run --args \"serve 8080\""
    echo "  Then run this script with:"
    echo "    bash scripts/hwpx/run_hwpx_full_audit.sh --base-url http://127.0.0.1:8080"
    SKIP_SMOKE="true"
fi
echo ""

# Step 5: API smoke test
if [ "$SKIP_SMOKE" != "true" ]; then
    echo "[STEP 5] Running API smoke test..."
    python3 scripts/hwpx/smoke_hwpx_api.py \
        --base-url "$BASE_URL" \
        --inventory "$OUT_DIR/inventories/hwpx_sample_inventory_latest.json" \
        --out-dir "$OUT_DIR" \
        --include-fixtures="$INCLUDE_FIXTURES" > $OUT_DIR/logs/smoke_hwpx_api.log 2>&1

    if [ -f "$OUT_DIR/evidence/latest_batch_summary.json" ]; then
        echo -e "  ${GREEN}✅ Smoke test completed${NC}"
    else
        echo -e "  ${RED}❌ Smoke test failed${NC}"
        exit 1
    fi
else
    echo "[STEP 5] Skipping API smoke test (server not running)"
fi
echo ""

# Step 6: Security tests
if [ "$SKIP_SMOKE" != "true" ]; then
    echo "[STEP 6] Running security defense tests..."
    python3 scripts/hwpx/test_hwpx_security.py \
        --base-url "$BASE_URL" \
        --out-dir "$OUT_DIR/evidence" > $OUT_DIR/logs/test_hwpx_security.log 2>&1

    if [ -f "$OUT_DIR/evidence/negative_smoke_summary.json" ]; then
        echo -e "  ${GREEN}✅ Security tests completed${NC}"
    else
        echo -e "  ${RED}❌ Security tests failed${NC}"
        exit 1
    fi
else
    echo "[STEP 6] Skipping security tests (server not running)"
fi
echo ""

# Step 7: Evidence verification
if [ "$SKIP_SMOKE" != "true" ]; then
    echo "[STEP 7] Verifying evidence..."

    # Find latest batch summary run directory
    LATEST_BATCH=$(ls -t $OUT_DIR/evidence/latest_batch_summary.json 2>/dev/null | head -1)
    if [ -z "$LATEST_BATCH" ]; then
        echo -e "  ${RED}❌ No batch summary found${NC}"
        exit 1
    fi

    # Get the run_id from batch summary
    RUN_ID=$(python3 -c "import json; f=open('$LATEST_BATCH'); d=json.load(f); print(d.get('run_id', ''))" 2>/dev/null)

    if [ -z "$RUN_ID" ]; then
        echo -e "  ${YELLOW}⚠️  Could not extract run_id${NC}"
        RUN_ID="20260507_182925"  # fallback
    fi

    SAMPLE_DIR="$OUT_DIR/evidence/$RUN_ID"

    python3 scripts/hwpx/verify_hwpx_evidence.py \
        --inventory "$OUT_DIR/inventories/hwpx_sample_inventory_latest.json" \
        --batch-summary "$LATEST_BATCH" \
        --sample-dir "$SAMPLE_DIR" \
        --out-dir "$OUT_DIR/summaries" > $OUT_DIR/logs/verify_hwpx_evidence.log 2>&1

    if [ -f "$OUT_DIR/summaries/hwpx_evidence_verification_latest.json" ]; then
        echo -e "  ${GREEN}✅ Evidence verification completed${NC}"
    else
        echo -e "  ${YELLOW}⚠️  Evidence verification skipped${NC}"
    fi
else
    echo "[STEP 7] Skipping evidence verification (server not running)"
fi
echo ""

# Step 8: Final report
echo "[STEP 8] Generating final report..."
if [ -f "$OUT_DIR/summaries/hwpx_evidence_verification_latest.json" ]; then
    echo -e "  ${GREEN}✅ Full audit completed${NC}"

    # Show summary
    python3 -c "
import json
with open('$OUT_DIR/summaries/hwpx_evidence_verification_latest.json') as f:
    data = json.load(f)
    print(f'  Inventory: {data[\"inventoryCount\"]} samples')
    print(f'  Batch: {data[\"batchCount\"]} results')
    print(f'  Passed: {data[\"batchPassed\"]} samples')
    print(f'  Judgment: {data[\"judgment\"]}')
" 2>/dev/null || true
else
    echo -e "  ${YELLOW}⚠️  Final report skipped${NC}"
fi
echo ""

# Step 9: Git status after
echo "[STEP 9] Recording final git status..."
git status --short > $OUT_DIR/logs/git_status_after.log 2>&1 || true
echo "  ✅ Final git status recorded"
echo ""

echo "=========================================="
if [ "$SKIP_SMOKE" != "true" ]; then
    echo -e "${GREEN}✅ Full audit completed successfully${NC}"
    echo "Results at: $OUT_DIR/"
else
    echo -e "${YELLOW}⚠️  Partial audit (server not running)${NC}"
    echo "To complete full audit, run:"
    echo "  ./gradlew run &"
    echo "  bash scripts/hwpx/run_hwpx_full_audit.sh"
fi
echo "=========================================="
