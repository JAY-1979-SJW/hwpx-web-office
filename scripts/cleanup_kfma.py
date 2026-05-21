"""KFMA 수집 파일 정리 - 중복 및 폐지된 파일 처리"""
from pathlib import Path
import re

FIRE_DIR = Path.home() / "app/haehan-platform/storage/templates/inspection/소방시설법_시행규칙"

# 앱과 관련 없는 파일 목록 (제거 대상)
NOT_RELEVANT = [
    # 폐지된 구버전
    "KFMA____폐지___241201_소방시설등_자체점검_실시결과_보고서.hwp",
    "KFMA____폐지___자체점검_결과보고서_업무시행_지침_확정_관련_서류.hwp",
    "KFMA____일부폐지___2022_12_1_소방시설등_자체점검_실시결과_보고서_및_점검표_양식.hwp",
    "KFMA____일부폐지____2022_12_1_소방시설_외관점검표_세대_점검용__양식_및_세대점검_.hwp",
    "KFMA____일부폐지____2022_12_1_소방시설_외관점검표_세대_점검용__양식_및_세대점검_.pdf",
    # 앱 무관 서식
    "KFMA__양식__일반_환불신청_서식.hwp",
    "KFMA__양식__일반_환불신청_서식.hwpx",
    "KFMA__양식__소민터_자체점검결과보고서_위임장_소민터_첨부_파일용_.hwp",
    "KFMA__양식___별지_제4호서식__다대상물_점검실적_상세내역서__점검능력_평가_.hwp",
    "KFMA__양식___별지_제4호서식__다대상물_점검실적_상세내역서__점검능력_평가_.pdf",
    "KFMA__양식___별지_제8호서식__소방시설관리업_기술개발투자비_확인서.hwpx",
    "KFMA__양식__중대재해처벌법_관련_서식_모음집.hwp",
]

# 중복 처리 (같은 이름으로 덮어쓰인 파일들 → 마지막 버전이 남아있음, 정리 불필요)

deleted = []
kept = []

files = list(FIRE_DIR.iterdir())
print(f"소방시설법_시행규칙/ 전체 파일: {len(files)}개")

for f in sorted(files):
    if f.name in NOT_RELEVANT:
        f.unlink()
        deleted.append(f.name)
        print(f"  삭제: {f.name}")
    else:
        kept.append(f.name)
        print(f"  유지: {f.name}")

print(f"\n삭제: {len(deleted)}건 / 유지: {len(kept)}건")

# 현재 유지되는 관련 파일 목록
print("\n=== 현행 유지 파일 ===")
for n in sorted(kept):
    p = FIRE_DIR / n
    kb = p.stat().st_size // 1024
    print(f"  {n} ({kb}KB)")
