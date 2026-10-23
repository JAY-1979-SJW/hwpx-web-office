"""hancom_layout_refresh — 로드 시 한컴 재저장으로 좌표 데이터 정규화.

문서마다 저장된 레이아웃 데이터(lineseg·cellSz·표 선언높이)의 신선도가
제각각이라(구버전 저장·수기 편집 잔존) 좌표 재현 품질이 문서별로 흔들린다.
한컴 오피스(COM)가 설치돼 있으면 로드 시 문서를 한컴으로 열어 sandbox 에
재저장한다 — 한컴이 전체를 재조판해 모든 좌표를 현재 레이아웃으로 갱신
하므로, 추출기는 신선한 좌표를 그대로 그리면 된다(구조적 정확성).

- 표시(layout) 전용: 편집·저장 파이프라인은 계속 '원본'을 대상으로 한다.
  cellId 는 구조(섹션/표 문서순/행/열) 기반이라 재저장 후에도 동일.
- 원본 무수정: 산출물은 tmp/web_office_normalized/<sha16>.hwpx 에만.
- 내용해시 캐시: 같은 문서는 재실행하지 않는다.
- COM 은 서브프로세스에서 실행(타임아웃 격리 — API 서버 행 방지).
- 한컴 미설치/실패 시 원본 경로 반환(현행 동작 폴백).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR_ENV = "HWPX_WEB_OFFICE_NORMALIZED_DIR"
DISABLE_ENV = "HWPX_WEB_OFFICE_HANCOM_REFRESH"  # "0" 이면 비활성
TIMEOUT_SEC = 90


def _cache_dir(project_root: Path) -> Path:
    configured = os.environ.get(CACHE_DIR_ENV)
    d = Path(configured) if configured else project_root / "tmp" / "web_office_normalized"
    d.mkdir(parents=True, exist_ok=True)
    return d


def hancom_available() -> bool:
    if os.environ.get(DISABLE_ENV, "1") == "0":
        return False
    try:
        import winreg

        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "HWPFrame.HwpObject")
        return True
    except (ImportError, OSError):
        return False


def _resave_subprocess(src: Path, dst: Path) -> bool:
    """서브프로세스에서 한컴 COM 재저장 실행(행/크래시 격리)."""
    code = (
        "import sys, win32com.client\n"
        "src, dst = sys.argv[1], sys.argv[2]\n"
        "hwp = win32com.client.Dispatch('HwpFrame.HwpObject.2')\n"
        "try:\n"
        "    hwp.XHwpWindows.Item(0).Visible = False\n"
        "except Exception:\n"
        "    pass\n"
        "for name in ('FilePathCheckerModule', 'SecurityModule',\n"
        "             'FilePathCheckerModuleExample', 'AutomationModule'):\n"
        "    try:\n"
        "        if hwp.RegisterModule('FilePathCheckDLL', name):\n"
        "            break\n"
        "    except Exception:\n"
        "        continue\n"
        "try:\n"
        "    hwp.SetMessageBoxMode(0x00010000)\n"
        "except Exception:\n"
        "    pass\n"
        "ok = hwp.Open(src, '',\n"
        "              'forceopen:true;versionwarning:false;lock:false;')\n"
        "ok2 = hwp.SaveAs(dst, 'HWPX', '') if ok else False\n"
        "try:\n"
        "    hwp.XHwpDocuments.Close(False)\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    hwp.Quit()\n"
        "except Exception:\n"
        "    pass\n"
        "sys.exit(0 if (ok and ok2) else 1)\n"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", code, str(src), str(dst)],
            capture_output=True,
            timeout=TIMEOUT_SEC,
        )
        return r.returncode == 0 and dst.is_file()
    except (subprocess.TimeoutExpired, OSError):
        return False


def normalize_for_layout(source_path: Path, project_root: Path = PROJECT_ROOT) -> Path:
    """표시용 정규화 사본 경로 반환. 실패/비가용 시 원본 경로 그대로."""
    src = Path(source_path)
    if not src.is_file() or src.suffix.lower() != ".hwpx":
        return src
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    except OSError:
        return src
    out = _cache_dir(Path(project_root)) / f"norm_{digest}.hwpx"
    # 캐시 우선 — 빌드타임(한컴 있는 공장)에서 미리 정규화한 산출물은
    # 런타임에 한컴 없이도 그대로 쓴다(운영 아키텍처: 한컴은 공장에만).
    if out.is_file():
        return out
    if not hancom_available():
        return src
    if _resave_subprocess(src.resolve(), out.resolve()):
        return out
    # 실패 흔적 정리 후 원본 폴백
    try:
        if out.exists():
            out.unlink()
    except OSError:
        pass
    return src


TRUTH_DIR_ENV = "HWPX_WEB_OFFICE_TRUTH_DIR"


def _truth_dir(project_root: Path) -> Path:
    configured = os.environ.get(TRUTH_DIR_ENV)
    d = Path(configured) if configured else project_root / "tmp" / "web_office_truth"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pdf_subprocess(src: Path, dst_pdf: Path) -> bool:
    """서브프로세스에서 한컴 COM 으로 PDF 출력(행/크래시 격리)."""
    code = (
        "import sys, win32com.client\n"
        "src, dst = sys.argv[1], sys.argv[2]\n"
        "hwp = win32com.client.Dispatch('HwpFrame.HwpObject.2')\n"
        "try:\n"
        "    hwp.XHwpWindows.Item(0).Visible = False\n"
        "except Exception:\n"
        "    pass\n"
        "for name in ('FilePathCheckerModule', 'SecurityModule',\n"
        "             'FilePathCheckerModuleExample', 'AutomationModule'):\n"
        "    try:\n"
        "        if hwp.RegisterModule('FilePathCheckDLL', name):\n"
        "            break\n"
        "    except Exception:\n"
        "        continue\n"
        "try:\n"
        "    hwp.SetMessageBoxMode(0x00010000)\n"
        "except Exception:\n"
        "    pass\n"
        "ok = hwp.Open(src, '',\n"
        "              'forceopen:true;versionwarning:false;lock:false;')\n"
        "ok2 = hwp.SaveAs(dst, 'PDF', '') if ok else False\n"
        "try:\n"
        "    hwp.XHwpDocuments.Close(False)\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    hwp.Quit()\n"
        "except Exception:\n"
        "    pass\n"
        "sys.exit(0 if (ok and ok2) else 1)\n"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", code, str(src), str(dst_pdf)],
            capture_output=True,
            timeout=TIMEOUT_SEC,
        )
        return r.returncode == 0 and dst_pdf.is_file()
    except (subprocess.TimeoutExpired, OSError):
        return False


def render_truth_pages(
    source_path: Path, project_root: Path = PROJECT_ROOT, width_px: int = 794
) -> Path | None:
    """한컴 실렌더 페이지 이미지 생성(내용해시 캐시) → 디렉터리 경로.

    '원본 그대로' 표시 모드의 배경: 한컴이 그린 페이지를 그대로 쓰므로
    화면은 정의상 원본과 동일하다. 편집은 좌표 오버레이가 담당.
    실패/미설치 시 None(로직 렌더 폴백). read-only, 원본 무수정.
    """
    src = Path(source_path)
    if not src.is_file():
        return None
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    except OSError:
        return None
    out_dir = _truth_dir(Path(project_root)) / digest
    done = out_dir / "DONE"
    # 캐시 우선 — 빌드타임에 생성한 실렌더 이미지는 한컴 없는 런타임에서도
    # 서빙한다(운영: 한컴은 공장에만, 산출물은 배포 캐시).
    if done.is_file():
        return out_dir
    if not hancom_available():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / "truth.pdf"
    if not pdf.is_file() and not _pdf_subprocess(src.resolve(), pdf.resolve()):
        return None
    try:
        import fitz

        doc = fitz.open(str(pdf))
        for i, page in enumerate(doc):
            z = float(width_px) / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z))
            pix.save(str(out_dir / f"p{i + 1}.png"))
        (out_dir / "DONE").write_text(str(doc.page_count), encoding="ascii")
        return out_dir
    except Exception:  # ruff: ignore[blind-except] — fitz(C 확장) 예외 표면이 넓음, 실패 시 로직 렌더 폴백(None)
        return None


def _detect_grid(png_path: Path):
    """실렌더 PNG 에서 표 격자선(가로/세로) 픽셀 좌표 검출."""
    import numpy as np
    from PIL import Image

    im = np.asarray(Image.open(png_path).convert("L"))
    dark = im < 176

    def cluster(idx):
        out = []
        for v in idx:
            if out and v - out[-1][-1] <= 2:
                out[-1].append(v)
            else:
                out.append([v])
        return [sum(g) / len(g) for g in out]

    ys = cluster([y for y, v in enumerate(dark.mean(axis=1)) if v > 0.06])
    xs = cluster([x for x, v in enumerate(dark.mean(axis=0)) if v > 0.06])
    return ys, xs


def _snap(v: float, lines: list[float], tol: float) -> float:
    if not lines:
        return v
    srt = sorted(lines, key=lambda t: abs(v - t))
    best = srt[0]
    d = abs(v - best)
    if d <= tol:
        return best
    # 장거리 스냅 — 누적 드리프트(수십 px)로 톨러런스를 벗어났지만
    # 두 번째 후보보다 확연히 가까우면(모호성 없음) 흡착한다.
    second = abs(v - srt[1]) if len(srt) > 1 else 1e9
    if d <= 25.0 and second - d >= 12.0:
        return best
    return v


def _has_border(b: dict) -> bool:
    bd = b.get("border") or {}
    return any(bd.get(k, "none") != "none" for k in ("l", "r", "t", "b"))


def _group_shift(gboxes: list[dict], ys: list[float], xs: list[float]) -> tuple[float, float]:
    """표 그룹의 계통 이동(dy/dx)을 근접선 오프셋의 중앙값으로 투표한다."""
    dys, dxs = [], []
    for b in gboxes:
        if not _has_border(b):
            continue
        for e in (b["y"], b["y"] + b["h"]):
            dd = min((t - e for t in ys), key=abs)
            if abs(dd) <= 40:
                dys.append(dd)
        for e in (b["x"], b["x"] + b["w"]):
            dd = min((t - e for t in xs), key=abs)
            if abs(dd) <= 40:
                dxs.append(dd)
    shift_y = sorted(dys)[len(dys) // 2] if len(dys) >= 4 else 0.0
    shift_x = sorted(dxs)[len(dxs) // 2] if len(dxs) >= 4 else 0.0
    return shift_y, shift_x


def _align_table_groups(boxes: list[dict], ys: list[float], xs: list[float]) -> bool:
    """1단: 표 단위 정합등록 — 페이지 안에서도 표마다 흐름 누적 오차가
    달라(위 표 0px·아래 표 20px 등) 페이지 단일 보정으론 부족하다.
    cellId 의 표 접두(cell_t_sX_TTT)로 묶어 표별 계통 이동(dy/dx)을
    투표·제거한 뒤 개별 스냅한다."""
    changed = False
    groups: dict[str, list[dict]] = {}
    for b in boxes:
        cid = b.get("cellId") or ""
        key = cid.rsplit("_r", 1)[0] if "_r" in cid else "_"
        groups.setdefault(key, []).append(b)
    for gboxes in groups.values():
        shift_y, shift_x = _group_shift(gboxes, ys, xs)
        if abs(shift_y) > 1.0 or abs(shift_x) > 1.0:
            for b in gboxes:
                b["y"] = round(b["y"] + shift_y, 1)
                b["x"] = round(b["x"] + shift_x, 1)
            changed = True
    return changed


def _snap_bordered_boxes(
    boxes: list[dict], ys: list[float], xs: list[float], tol_y: float, tol_x: float
) -> bool:
    """테두리 있는 셀만 개별 스냅 — 보이지 않는 셀은 배경에 선이 없어
    흡착 대상이 아니며(근사 클릭 타깃으로 충분), 잘못 끌리면 해롭다."""
    changed = False
    for b in boxes:
        if not _has_border(b):
            continue
        y0 = _snap(b["y"], ys, tol_y)
        y1 = _snap(b["y"] + b["h"], ys, tol_y)
        x0 = _snap(b["x"], xs, tol_x)
        x1 = _snap(b["x"] + b["w"], xs, tol_x)
        if y1 - y0 > 4 and x1 - x0 > 4:
            if (y0, y1 - y0, x0, x1 - x0) != (b["y"], b["h"], b["x"], b["w"]):
                b["y"], b["h"] = round(y0, 1), round(y1 - y0, 1)
                b["x"], b["w"] = round(x0, 1), round(x1 - x0, 1)
                changed = True
    return changed


def _refit_grid_cells(boxes: list[dict], ys: list[float], xs: list[float]) -> bool:
    """격자칸 재봉합 — 스냅 후에도 박스 '내부'를 격자선이 관통하면(변이
    서로 다른 칸의 선에 붙은 오정렬) 박스 중심을 감싸는 실제 격자칸으로
    재봉합한다.

    안전장치(회귀 수리) — ys/xs 는 페이지 폭 전체 기준 암선 검출이라 이
    셀과 무관한 다른 표·구분선까지 "내부 선"으로 잡을 수 있다. 서명란처럼
    원래 큰(병합·장문단) 셀이 194px→85px 로 잘못 축소되는 사고가 실사례로
    확인됨 — 축소가 30%를 넘거나(원본 대부분을 삭제) 결과 칸이 지나치게
    작아지면(min 20px, 표 안 텍스트 줄 높이 미만) 재봉합을 적용하지
    않는다(원본 박스 유지가 항상 더 안전)."""
    changed = False
    for b in boxes:
        if not b.get("cellId"):
            continue
        y0, y1 = b["y"], b["y"] + b["h"]
        x0, x1 = b["x"], b["x"] + b["w"]
        in_y = [t for t in ys if y0 + 4 < t < y1 - 4]
        in_x = [t for t in xs if x0 + 4 < t < x1 - 4]
        if not in_y and not in_x:
            continue
        cyc, cxc = (y0 + y1) / 2, (x0 + x1) / 2
        if in_y:
            lo = max((t for t in ys if t <= cyc), default=None)
            hi = min((t for t in ys if t >= cyc), default=None)
            new_h = (hi - lo) if (lo is not None and hi is not None) else 0
            if (
                lo is not None
                and hi is not None
                and new_h > 8
                and new_h >= 20
                and new_h >= 0.7 * b["h"]
            ):
                b["y"], b["h"] = round(lo, 1), round(new_h, 1)
                changed = True
        if in_x:
            lo = max((t for t in xs if t <= cxc), default=None)
            hi = min((t for t in xs if t >= cxc), default=None)
            new_w = (hi - lo) if (lo is not None and hi is not None) else 0
            if (
                lo is not None
                and hi is not None
                and new_w > 8
                and new_w >= 20
                and new_w >= 0.7 * b["w"]
            ):
                b["x"], b["w"] = round(lo, 1), round(new_w, 1)
                changed = True
    return changed


def _row_pair_base_shared(boxes0: list[dict], boxes1: list[dict]) -> tuple[float, float, float]:
    """실제 테두리로 스냅된 쪽(더 신뢰) 경계를 우선 채택 — 겹치는 그 변
    (위 행의 아래쪽 / 아래 행의 위쪽)에 정확히 테두리가 있는 경우만 "그
    변이 실측됨"으로 인정한다(그 칸에 다른 변 테두리만 있는 경우까지
    신뢰하면 안 됨). (bottom0, top1, shared) 반환."""
    bottom0 = max(b["y"] + b["h"] for b in boxes0)
    top1 = min(b["y"] for b in boxes1)
    bordered0 = [
        b
        for b in boxes0
        if (b.get("border") or {}).get("b", "none") != "none" and b["y"] + b["h"] == bottom0
    ]
    bordered1 = [
        b for b in boxes1 if (b.get("border") or {}).get("t", "none") != "none" and b["y"] == top1
    ]
    if bordered0 and not bordered1:
        shared = bottom0
    elif bordered1 and not bordered0:
        shared = top1
    else:
        shared = (bottom0 + top1) / 2
    return bottom0, top1, shared


def _stitch_one_row_pair(
    boxes0: list[dict], boxes1: list[dict], lines: list[dict], orig_box_pos: dict
) -> bool:
    """인접한 두 행(boxes0=위, boxes1=아래)의 겹침을 실측 경계로 봉합.

    docstring 은 _stitch_adjacent_rows 참조 (판정 로직·안전장치 동일)."""
    bottom0, top1, shared = _row_pair_base_shared(boxes0, boxes1)
    overlap = bottom0 - top1
    if overlap <= 0.3:
        return False  # 겹침 없음(또는 오차 이내) — 손대지 않음
    # 내용 수용 하한/상한 — 순수 기하 절충(중점/테두리)만으로 자르면, 위
    # 행 글자의 실제 줄 높이(line.y+line.h, 박스 안 상단 여백까지 포함한
    # 실측값)보다 짧게 잘려 글자 아래쪽(받침)이 다시 잘리는 결함이
    # 실사례로 확인됨(제목행 자체 재봉합 직후). 위 행은 자기 줄의 실제
    # 하단 아래로는 절대 안 자르고(하한), 아래 행도 자기 줄의 실제 상단
    # 위로는 안 자른다(상한) — 둘 다 만족 못 하면 위 행 보호를 우선
    # (겹침이 지나치게 큰 극단 사례만 잔여 겹침 허용, 글자 잘림보다
    # 안전). 줄(lines)은 이 시점까지 아직 안 옮겨져 있다(박스-줄 정합
    # 동기화는 별도 단계에서 처리) — 원본 대비 박스가 이미 이동한
    # 만큼(dy)을 여기서 즉석 보정해 비교해야 정확한 하한/상한이 나온다.
    cids0 = {b.get("cellId") for b in boxes0}
    cids1 = {b.get("cellId") for b in boxes1}
    dy0 = boxes0[0]["y"] - orig_box_pos[id(boxes0[0])][1] if id(boxes0[0]) in orig_box_pos else 0.0
    dy1 = boxes1[0]["y"] - orig_box_pos[id(boxes1[0])][1] if id(boxes1[0]) in orig_box_pos else 0.0
    content_bottom0 = max(
        (l["y"] + l["h"] + dy0 for l in lines if l.get("cellId") in cids0),
        default=None,
    )
    content_top1 = min((l["y"] + dy1 for l in lines if l.get("cellId") in cids1), default=None)
    if content_bottom0 is not None and shared < content_bottom0:
        shared = content_bottom0
    if content_top1 is not None and shared > content_top1 >= (content_bottom0 or 0):
        shared = content_top1
    # 안전장치 — 여러 행 쌍을 순차 처리하다 보면(예: r8-r9 처리 직후
    # r9-r10 처리) 앞선 조정이 뒤 계산의 전제를 바꿔, shared 가 어느 한쪽
    # 박스의 원래 top 보다 위로 밀려 음수 높이(박스 상하 뒤집힘)를 만드는
    # 사고가 실사례로 확인됨(r9 박스 height=-29.6). 결과가 두 박스
    # 모두에 유효한 양수 높이를 줄 때만 적용하고, 아니면 이 쌍은
    # 건드리지 않는다(잔여 겹침이 뒤집힌 박스보다 안전).
    new_h0 = {id(b): shared - b["y"] for b in boxes0}
    new_h1 = {id(b): b["y"] + b["h"] - shared for b in boxes1}
    if not (all(h >= 0.5 for h in new_h0.values()) and all(h >= 0.5 for h in new_h1.values())):
        return False
    for b in boxes0:
        if b["y"] + b["h"] > shared:
            b["h"] = round(new_h0[id(b)], 1)
    for b in boxes1:
        if b["y"] < shared:
            b["h"] = round(new_h1[id(b)], 1)
            b["y"] = round(shared, 1)
    return True


def _stitch_adjacent_rows(boxes: list[dict], lines: list[dict], orig_box_pos: dict) -> bool:
    """인접 행 겹침 봉합 — 앞 단계들(계통이동·개별스냅·재봉합)은 박스를
    각자 독립적으로 실제 격자선에 흡착한다. 테두리 없는 행(예: 제목 문단
    행)은 어떤 단계에서도 안 건드려지고, 테두리 있는 이웃 행만 개별
    스냅되면 — "행 N 하단 = 행 N+1 상단"이라는, coord_table.py 원 계산이
    항상 지키던 불변식이 스냅 후에 깨질 수 있다(실사례: fx_metadata_form
    제목행이 사진 위에서 그 아래 빈 행과 11px 겹쳐, 제목 글자 아래쪽이
    이웃 행의 흰 편집 상자에 가려 보이는 결함 — 사진 배경을 켰을 때는
    사진 픽셀 자체가 보여 안 드러났지만(2026-07-24 사진 배경 제거 이후)
    처음 드러남). 표별로 행 순서를 복원해 연속된 두 행이 겹치면(진짜
    겹침만 — 틈은 손대지 않음, 회귀 위험 최소화) 테두리로 실측된 쪽
    경계에 다른 쪽을 붙인다."""
    changed = False
    row_re = re.compile(r"_r(\d+)_c\d+$")
    tbl_groups: dict[str, dict[int, list[dict]]] = {}
    for b in boxes:
        cid = b.get("cellId") or ""
        m = row_re.search(cid)
        if not m:
            continue
        key = cid[: m.start()]
        tbl_groups.setdefault(key, {}).setdefault(int(m.group(1)), []).append(b)
    for rows in tbl_groups.values():
        row_idxs = sorted(rows)
        for i in range(len(row_idxs) - 1):
            r0, r1 = row_idxs[i], row_idxs[i + 1]
            if r1 != r0 + 1:
                continue  # 병합으로 행 번호가 안 이어지면 스킵(안전)
            if _stitch_one_row_pair(rows[r0], rows[r1], lines, orig_box_pos):
                changed = True
    return changed


def _sync_lines_to_boxes(boxes: list[dict], lines: list[dict], orig_box_pos: dict) -> bool:
    """박스-줄 정합 — 위 스냅 단계들이 옮긴 만큼(칸별 dx,dy) 그 칸 소속
    텍스트 줄(lines)도 같이 옮긴다. 병합/조각(frag)으로 한 cellId 에
    박스가 여럿이면 첫 박스 기준으로만 이동량을 잡는다(과도한 복잡화
    방지 — 조각 이동량 차는 페이지 경계뿐이라 실무상 첫 박스로 충분)."""
    changed = False
    delta_by_cell: dict[str, tuple[float, float]] = {}
    for b in boxes:
        cid = b.get("cellId")
        if not cid or cid in delta_by_cell:
            continue
        orig = orig_box_pos.get(id(b))
        if orig is None:
            continue
        dx, dy = b["x"] - orig[0], b["y"] - orig[1]
        if abs(dx) > 0.05 or abs(dy) > 0.05:
            delta_by_cell[cid] = (dx, dy)
    if delta_by_cell:
        for l in lines:
            cid = l.get("cellId")
            d = delta_by_cell.get(cid) if cid else None
            if d:
                l["x"] = round(l["x"] + d[0], 1)
                l["y"] = round(l["y"] + d[1], 1)
                changed = True
    return changed


def _page_truth_ok(boxes: list[dict], ys: list[float]) -> bool:
    """페이지별 정합 판정 — 총 쪽수가 같아도 중간 페이지 경계가 달라
    특정 페이지 내용이 통째로 어긋날 수 있다(예: 우리 p6 내용이 한컴 p6
    그림과 다름). 스냅 후 잔여 중위가 크면 그 페이지만 배경 사용을
    차단(False) → 뷰어가 해당 페이지를 좌표 렌더로 그린다(정합
    페이지=원본 픽셀, 아닌 페이지=정직한 자체 렌더)."""
    res = []
    for b in boxes:
        if not _has_border(b):
            continue
        res.extend(min(abs(e - t) for t in ys) for e in (b["y"], b["y"] + b["h"]))
    if len(res) >= 8:
        res.sort()
        if res[len(res) // 2] > 3.0:
            return False
    return True


def _prepare_page_grid(
    tdir: Path, pi: int, pd: dict
) -> tuple[list[float], list[float], dict] | None:
    """이 페이지에 스냅을 적용할 수 있는지 확인하고 (ys, xs, orig_box_pos)를
    반환한다. 배경 PNG 가 없거나 격자 검출이 실패/희박하면 None."""
    png = tdir / f"p{pi + 1}.png"
    if not png.is_file():
        return None
    try:
        ys, xs = _detect_grid(png)
    except Exception:  # ruff: ignore[blind-except] — numpy/PIL 예외 표면이 넓음, 이 페이지만 스냅 생략
        return None
    # 검출 신뢰 가드 — 격자선이 희박한 페이지(그래프·목록 등)는 스냅
    # 생략(무관한 선에 끌려 오정렬되는 것 방지).
    if len(ys) < 4 or len(xs) < 3:
        return None
    # 박스 원위치 스냅샷 — 아래 스냅 단계들은 박스(클릭 타깃/테두리)만
    # 옮기고 그 칸의 텍스트 줄(lines)은 그대로 둔다. 박스만 실제 사진
    # 격자에 맞춰 수십 px 이동하면, 줄은 옛 위치에 남아 칸 경계와 줄
    # 위치가 어긋나 옆 칸(덜 이동한 칸) 쪽으로 글자가 침범해 보이는
    # 결함이 생긴다(실사례: fx_metadata_form "귀하" 칸이 +19px
    # 이동했는데 그 줄은 안 옮겨져 왼쪽 이웃 칸 글자와 겹쳐 보임). 스냅이
    # 끝난 뒤 칸별 이동량(dx,dy)만큼 그 칸 소속 줄도 같이 옮겨 박스-줄
    # 정합을 유지한다.
    orig_box_pos = {id(b): (b["x"], b["y"]) for b in pd["boxes"] if b.get("cellId")}
    return ys, xs, orig_box_pos


def _resolve_ready_truth_dir(layout: dict, source_path: Path, project_root: Path) -> Path | None:
    """truth 캐시가 있고 한컴 쪽수가 우리 쪽수와 일치하면 tdir 을 반환.

    한컴 쪽수와 우리 쪽수가 다르면 배경-오버레이 페이지 대응 자체가
    어긋나므로 스냅하지 않는다(뷰어는 이 신호로 배경 모드를 차단하고
    좌표 렌더를 유지한다)."""
    src = Path(source_path)
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    except OSError:
        return None
    tdir = _truth_dir(Path(project_root)) / digest
    if not (tdir / "DONE").is_file():
        return None
    try:
        hancom_pages = int((tdir / "DONE").read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    if hancom_pages != len(layout.get("pagesDetail", [])):
        return None
    return tdir


def snap_layout_to_truth(
    layout: dict,
    source_path: Path,
    project_root: Path = PROJECT_ROOT,
    tol_y: float = 12.0,
    tol_x: float = 6.0,
) -> bool:
    """편집 오버레이(셀 박스)를 실렌더 배경의 실제 격자선에 스냅.

    배경은 한컴 픽셀, 오버레이는 우리 좌표라 수 px~수십 px 어긋날 수 있다
    (클릭 타깃 오정렬). 정답 이미지에서 격자선을 검출해 각 박스 변을 가장
    가까운 실제 선에 흡착시키면 정합 오차가 구조적으로 소멸한다.
    truth 캐시가 있을 때만 동작(없으면 False — 무변화)."""
    tdir = _resolve_ready_truth_dir(layout, source_path, project_root)
    if tdir is None:
        return False

    changed = False
    for pi, pd in enumerate(layout.get("pagesDetail", [])):
        pd["truthOk"] = True  # 기본: 배경 사용(측정 실패 페이지 포함)
        prepared = _prepare_page_grid(tdir, pi, pd)
        if prepared is None:
            continue
        ys, xs, orig_box_pos = prepared

        if _align_table_groups(pd["boxes"], ys, xs):
            changed = True
        if _snap_bordered_boxes(pd["boxes"], ys, xs, tol_y, tol_x):
            changed = True
        if _refit_grid_cells(pd["boxes"], ys, xs):
            changed = True
        if _stitch_adjacent_rows(pd["boxes"], pd["lines"], orig_box_pos):
            changed = True
        if _sync_lines_to_boxes(pd["boxes"], pd["lines"], orig_box_pos):
            changed = True

        pd["truthOk"] = _page_truth_ok(pd["boxes"], ys)
    return changed


def get_row_scale(source_path: Path, project_root: Path = PROJECT_ROOT) -> float:
    """공장 캘리브레이션 배율 조회(truth 캐시의 calib.json, 없으면 1.0)."""
    src = Path(source_path)
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
        import json as _json

        cj = _truth_dir(Path(project_root)) / digest / "calib.json"
        if cj.is_file():
            v = float(_json.loads(cj.read_text(encoding="utf-8")).get("rowScale", 1.0))
            if 0.85 <= v <= 1.15:
                return v
    except (OSError, ValueError, TypeError):
        pass
    return 1.0


def calibrate_row_scale(source_path: Path, project_root: Path = PROJECT_ROOT) -> float | None:
    """±1쪽 캘리브레이션 — 한컴 실제 쪽수에 우리 쪽수가 일치하는 행높이
    배율 k 를 1.0 에서 가까운 순으로 탐색해 truth 캐시에 저장한다.

    공장(한컴 산출물 보유) 공정: 축소는 추출기에서 내용 하한이 지켜지므로
    물림을 만들지 않고, 확대는 잘림이 없다. 일치 k 가 없으면 저장 안 함
    (기본 1.0 유지 — 캘리브레이션 불가 문서로 기록)."""
    src = Path(source_path)
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    except OSError:
        return None
    tdir = _truth_dir(Path(project_root)) / digest
    done = tdir / "DONE"
    if not done.is_file():
        return None
    try:
        hancom_pages = int(done.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    # 정규화 사본이 있으면 그것으로(로더와 동일 경로), 없으면 원본으로 탐색
    norm = _cache_dir(Path(project_root)) / f"norm_{digest}.hwpx"
    target = norm if norm.is_file() else src
    try:
        from .coordinate_layout import extract as _extract
    except ImportError:
        from coordinate_layout import extract as _extract
    cands = [1.0]
    for step in (0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12):
        cands.extend([1.0 - step, 1.0 + step])
    for k in cands:
        try:
            if _extract(str(target), row_scale=k).get("pages") == hancom_pages:
                import json as _json

                (tdir / "calib.json").write_text(
                    _json.dumps({"rowScale": round(k, 4)}), encoding="utf-8"
                )
                return k
        except Exception:  # ruff: ignore[blind-except] — 배율 후보 하나가 깨져도 나머지 후보 탐색 계속
            continue
    return None


if __name__ == "__main__":
    p = normalize_for_layout(Path(sys.argv[1]))
    print(str(p))
