"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01 — target resolver.

AI proposal의 (label, optional targetHint)로부터 운영동이 이해할
target_key (cellKey / paragraphKey)를 결정론적으로 도출한다.

본 모듈은 A동(라벨 corpus) read-only, B동 진단 결과 read-only로 사용한다.
"""
from __future__ import annotations

import re

# 라벨 정규화: 공백/괄호/마침표 제거 + 소문자 (한글은 그대로)
_NORM_RE = re.compile(r"[\s\(\)\[\]\.,:;·\-_/]+")


def normalize_label(label: str) -> str:
    if not label:
        return ""
    n = _NORM_RE.sub("", label)
    return n.strip()


def find_candidate_targets_in_recognition(
    normalized_label: str,
    recognition_result: dict,
) -> list[dict]:
    """recognitionResult.labelOccurrences에서 동일 normalized_label 위치 후보 수집.

    recognition_result는 운영동에서 받은 인식 결과 (read-only).
    반환: [{targetType, cellKey?, paragraphKey?, neighborText?}, ...]
    """
    if not normalized_label:
        return []
    occurrences = (recognition_result or {}).get("labelOccurrences") or []
    out: list[dict] = []
    for occ in occurrences:
        if occ.get("normalizedLabel") == normalized_label:
            cell_key = occ.get("cellKey")
            paragraph_key = occ.get("paragraphKey")
            if cell_key:
                out.append({
                    "targetType": "cell",
                    "cellKey": cell_key,
                    "paragraphKey": None,
                    "neighborText": occ.get("neighborText"),
                })
            elif paragraph_key:
                out.append({
                    "targetType": "paragraph",
                    "cellKey": None,
                    "paragraphKey": paragraph_key,
                    "neighborText": occ.get("neighborText"),
                })
    return out


def resolve_target(
    proposal: dict,
    recognition_result: dict,
) -> dict:
    """AI proposal 1건의 target 결정.

    return: {
        "status": "RESOLVED" | "AMBIGUOUS" | "NOT_FOUND",
        "target": dict or None,
        "candidates": list[dict],
        "normalizedLabel": str,
    }
    """
    label = proposal.get("label") or ""
    norm = normalize_label(label)
    hint = proposal.get("targetHint") or {}

    # targetHint가 명시적으로 cellKey/paragraphKey를 주면 우선 사용
    if isinstance(hint, dict):
        if hint.get("cellKey"):
            return {
                "status": "RESOLVED",
                "target": {"targetType": "cell",
                              "cellKey": hint["cellKey"],
                              "paragraphKey": None},
                "candidates": [],
                "normalizedLabel": norm,
            }
        if hint.get("paragraphKey"):
            return {
                "status": "RESOLVED",
                "target": {"targetType": "paragraph",
                              "cellKey": None,
                              "paragraphKey": hint["paragraphKey"]},
                "candidates": [],
                "normalizedLabel": norm,
            }

    candidates = find_candidate_targets_in_recognition(norm, recognition_result)
    if not candidates:
        return {
            "status": "NOT_FOUND",
            "target": None,
            "candidates": [],
            "normalizedLabel": norm,
        }
    if len(candidates) == 1:
        return {
            "status": "RESOLVED",
            "target": candidates[0],
            "candidates": candidates,
            "normalizedLabel": norm,
        }
    return {
        "status": "AMBIGUOUS",
        "target": None,
        "candidates": candidates,
        "normalizedLabel": norm,
    }


def resolve_target_batch(
    proposals: list,
    recognition_result: dict,
) -> list[dict]:
    return [resolve_target(p, recognition_result) for p in proposals or []]
