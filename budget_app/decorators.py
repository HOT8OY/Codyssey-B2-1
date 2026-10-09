"""
decorators.py — 공통 관심사(cross-cutting concerns)를 분리하는 데코레이터 모음

[이 파일의 데코레이터]
  @handle_errors  : 예외 → 메시지 + 종료 코드(int)로 변환
  @log_execution  : 실행 시작/종료/실패를 로그에 기록
  @timed          : 실행 시간을 측정해 로그에 기록
"""

import logging
import sys
import time
from collections.abc import Callable
from functools import wraps
from .errors import AppError

# ParamSpec, TypeVar: 데코레이터의 타입 힌트를 정확하게 쓰기 위한 도구
#   P = 원래 함수의 매개변수 목록 전체
#   R = 원래 함수의 반환 타입
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

LOGGER_NAME = "budget_app"
logger = logging.getLogger(LOGGER_NAME)

# 종료 코드 약속
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130  # Ctrl+C로 중단 (128 + SIGINT 번호 2)

def print_error(message: str, hint: str = "") -> None:
    """오류를 '[오류] 원인 / [힌트] 해결 방법' 형태로 출력.
    """
    print(f"[오류] {message}", file=sys.stderr)
    if hint:
        print(f"[힌트] {hint}", file=sys.stderr)

def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    """예외를 잡아 친절한 메시지로 바꾸고, 종료 코드(int)를 돌려주는 데코레이터.

    감싸는 함수는 정상일 떄 0을 반환.
    예외가 발생하면 여기서 잡아서 [오류]/[힌트]를 출력하고 0이 아닌 값을 반환.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        
        # 구체적 -> 일반적인것 순으로 검사
        except AppError as error:
            print_error(error.message, error.hint)
            return error.exit_code
        
        except KeyboardInterrupt: # Ctrl + C
            print("\n[중단] 사용자가 작업을 취소했습니다. 저장되지 않은 입력은 버려집니다.", file=sys.stderr)
            return EXIT_INTERRUPTED
        
        except EOFError: # Ctrl + D or 파이프 입력이 바닥남
            print_error(
                "입력이 끝나서 작업을 계속할 수 없습니다.",
                "대화형 명령(add 등)은 터미널에서 직접 실행하세요.",
            )
            return EXIT_ERROR
        
        except OSError as error: # 파일 관련 오류 (권한 없음, 디스크 가득 참, 경로가 폴더가 아님 등)
            print_error(
                f"파일을 처리하는 중 문제가 발생했습니다: {error.strerror} ({error.filename})",
                "경로와 권한을 확인하세요. --data-dir 옵션으로 저장 위치를 바꿀 수 있습니다."
            )
            return EXIT_ERROR
        
        except Exception as error: # 나머지 모든 예외
            # exc_info=True: 로그에 스택트레이스를 함께 기록하라는 옵션
            logger.debug("예상치 못한 오류", exc_info=True)
            print_error(
                f"예상치 못한 오류가 발생했습니다: {error}",
                "같은 문제가 반복되면 data 폴더의 app.log 파일을 확인하세요."
            )
            return EXIT_ERROR
    
    return wrapper

def log_execution(func: Callable[P, R]) -> Callable[P, R]:
    """함수 실행 시작/종료/실패를 로그에 남기는 데코레이터.

    로그는 기본적으로 data/app.log 파일에 쌓이고,
    --verbose 옵션을 주면 화면(stderr)에도 함께 보입니다. (cli.setup_logging 참고)
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.info("실행 시작: %s", func.__name__)
        try:
            result = func(*args, **kwargs)
        except Exception as error:
            # 실패했다는 사실만 기록 후 예외는 그대로 던짐.
            # 예외 처리는 handle_error에서.
            logger.warning("실행 실패: %s (%s: %s)", func.__name__, type(error).__name__, error)
            raise
        logger.info("실행 종료: %s", func.__name__)
        return result
    
    return wrapper

def timed(func: Callable[P, R]) -> Callable[P, R]:
    """함수 실행 시간을 측정해 로그에 남기는 데코레이터."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.info("소요 시간: %s %.3f초", func.__name__, elapsed)
    
    return wrapper