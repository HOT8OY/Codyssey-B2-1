"""
decorators.py — 공통 관심사(cross-cutting concerns)를 분리하는 데코레이터 모음
==============================================================================

[데코레이터(decorator)란?]
"함수를 받아서, 기능을 덧붙인 새 함수를 돌려주는 함수"입니다.

    @timed
    def cmd_list(...):
        ...

위 코드는 아래와 '완전히 같은' 뜻입니다.

    def cmd_list(...):
        ...
    cmd_list = timed(cmd_list)   # 원래 함수를 감싼(wrap) 새 함수로 바꿔치기

[왜 쓰나요? — 공통 관심사의 분리]
add, list, search, summary ... 모든 명령에서 똑같이 필요한 일들이 있습니다.
  - 오류가 나면 스택트레이스 대신 [오류]/[힌트]로 출력하기
  - 언제 어떤 명령이 실행됐는지 로그 남기기
  - 실행 시간 재기
이걸 명령 함수마다 try/except, time.perf_counter()로 복붙하면
코드가 지저분해지고, 규칙을 바꿀 때 모든 함수를 고쳐야 합니다.
데코레이터로 빼두면 → 명령 함수는 '자기 일'에만 집중하고, 공통 기능은 한 곳에서 관리합니다.

[이 파일의 데코레이터]
  @handle_errors  : 예외 → 친절한 메시지 + 종료 코드(int)로 변환
  @log_execution  : 실행 시작/종료/실패를 로그에 기록
  @timed          : 실행 시간을 측정해 로그에 기록
"""

import logging
import sys
import time
from collections.abc import Callable
from functools import wraps

# ParamSpec, TypeVar: 데코레이터의 타입 힌트를 정확하게 쓰기 위한 도구 (Python 3.10+)
#   P = "원래 함수의 매개변수 목록 전체"
#   R = "원래 함수의 반환 타입"
# 이렇게 써두면 데코레이터를 씌운 뒤에도 IDE가 원래 함수의 매개변수를 정확히 알려줍니다.
from typing import ParamSpec, TypeVar

from .errors import AppError

P = ParamSpec("P")
R = TypeVar("R")

LOGGER_NAME = "budget_app"
logger = logging.getLogger(LOGGER_NAME)

# 종료 코드 약속 (운영체제/셸의 관례)
EXIT_OK = 0           # 정상 종료
EXIT_ERROR = 1        # 일반 오류
EXIT_INTERRUPTED = 130  # Ctrl+C로 중단 (128 + SIGINT 번호 2)


def print_error(message: str, hint: str = "") -> None:
    """오류를 '[오류] 원인 / [힌트] 해결 방법' 형태로 출력합니다.

    file=sys.stderr: 오류 메시지는 '표준 에러' 통로로 내보냅니다.
    정상 출력(stdout)과 분리해 두면, 예를 들어
        python -m budget_app list > out.txt
    처럼 결과를 파일로 저장할 때 오류 메시지가 섞이지 않습니다.
    """
    print(f"[오류] {message}", file=sys.stderr)
    if hint:
        print(f"[힌트] {hint}", file=sys.stderr)


def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    """예외를 잡아 친절한 메시지로 바꾸고, 종료 코드(int)를 돌려주는 데코레이터.

    감싸는 함수는 정상일 때 0(int)을 반환해야 합니다.
    예외가 발생하면 여기서 잡아서 [오류]/[힌트]를 출력하고 0이 아닌 값을 반환합니다.
    → 프로그램 어디서 에러가 나든 사용자에게 스택트레이스가 보이지 않습니다.
    """

    # @wraps(func): 감싼 함수(wrapper)가 원래 함수의 이름(__name__), 설명(__doc__)을
    # 그대로 물려받게 해줍니다. 이게 없으면 모든 함수 이름이 'wrapper'로 보여서
    # 로그나 디버깅 때 헷갈립니다.
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        # *args, **kwargs: "어떤 인자가 오든 전부 받아서 원래 함수에 그대로 넘긴다"
        try:
            return func(*args, **kwargs)

        # except는 위에서부터 순서대로 검사합니다. 구체적인 것 → 일반적인 것 순으로!
        except AppError as error:
            # 우리가 직접 던진 '예상된' 오류: 메시지와 힌트가 이미 준비되어 있음
            print_error(error.message, error.hint)
            return error.exit_code

        except KeyboardInterrupt:
            # 사용자가 Ctrl+C를 누름
            print("\n[중단] 사용자가 작업을 취소했습니다. 저장되지 않은 입력은 버려집니다.", file=sys.stderr)
            return EXIT_INTERRUPTED

        except EOFError:
            # input() 도중 입력이 끝남 (Ctrl+D, 또는 파이프 입력이 바닥남)
            print_error(
                "입력이 끝나서 작업을 계속할 수 없습니다.",
                "대화형 명령(add 등)은 터미널에서 직접 실행하세요.",
            )
            return EXIT_ERROR

        except OSError as error:
            # 파일 관련 오류 (권한 없음, 디스크 가득 참, 경로가 폴더가 아님 등)
            print_error(
                f"파일을 처리하는 중 문제가 발생했습니다: {error.strerror} ({error.filename})",
                "경로와 권한을 확인하세요. --data-dir 옵션으로 저장 위치를 바꿀 수 있습니다.",
            )
            return EXIT_ERROR

        except Exception as error:  # noqa: BLE001  (모든 예외를 잡는 건 '최후의 안전망'이라 의도적)
            # 예상하지 못한 버그. 스택트레이스는 화면 대신 '로그 파일'에만 남깁니다.
            # exc_info=True: 로그에 스택트레이스를 함께 기록하라는 옵션
            logger.debug("예상치 못한 오류", exc_info=True)
            print_error(
                f"예상치 못한 오류가 발생했습니다: {error}",
                "같은 문제가 반복되면 data 폴더의 app.log 파일을 확인하세요.",
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
            # 실패했다는 사실만 기록하고, 예외는 그대로 다시 던집니다(raise).
            # 예외를 '처리'하는 건 handle_errors의 일이기 때문입니다. (역할 분리)
            logger.warning("실행 실패: %s (%s: %s)", func.__name__, type(error).__name__, error)
            raise
        logger.info("실행 종료: %s", func.__name__)
        return result

    return wrapper


def timed(func: Callable[P, R]) -> Callable[P, R]:
    """함수 실행 시간을 측정해 로그에 남기는 데코레이터."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # perf_counter(): 시간 '간격'을 재는 데 가장 정밀한 시계
        # (time.time()은 시스템 시계가 바뀌면 값이 튈 수 있음)
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            # finally: 성공하든 예외가 나든 '항상' 실행됩니다.
            elapsed = time.perf_counter() - start
            logger.info("소요 시간: %s %.3f초", func.__name__, elapsed)

    return wrapper
