#!/usr/bin/env node
/* 질문 패널 순수 로직 자체 시나리오. 실패 시 비-0 종료.
 *
 * DOM 없이 buildFillCommands·partitionPlan·initialAnswers·charPrIndex 를
 * 검증한다. §4 안전 성질(빈값 안채움·문서없는칸 제외·charPr 상속·민감칸
 * 확인분리)을 고정한다.
 */
import {
  charPrIndex, buildFillCommands, partitionPlan, initialAnswers,
  parseSourceLines, applyAiProposals, planFieldRows, roleCellMap,
  roleByCellId,
} from "./form_question_panel.mjs";

let failed = 0;
function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); failed++; }
}

// ── fixture ──────────────────────────────────────────────────────────────
const docModel = {
  paragraphs: [
    { paragraphId: "par_t_s0_000_r1_c1_p0",
      runs: [{ runId: "r0", text: "", charPrIDRef: "11" }] },
    { paragraphId: "par_t_s0_000_r2_c1_p0",
      runs: [{ runId: "r0", text: "", charPrIDRef: "12" }] },
    { paragraphId: "par_t_s0_000_r3_c1_p0", runs: [] },   // run 없음
  ],
};
const HASH = "deadbeef";

// ── charPrIndex ──────────────────────────────────────────────────────────
const idx = charPrIndex(docModel);
assert(idx["par_t_s0_000_r1_c1_p0"] === "11", "charPr 첫 run 상속");
assert(idx["par_t_s0_000_r3_c1_p0"] === null, "run 없으면 null");

// ── buildFillCommands: 정상 ─────────────────────────────────────────────
const cmds = buildFillCommands(
  { "par_t_s0_000_r1_c1_p0": "홍길동",
    "par_t_s0_000_r2_c1_p0": "서울시" }, docModel, HASH);
assert(cmds.length === 2, "2칸 명령 생성");
assert(cmds[0].commandType === "TYPE_TEXT", "TYPE_TEXT");
assert(cmds[0].forward.inheritCharPrIDRef === "11", "charPr 상속 (신규 생성 안 함)");
assert(cmds[0].forward.insertText === "홍길동", "삽입값");
assert(cmds[0].forward.rangeStart === 0 && cmds[0].forward.rangeEnd === 0,
  "빈 칸 [0,0] 삽입");
assert(cmds[0].sourceDocumentHash === HASH, "소스 해시 전달");
assert(cmds[0].expectedBefore === "", "빈 칸 expectedBefore");

// ── buildFillCommands: 빈 값은 안 채운다(지어내지 않음) ──────────────────
const c2 = buildFillCommands(
  { "par_t_s0_000_r1_c1_p0": "", "par_t_s0_000_r2_c1_p0": "값" },
  docModel, HASH);
assert(c2.length === 1, "빈 값 칸은 제외");
assert(c2[0].paragraphId === "par_t_s0_000_r2_c1_p0", "값 있는 칸만");

// ── buildFillCommands: 문서에 없는 칸은 제외 ────────────────────────────
const c3 = buildFillCommands(
  { "par_없는칸_p0": "값", "par_t_s0_000_r1_c1_p0": "값2" }, docModel, HASH);
assert(c3.length === 1, "문서에 없는 paragraphId 제외");

// ── commandId 는 매번 유일 ───────────────────────────────────────────────
assert(cmds[0].commandId !== cmds[1].commandId, "명령 id 유일");

// ── partitionPlan: 민감칸을 '확인 필요'로 분리 ──────────────────────────
const plan = {
  autoFill: [
    { paragraphId: "a1", label: "주소", value: "서울" },
    { paragraphId: "a2", label: "주민등록번호", value: "x",
      requiresConfirmation: true },
  ],
  questions: [
    { paragraphId: "q1", label: "사용용도", suggested: "" },
    { paragraphId: "q2", label: "생년월일", suggested: "",
      requiresConfirmation: true },
  ],
  skipped: [{ paragraphId: "s1", label: "접수번호" }],
};
const part = partitionPlan(plan);
assert(part.auto.length === 1 && part.auto[0].paragraphId === "a1",
  "자동채움은 비민감만");
assert(part.ask.length === 1 && part.ask[0].paragraphId === "q1",
  "질문은 비민감만");
assert(part.sensitive.length === 2, "민감칸 2개 확인분리 (자동채움+질문)");
assert(part.skipped.length === 1, "관공서칸 제외 보존");

// ── initialAnswers: 자동값·제안값을 초기값으로 ──────────────────────────
const init = initialAnswers(plan);
assert(init["a1"] === "서울", "자동채움 초기값");
assert(init["q1"] === undefined, "빈 제안은 초기값 없음");
assert(init["a2"] === "x", "민감 자동값도 초기값(단, 사용자 확인 대상)");

// ── 통합: 계획 → 초기답변 → 명령. 민감 자동값이 확인 없이 나가지 않는가? ─
// 정책상 민감칸은 사용자가 확인해야 하지만, 이 순수 로직은 answers 를
// 그대로 명령화한다. 민감 확인 강제는 UI(확인 필요 구역)가 담당한다.
// 여기서는 answers 에 든 값만 명령이 됨을 확인한다.
const flowDoc = { paragraphs: [{ paragraphId: "a1",
  runs: [{ text: "", charPrIDRef: "1" }] }] };
const flowCmds = buildFillCommands({ a1: "서울" }, flowDoc, HASH);
assert(flowCmds.length === 1, "통합 흐름 명령화");

// ── parseSourceLines: "항목: 값" 파싱 ───────────────────────────────────
const src = parseSourceLines("상호: 가나다전기\n대표자 : 홍길동\n빈줄\n전화： 02-1\n무값:");
assert(src["상호"] === "가나다전기", "콜론 파싱");
assert(src["대표자"] === "홍길동", "공백 허용");
assert(src["전화"] === "02-1", "전각 콜론 허용");
assert(!("무값" in src), "값 없는 줄 제외");
assert(!("빈줄" in src), "콜론 없는 줄 제외");

// ── applyAiProposals: 제3자 칸 자동 안 채움 ─────────────────────────────
const planItems = [
  { label: "상호", paragraphId: "p_org" },
  { label: "법정대리인성명", paragraphId: "p_rep" },
  { label: "주소", paragraphId: "p_addr" },
];
const aiResult = {
  proposals: [
    { label: "상호", value: "가나다전기", key: "p_org" },
    { label: "주소", value: "서울시", key: "p_addr" },
    { label: "법정대리인성명", value: "홍길동", key: "p_rep" },  // 모델이 잘못 냄
  ],
  heldForThirdParty: [{ label: "법정대리인성명" }],
};
const merged = applyAiProposals({}, aiResult, planItems);
assert(merged["p_org"] === "가나다전기", "본인 칸 제안 반영");
assert(merged["p_addr"] === "서울시", "본인 칸 제안 반영2");
assert(!("p_rep" in merged), "제3자 칸은 held 라 자동 안 채움");

// ── applyAiProposals: 사용자 입력 우선(안 덮음) ─────────────────────────
const merged2 = applyAiProposals({ p_org: "내가입력" }, aiResult, planItems);
assert(merged2["p_org"] === "내가입력", "기존 사용자 입력 보존");

// ── planFieldRows: 서식이 바뀌면 필드 목록이 통째로 바뀐다 ──────────────
// (신고된 버그 "서식 변경 시 입력창이 안 바뀜" 의 회귀 감시)
const planA = {
  autoFill: [{ paragraphId: "A_p1", label: "성명" }],
  questions: [{ paragraphId: "A_q1", label: "사용용도" }],
  skipped: [],
};
const planB = {
  autoFill: [],
  questions: [{ paragraphId: "B_q1", label: "전기사용장소" },
              { paragraphId: "B_q2", label: "소유자명" }],
  skipped: [],
};
const rowsA = planFieldRows(planA, initialAnswers(planA));
const rowsB = planFieldRows(planB, initialAnswers(planB));
const pidsA = rowsA.map((r) => r.paragraphId).sort();
const pidsB = rowsB.map((r) => r.paragraphId).sort();
assert(JSON.stringify(pidsA) === JSON.stringify(["A_p1", "A_q1"]),
  "서식 A 필드");
assert(JSON.stringify(pidsB) === JSON.stringify(["B_q1", "B_q2"]),
  "서식 B 필드");
assert(pidsA.every((p) => !pidsB.includes(p)),
  "서식 바꾸면 이전 서식 필드가 하나도 안 남는다");
// 값도 새 서식 기준(A의 값이 B로 새지 않음)
const rowsB2 = planFieldRows(planB, { A_p1: "옛값" });
assert(rowsB2.every((r) => r.value === ""), "이전 서식 답이 새 서식에 안 샘");

// ── roleCellMap: 민원인/관계자 셀 좌표 구분 ─────────────────────────────
const planRC = {
  autoFill: [{ paragraphId: "a", tableIndex: 0, row: 1, col: 1 }],
  questions: [{ paragraphId: "q", tableIndex: 0, row: 2, col: 1 }],
  skipped: [{ paragraphId: "s", tableIndex: 0, row: 0, col: 0 }],
};
const rc = roleCellMap(planRC);
assert(rc["0:1:1"] === "applicant", "자동채움 칸 = 민원인");
assert(rc["0:2:1"] === "applicant", "질문 칸 = 민원인");
assert(rc["0:0:0"] === "office", "skipped 칸 = 관계자");
assert(Object.keys(rc).length === 3, "좌표 없는 항목은 제외");

// ── roleByCellId: paragraphId → 좌표 렌더러 cellId 역할 매핑 ──────────────
// (충실 뷰어 .co-box[data-cell-id] / 레이아웃 박스 색칠의 근거)
const planCid = {
  autoFill: [{ paragraphId: "par_t_s0_000_r1_c1_p0" }],
  questions: [{ paragraphId: "par_t_s0_002_r3_c2_p1" }],
  skipped: [{ paragraphId: "par_t_s1_005_r6_c1_p0" },
            { paragraphId: "본문문단_없음" }],   // 표 셀 아님 → 제외
};
const cid = roleByCellId(planCid);
assert(cid["cell_t_s0_000_r1_c1"] === "applicant",
  "자동채움 paragraphId → cellId(민원인)");
assert(cid["cell_t_s0_002_r3_c2"] === "applicant",
  "질문 paragraphId → cellId(민원인), _p1 제거");
assert(cid["cell_t_s1_005_r6_c1"] === "office",
  "skipped paragraphId → cellId(관계자)");
assert(Object.keys(cid).length === 3, "표 셀 아닌 paragraphId 는 제외");

if (failed) { console.error(`\n${failed} FAIL`); process.exit(1); }
console.log("form_question_panel_self_test: ALL PASS");
