"""HWPX-FORM-TYPE-CLASSIFICATION-01 — 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def test_form_type_classifier_importable():
    from hwpx.recognition_corpus import form_type_classifier as ftc

    assert hasattr(ftc, "classify_form_type")
    assert hasattr(ftc, "classify_batch")
    assert hasattr(ftc, "build_summary")


@pytest.mark.parametrize(
    "filename,expected_domain,expected_kind",
    [
        ("00155_054_[별지_제6호서식]_허가증__filled.hwpx", "기타", "허가증"),
        (
            "0018a0240c771c1c_011_[별지_제8호서식]_기계설비_사용_전_검사_확인증__filled.hwpx",
            "기계설비",
            "확인증",
        ),
        ("00209_039_[별지_제21호의2서식]_시공감리_신청서__filled.hwpx", "건축·건설", "신청서"),
        (
            "00211_041_[별지_제33호서식]_특정고압가스_사용신고서__filled.hwpx",
            "가스·위험물",
            "신고서",
        ),
        ("(0)관리책임자 등 선임보고서__filled.hwpx", "기타", "보고서"),
        ("소방시설_완공검사_신청서__filled.hwpx", "소방시설", "신청서"),
        ("전기공사_준공계__filled.hwpx", "전기", "준공서"),
    ],
)
def test_form_type_classification(filename, expected_domain, expected_kind):
    from hwpx.recognition_corpus.form_type_classifier import classify_form_type

    r = classify_form_type(Path(filename))
    assert r.domain == expected_domain, (
        f"'{filename}' → domain={r.domain} (expected {expected_domain})"
    )
    assert r.formKind == expected_kind, (
        f"'{filename}' → kind={r.formKind} (expected {expected_kind})"
    )


def test_byeolji_number_extraction():
    from hwpx.recognition_corpus.form_type_classifier import classify_form_type

    r = classify_form_type(Path("001_[별지_제21호의2서식]_신청서__filled.hwpx"))
    assert r.byeoljiNumber == "21호의2", f"byeoljiNumber={r.byeoljiNumber}"


def test_form_name_extraction():
    from hwpx.recognition_corpus.form_type_classifier import classify_form_type

    r = classify_form_type(Path("00209_039_[별지_제21호의2서식]_시공감리_신청서__filled.hwpx"))
    assert "신청서" in r.formName, f"formName={r.formName}"


def test_no_path_leak_in_result():
    import json

    from hwpx.recognition_corpus.form_type_classifier import classify_form_type

    r = classify_form_type(Path("C:\\Users\\test\\서식명__filled.hwpx"))
    out = json.dumps(r.to_dict(), ensure_ascii=False)
    assert "C:\\Users\\" not in out, f"path leak: {out}"


def test_build_summary_structure():
    from hwpx.recognition_corpus.form_type_classifier import build_summary, classify_form_type

    paths = [
        Path("소방시설_신청서__filled.hwpx"),
        Path("건축_신고서__filled.hwpx"),
        Path("_unknown.hwpx"),
    ]
    results = [classify_form_type(p) for p in paths]
    s = build_summary(results)
    assert s["totalFiles"] == 3
    assert "domainCounts" in s
    assert "formKindCounts" in s


def test_output_report_exists():
    out = (
        PROJECT_ROOT
        / "data"
        / "reports"
        / "hwpx_form_type_classification"
        / "per_file_form_type.jsonl"
    )
    if not out.exists():
        pytest.skip(
            f"실제 로컬 코퍼스로 생성한 산출물 없음(data/reports/는 .gitignore 대상): {out}"
        )


def test_output_jsonl_record_structure():
    import json

    out = (
        PROJECT_ROOT
        / "data"
        / "reports"
        / "hwpx_form_type_classification"
        / "per_file_form_type.jsonl"
    )
    if not out.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    line = out.read_text(encoding="utf-8").splitlines()[0]
    rec = json.loads(line)
    for key in ("maskedFileId", "formName", "domain", "formKind", "confidence"):
        assert key in rec, f"key missing: {key}"
