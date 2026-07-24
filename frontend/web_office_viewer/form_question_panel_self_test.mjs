#!/usr/bin/env node
/* 질문 패널 순수 로직 자체 시나리오. 실패 시 비-0 종료.
 *
 * DOM 없이 buildFillCommands·partitionPlan·initialAnswers·charPrIndex 를
 * 검증한다. §4 안전 성질(빈값 안채움·문서없는칸 제외·charPr 상속·민감칸
 * 확인분리)을 고정한다.
 */
import {
  charPrIndex, buildFillCommands, partitionPlan, initialAnswers,
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

if (failed) { console.error(`\n${failed} FAIL`); process.exit(1); }
console.log("form_question_panel_self_test: ALL PASS");
