# 삭제된 코드 목록

저장소에서 의도적으로 제거한 코드의 기록이다. 이력은 재작성하지 않으므로 아래 "마지막으로 존재한 커밋"에서
`git checkout <커밋> -- <경로>` 로 복원할 수 있다. 삭제 전에는 호출처를 확인하고 이 표에 먼저 적는다.

## 2026-10-16 — P3 범위 밖 제거 (건설 물가 PDF 파서)

HWPX 읽기·쓰기·서식 채움과 무관한 KPI/KPRC 물가 PDF 파서 묶음. 묶음 밖에서 import 하는 곳은 없었다
(이 저장소와 orchestrator 및 로컬의 다른 저장소 전체에서 0곳). orchestrator 에는 대응 기능이 없고,
소비처가 생기면 아래 기준 커밋에서 가져온다(미리 복사하지 않는다).

| 삭제 경로 | 줄 수 | 하던 일 | 사유 | 마지막으로 존재한 커밋 |
|---|---|---|---|---|
| scripts/kpi_parse.py | 861 | kpi.or.kr 종합물가정보 PDF 파서 | HWPX 범위 밖, 호출처 0 | 4756a31 |
| scripts/kpi_parse_test.py | 847 | 위 파서 회귀 검증(독립 실행형) | 위 파서 전용 | 4756a31 |
| scripts/kpi_quality_report.py | 415 | KPI 파싱 결과 품질 리포트 | 위 파서 전용 | 4756a31 |
| scripts/kprc_parse.py | 236 | kprc.or.kr 주요자재 가격 PDF 파서 | HWPX 범위 밖, 호출처 0 | 4756a31 |
| scripts/kprc_batch_parse.py | 521 | KPRC PDF 배치 파서 | HWPX 범위 밖, 호출처 0 | 4756a31 |
| scripts/pdf_batch_parse.py | 653 | 수집 PDF 전수 스캔·파싱 배치 실행기 | HWPX 범위 밖, 호출처 0 | 4756a31 |

함께 정정한 곳(동작 변경 없음):
- `scripts/ops/audit_hwpx_gate_infrastructure_health.py` — `fitz` 설명에서 삭제된 파일 언급 제거.
  `fitz`(pymupdf) 요구사항은 `scripts/hwpx/web_office/hancom_layout_refresh.py` 가 계속 쓰므로 유지.
- `scripts/hwpx/production_adapters/source_extractor_adapters.py` — 주석의 삭제된 파서 언급 정정.
  KPRC/PDF 어댑터 스텁(`NotImplementedError`)과 계약 시험은 그대로.

참고: `data/reports/hwpx_repo_inventory_classification/*.json` 은 삭제 전 기준 스냅샷이다(재생성은 문서 정리 단계에서).
