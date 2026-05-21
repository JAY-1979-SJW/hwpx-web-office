"""
감리서류 수집 공통 로거 설정.

사용법:
    from collect_logger import get_logger
    log = get_logger("collect_v8")
    log.info("서식 수집 시작")

로그 위치:
    ~/app/haehan-platform/logs/collect-YYYY-MM-DD.log  (날짜별 롤링, 30일 보관)
    콘솔: INFO 이상
    파일: DEBUG 이상
"""
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

LOG_DIR = Path.home() / "app/haehan-platform/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_FORMATTER_CONSOLE = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-5s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_FORMATTER_FILE = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d [%(levelname)-5s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """이름을 가진 로거 반환. 중복 호출해도 핸들러 중복 추가 안 함."""
    logger = logging.getLogger(f"collect.{name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 콘솔 핸들러: INFO 이상
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(_FORMATTER_CONSOLE)
    logger.addHandler(ch)

    # 날짜별 롤링 파일 핸들러: DEBUG 이상
    log_file = LOG_DIR / "collect.log"
    fh = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    fh.suffix = "%Y-%m-%d"
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FORMATTER_FILE)
    logger.addHandler(fh)

    logger.propagate = False
    return logger
