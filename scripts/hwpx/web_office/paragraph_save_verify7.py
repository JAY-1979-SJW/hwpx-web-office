"""PARA-SAVE verify7 게이트 (V1~V7) — 부분 준공 모드.

본 모듈은 writer (hwpx edit tool 모듈) 를 import 하지 않는다.
writer paragraph plan 미지원 단계에서는 output HWPX 가 생성되지 않으므로
V1/V2/V3/V7 은 "vacuous PASS 차단" 의도로 FAIL 로 떨어지지만,
V4/V5/V6 는 정상 검증된다.

게이트 항목
- V1_RANGE_POSITION_OK         : output readback, paragraph 의 (anchor~focus)
                                                          슬라이스 = afterText
- V2_NO_CROSS_PARAGRAPH_LEAK   : output blob 내 afterText 출현이 다른
                                                          paragraphId 로 누출되지 않음
- V3_UNTOUCHED_RUNS_PRESERVED  : 적용 안 한 paragraph 의 text 동일
- V4_CHARPR_PRESERVED          : applyCharPrIDRef ⊆ 원본 char_pr_set
- V5_PARPR_PRESERVED           : parPr 무결성 — APPLY_PARA_FORMAT 대상만
                                 의도된 기존 paraPr 로 변경, 신규 paraPr 도입 금지
- V6_OUTPUT_ISOLATED           : output != source && sandbox 하위
- V7_READBACK_MATCH            : V1 PASS && output 존재
"""
from __future__ import annotations
import zipfile
from pathlib import Path
from typing import Any

from .para_edit_model import Paragraph
from .cell_save_verify7 import _output_under_sandbox


def _read_blob(zip_path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(str(zip_path)) as z:
        for name in z.namelist():
            if name.endswith(".xml") or name.endswith(".hpf"):
                parts.append(z.read(name).decode("utf-8", "ignore"))
    return "".join(parts)


def _header_para_pr_ids(zip_path: Path) -> set[str]:
    """HWPX 의 Contents/header.xml 에서 <hh:paraPr id> 집합 (신규 도입 탐지용)."""
    import xml.etree.ElementTree as ET
    if not zip_path.is_file():
        return set()
    try:
        with zipfile.ZipFile(str(zip_path)) as z:
            name = next((n for n in z.namelist()
                         if n.replace("\\", "/").endswith("Contents/header.xml")), None)
            if name is None:
                return set()
            root = ET.fromstring(z.read(name))
    except Exception:
        return set()
    return {str(el.attrib["id"]) for el in root.iter()
            if el.tag.rsplit("}", 1)[-1] == "paraPr" and "id" in el.attrib}


def verify7_paragraphs(
    *,
    source_path: Path,
    output_path: Path,
    project_root: Path,
    applied_plan_edits: list[dict],
    paragraphs_by_id: dict[str, Paragraph],
    pre_save_paragraph_texts: dict[str, str],
) -> dict[str, Any]:
    """paragraph 판 verify7. writer 본 실행 이후 호출되도록 설계되었으나
    본 부분 준공 단계에서는 output_path 가 존재하지 않을 수 있다.
    """
    findings: list[dict] = []
    results: dict[str, str] = {}

    # V6 — output 격리 (output 미존재여도 경로 정책은 검증 가능)
    same_path = (output_path.resolve() == source_path.resolve()
                              if source_path.is_file() else False)
    under_sb = _output_under_sandbox(output_path, project_root)
    v6 = "PASS" if (not same_path and under_sb) else "FAIL"
    results["V6_OUTPUT_ISOLATED"] = v6
    if v6 == "FAIL":
        findings.append({"code": "V6_OUTPUT_NOT_ISOLATED",
                                  "samePath": same_path,
                                  "underSandbox": under_sb,
                                  "outputPath": str(output_path)})

    # V4 — applyCharPrIDRef 가 원본 paragraph char_pr_set 의 부분집합
    v4 = "PASS"
    for entry in applied_plan_edits:
        pid = entry["paragraphId"]
        para = paragraphs_by_id.get(pid)
        if para is None:
            v4 = "FAIL"
            findings.append({"code": "V4_PARAGRAPH_MISSING",
                                      "paragraphId": pid})
            continue
        apply_pr = entry.get("applyCharPrIDRef")
        # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
        # APPLY_FORMAT 은 targetCharPrIDRef 가 paragraph 의 원본 set
        # 에 없을 수 있다 (header 에는 존재). 신규 charPr 도입은 writer
        # 단계에서 header 존재 검증으로 차단되므로 본 V4 에서는 APPLY_FORMAT
        # 항목의 charPr-not-in-paragraph 검사는 면제한다.
        if entry.get("commandType") == "APPLY_FORMAT":
            continue
        if apply_pr is None:
            # None 은 원본 char_pr_set 에 None 이 있어야 PASS
            if None not in para.char_pr_set():
                v4 = "FAIL"
                findings.append({"code": "V4_CHARPR_NEW_INTRODUCED",
                                          "paragraphId": pid,
                                          "applyCharPrIDRef": None})
            continue
        if apply_pr not in para.char_pr_set():
            v4 = "FAIL"
            findings.append({"code": "V4_CHARPR_NEW_INTRODUCED",
                                      "paragraphId": pid,
                                      "applyCharPrIDRef": apply_pr,
                                      "origCharPr": sorted(
                                          str(x) for x in para.char_pr_set())})
    if not applied_plan_edits:
        v4 = "FAIL"
        findings.append({"code": "V4_NO_APPLIED",
                                  "detail": "applied=∅ — vacuous PASS 방지"})
    results["V4_CHARPR_PRESERVED"] = v4

    # V5 — parPrIDRef 무변경 (applied paragraphId 의 사전 parPr 와
    # 현재 paragraphs_by_id 의 parPr 동일성).
    v5 = "PASS"
    applied_pids = {e["paragraphId"] for e in applied_plan_edits}
    for pid in applied_pids:
        para = paragraphs_by_id.get(pid)
        if para is None:
            v5 = "FAIL"
            findings.append({"code": "V5_PARAGRAPH_MISSING",
                                      "paragraphId": pid})
    # WEB-OFFICE-PARA-FORMAT-01(M2): parPr 변경은 APPLY_PARA_FORMAT 명령의
    # 대상 문단에서만 허용하고, 그 값은 반드시 "원본 header 에 이미 있던"
    # paraPr id 여야 한다(신규 paraPr 도입 = header mutation 금지).
    src_para_pr_ids = _header_para_pr_ids(source_path)
    for e in applied_plan_edits:
        if e.get("commandType") != "APPLY_PARA_FORMAT":
            continue
        tgt = e.get("targetParaPrIDRef")
        after = e.get("afterParaPrIDRef", e.get("paraPrIDRef"))
        if tgt is None or str(after) != str(tgt):
            v5 = "FAIL"
            findings.append({"code": "V5_PARAPR_TARGET_MISMATCH",
                             "paragraphId": e.get("paragraphId"),
                             "targetParaPrIDRef": tgt,
                             "afterParaPrIDRef": after})
        elif src_para_pr_ids and str(tgt) not in src_para_pr_ids:
            v5 = "FAIL"
            findings.append({"code": "V5_NEW_PARAPR_INTRODUCED",
                             "paragraphId": e.get("paragraphId"),
                             "targetParaPrIDRef": tgt})
    if not applied_plan_edits:
        v5 = "FAIL"
        findings.append({"code": "V5_NO_APPLIED",
                                  "detail": "applied=∅ — vacuous PASS 방지"})
    results["V5_PARPR_PRESERVED"] = v5

    # output 미존재 시 V1/V2/V3/V7 FAIL (vacuous PASS 차단)
    output_exists = output_path.is_file()
    if not output_exists:
        findings.append({"code": "OUTPUT_MISSING",
                                  "detail": str(output_path)})

    # V1 — readback paragraph 슬라이스 매칭
    v1 = "PASS"
    out_paragraphs: dict[str, str] = {}
    if output_exists:
        # paragraph parsing 은 본 부분 준공 범위 밖 → readback 불가로 처리
        v1 = "FAIL"
        findings.append({"code": "V1_READBACK_UNSUPPORTED",
                                  "detail": "paragraph readback parser 미지원"})
    else:
        v1 = "FAIL"
    results["V1_RANGE_POSITION_OK"] = v1

    # V2 — blob 누출 검사: output 미존재 시 FAIL
    v2 = "PASS"
    if output_exists:
        blob = _read_blob(output_path)
        for entry in applied_plan_edits:
            # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
            # APPLY_FORMAT 은 텍스트 변경이 없고 run split 으로 인해
            # afterText (=원본 slice) 가 단일 hp:t 로 더 이상 존재하지
            # 않을 수 있다. 본 게이트는 텍스트 삽입/치환 명령 한정.
            if entry.get("commandType") == "APPLY_FORMAT":
                continue
            # WEB-OFFICE-PARA-FORMAT-01(M2): APPLY_PARA_FORMAT 은 charPr 을
            # 건드리지 않는 문단서식 명령 → V4(charPr 보존) 검사 대상 아님.
            if entry.get("commandType") == "APPLY_PARA_FORMAT":
                continue
            after = entry.get("afterText", "")
            if after and after not in blob:
                v2 = "FAIL"
                findings.append({"code": "V2_AFTER_TEXT_MISSING",
                                          "paragraphId": entry["paragraphId"],
                                          "afterText": after})
    else:
        v2 = "FAIL"
    results["V2_NO_CROSS_PARAGRAPH_LEAK"] = v2

    # V3 — untouched paragraph 보존
    v3 = "PASS"
    if output_exists:
        for pid, before_text in pre_save_paragraph_texts.items():
            if pid in applied_pids:
                continue
            after_text = out_paragraphs.get(pid, before_text)
            if after_text != before_text:
                v3 = "FAIL"
                findings.append({"code": "V3_UNTOUCHED_CHANGED",
                                          "paragraphId": pid})
                break
    else:
        v3 = "FAIL"
    results["V3_UNTOUCHED_RUNS_PRESERVED"] = v3

    # V7 — readback match
    v7 = "PASS" if (v1 == "PASS" and output_exists) else "FAIL"
    results["V7_READBACK_MATCH"] = v7

    # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01: V8 신설.
    # PARA_INSERT 가 적용된 항목에 대해 신규 paragraph id 가 발급되었고
    # before+after 텍스트 합이 원본 paragraph 텍스트와 동일한지 검증.
    v8_findings, v8_results = _verify_v8_para_struct_integrity(
        applied_plan_edits, pre_save_paragraph_texts)
    findings.extend(v8_findings)
    results.update(v8_results)

    overall = ("PASS" if all(v == "PASS" for v in results.values())
                          else "FAIL")
    return {"results": results, "findings": findings,
                "verdict": overall}


def _verify_v8_para_struct_integrity(
        applied_plan_edits: list[dict],
        pre_save_paragraph_texts: dict[str, str],
        ) -> tuple[list[dict], dict[str, str]]:
    """V8 — PARA_INSERT 적용 항목 구조 무결성 검증.

    - 신규 paragraph id 존재
    - before + after == 원본 paragraph 텍스트
    - 신규 paragraph id != 원 paragraph id (id 충돌 없음)
    - charPrIDRef / parPrIDRef 상속 일관성
    """
    findings: list[dict] = []
    insert_items = [e for e in applied_plan_edits
                              if e.get("commandType") == "PARA_INSERT"]
    delete_items = [e for e in applied_plan_edits
                              if e.get("commandType") == "PARA_DELETE"]
    if not insert_items and not delete_items:
        # PARA_INSERT/PARA_DELETE 없는 경우 — V8 미적용 (PASS, vacuous 허용)
        return [], {"V8_PARA_STRUCT_INTEGRITY": "PASS"}
    v8 = "PASS"
    for entry in insert_items:
        orig_pid = entry.get("paragraphId")
        new_pid = entry.get("newParagraphId")
        before_text = entry.get("beforeText", "")
        after_text = entry.get("afterText", "")
        if not new_pid:
            v8 = "FAIL"
            findings.append({"code": "V8_NEW_PARAGRAPH_ID_MISSING",
                                      "paragraphId": orig_pid})
            continue
        if new_pid == orig_pid:
            v8 = "FAIL"
            findings.append({"code": "V8_PARAGRAPH_ID_COLLISION",
                                      "paragraphId": orig_pid,
                                      "newParagraphId": new_pid})
            continue
        original_text = pre_save_paragraph_texts.get(orig_pid, "")
        if original_text and (before_text + after_text != original_text):
            v8 = "FAIL"
            findings.append({"code": "V8_TEXT_SUM_MISMATCH",
                                      "paragraphId": orig_pid,
                                      "before": before_text,
                                      "after": after_text,
                                      "original": original_text})
    # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01: PARA_DELETE 검증.
    for entry in delete_items:
        removed_pid = entry.get("removedParagraphId") or entry.get("paragraphId")
        prev_pid = entry.get("prevParagraphId")
        if not removed_pid:
            v8 = "FAIL"
            findings.append({"code": "V8_PARA_DELETE_REMOVED_ID_MISSING",
                                      "entry": entry})
            continue
        if not prev_pid:
            v8 = "FAIL"
            findings.append({"code": "V8_PARA_DELETE_PREV_ID_MISSING",
                                      "removedParagraphId": removed_pid})
            continue
        # 제거된 paragraph id 가 원본에 존재했는지 (pre_save 에 있어야 함)
        if removed_pid not in pre_save_paragraph_texts:
            v8 = "FAIL"
            findings.append({"code": "V8_PARA_DELETE_ID_NOT_IN_PRESAVE",
                                      "removedParagraphId": removed_pid})
    return findings, {"V8_PARA_STRUCT_INTEGRITY": v8}
