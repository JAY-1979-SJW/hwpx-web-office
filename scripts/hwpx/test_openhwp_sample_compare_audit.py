import openhwp_sample_compare_audit as audit


def test_fnv1a64_text_matches_rust_probe_algorithm() -> None:
    assert audit.fnv1a64_text("") == "cbf29ce484222325"
    assert audit.fnv1a64_text("hello") == "a430d84680aabd0b"


def test_length_ratio_and_token_overlap_are_stable() -> None:
    assert audit.length_ratio(10, 20) == 0.5
    assert audit.length_ratio(0, 0) == 1.0
    assert audit.token_overlap("alpha beta", "beta gamma") == 0.333333


def test_aggregate_counts_parser_and_decoder_signals() -> None:
    rows = [
        {
            "category": "A",
            "comparison": {"python_hwpx_text_equal": True, "python_hwpx_roundtrip_status": "PASS", "risk": "OPENHWP_TEXT_SHORTER"},
            "openhwp": {"status": "PASS"},
            "analysis": {
                "coverage_blockers": ["PARTIAL:tables"],
                "next_decoder_targets": [{"tag_id": 77, "tag_name": "TABLE", "count": 2}],
            },
        },
        {
            "category": "A",
            "comparison": {"python_hwpx_text_equal": False, "python_hwpx_roundtrip_status": "FAIL", "risk": ""},
            "openhwp": {"status": "FAIL"},
            "analysis": {
                "coverage_blockers": ["PARTIAL:tables"],
                "next_decoder_targets": [{"tag_id": 19, "tag_name": "FACE_NAME", "count": 3}],
            },
        },
    ]

    result = audit.aggregate(rows)

    assert result["sample_count"] == 2
    assert result["python_hwpx_text_equal_count"] == 1
    assert result["python_hwpx_roundtrip_pass_count"] == 1
    assert result["openhwp_pass_count"] == 1
    assert result["openhwp_fail_count"] == 1
    assert result["openhwp_text_shorter_count"] == 1
    assert result["coverage_blockers"] == {"PARTIAL:tables": 2}
    assert result["next_decoder_targets"][0] == {"tag": "19:FACE_NAME", "count": 3}
