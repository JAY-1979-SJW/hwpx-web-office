"""
HWPX-FORM-INDEX-AND-RECOMMEND-01

form_index.py — 서식 인덱스 빌드 및 키워드 기반 추천 엔진.

read-only: 파일 내용 읽지 않음. per_file_form_type.jsonl 기반.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSONL = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_type_classification" / "per_file_form_type.jsonl"
)

# ── 추천 결과 ────────────────────────────────────────────────────────────────

@dataclass
class RecommendResult:
    formName: str
    domain: str
    formKind: str
    byeoljiNumber: str
    fileCount: int
    score: float
    matchedTokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "formName":      self.formName,
            "domain":        self.domain,
            "formKind":      self.formKind,
            "byeoljiNumber": self.byeoljiNumber,
            "fileCount":     self.fileCount,
            "score":         round(self.score, 3),
            "matchedTokens": self.matchedTokens,
        }


# ── 인덱스 ────────────────────────────────────────────────────────────────────

class FormIndex:
    def __init__(self, records: list[dict]) -> None:
        # deduplicate by (formName, domain, formKind, byeoljiNumber)
        seen: dict[tuple, int] = {}  # key → index in _records
        file_counts: dict[int, int] = {}
        deduped: list[dict] = []
        for rec in records:
            key = (
                rec.get("formName", ""),
                rec.get("domain", ""),
                rec.get("formKind", ""),
                rec.get("byeoljiNumber", ""),
            )
            if key in seen:
                file_counts[seen[key]] += 1
            else:
                idx = len(deduped)
                seen[key] = idx
                deduped.append(rec)
                file_counts[idx] = 1

        self._records = deduped
        self._file_counts = file_counts
        # inverted index: token → set of record indices
        self._inv: dict[str, set[int]] = {}
        for i, rec in enumerate(self._records):
            for tok in _tokenize(
                rec.get("formName", "") + " "
                + rec.get("domain", "") + " "
                + rec.get("formKind", "")
            ):
                self._inv.setdefault(tok, set()).add(i)

    @classmethod
    def load(cls, jsonl_path: Path = DEFAULT_JSONL) -> "FormIndex":
        records = [
            json.loads(line)
            for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(records)

    def search(self, query: str, top_n: int = 10) -> list[RecommendResult]:
        """키워드 쿼리로 서식 추천 (BM25 없이 TF-style 점수)."""
        tokens = _tokenize(query)
        if not tokens:
            return []

        scores: dict[int, float] = {}
        matched: dict[int, list[str]] = {}

        for tok in tokens:
            # 완전 일치
            for idx in self._inv.get(tok, set()):
                scores[idx] = scores.get(idx, 0.0) + 1.0
                matched.setdefault(idx, []).append(tok)
            # 부분 일치 (0.4점)
            for inv_tok, idx_set in self._inv.items():
                if tok in inv_tok and inv_tok != tok:
                    for idx in idx_set:
                        scores[idx] = scores.get(idx, 0.0) + 0.4
                        if tok not in matched.get(idx, []):
                            matched.setdefault(idx, []).append(f"~{tok}")

        # 정규화: 매칭 토큰 수 / 전체 쿼리 토큰 수
        q_len = max(len(tokens), 1)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

        results = []
        for idx, raw_score in ranked:
            rec = self._records[idx]
            results.append(RecommendResult(
                formName      = rec.get("formName", ""),
                domain        = rec.get("domain", ""),
                formKind      = rec.get("formKind", ""),
                byeoljiNumber = rec.get("byeoljiNumber", ""),
                fileCount     = self._file_counts.get(idx, 1),
                score         = raw_score / q_len,
                matchedTokens = matched.get(idx, []),
            ))
        return results

    def stats(self) -> dict[str, Any]:
        from collections import Counter
        domains = Counter(r.get("domain", "") for r in self._records)
        kinds   = Counter(r.get("formKind", "") for r in self._records)
        return {
            "totalForms":    len(self._records),
            "domainCounts":  dict(domains.most_common()),
            "formKindCounts": dict(kinds.most_common()),
        }

    def export_static_index(self, out_path: Path) -> None:
        """JS fetch용 정적 JSON 인덱스 파일 생성."""
        # 용량 절감: maskedFileId 제외, 필수 필드만
        slim = [
            {
                "n": r.get("formName", ""),
                "d": r.get("domain", ""),
                "k": r.get("formKind", ""),
                "b": r.get("byeoljiNumber", ""),
            }
            for r in self._records
        ]
        out_path.write_text(
            json.dumps({"forms": slim}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )


# ── 토크나이저 ────────────────────────────────────────────────────────────────

_SPLIT_RE = re.compile(r"[\s_\-··/]+")

def _tokenize(text: str) -> list[str]:
    """한국어 텍스트를 공백/구분자로 토크나이즈."""
    parts = _SPLIT_RE.split(text.strip())
    tokens = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            tokens.append(p)
    return tokens


# ── 편의 함수 ─────────────────────────────────────────────────────────────────

_GLOBAL_INDEX: FormIndex | None = None

def get_index(jsonl_path: Path = DEFAULT_JSONL) -> FormIndex:
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = FormIndex.load(jsonl_path)
    return _GLOBAL_INDEX


def recommend(query: str, top_n: int = 10) -> list[RecommendResult]:
    return get_index().search(query, top_n)
