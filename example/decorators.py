"""
decorators.py — 데코레이터 모음
================================
이 파일은 여러 함수에 공통으로 적용할 데코레이터를 정의합니다.
데코레이터란: 함수를 감싸서 앞뒤에 공통 기능을 추가하는 함수.
  예) @handle_errors 를 붙이면 모든 에러를 친절한 메시지로 바꿔줌.

[왜 분리하나요?]
  각 커맨드 함수마다 try/except 를 직접 쓰면 코드가 중복됩니다.
  데코레이터로 분리하면 한 곳에서만 관리하고, @handle_errors 한 줄로 적용합니다.
"""

import functools   # functools.wraps: 데코레이터 적용 후에도 원래 함수 이름/docstring 유지
import sys         # sys.exit: 오류 발생 시 프로그램을 특정 코드로 종료
import time        # time.perf_counter: 고정밀 실행 시간 측정


# ──────────────────────────────────────────
# 데코레이터 1: 예외 처리 (필수 요구사항)
# ──────────────────────────────────────────
def handle_errors(func):
    """
    함수 실행 중 발생하는 예외를 잡아서
    스택트레이스 대신 [오류] + [힌트] 형식으로 출력하는 데코레이터.

    미션 요구사항:
      - 오류는 스택트레이스 대신 원인 + 해결 힌트로 출력한다.
      - 정상 종료는 0, 오류 종료는 0이 아닌 값으로 종료한다.
    """
    # @functools.wraps(func): 이 줄이 없으면 func.__name__이 'wrapper'로 바뀝니다.
    # 붙이면 원래 함수의 이름과 docstring이 그대로 유지됩니다.
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # *args   : 위치 인자를 몇 개든 받음 (예: cmd_add() 에 인자가 없어도 OK)
        # **kwargs: 키워드 인자를 몇 개든 받음 (예: cmd_list(limit=5) 도 처리)
        # 덕분에 이 데코레이터를 인자 모양이 다른 어떤 함수에도 붙일 수 있습니다.
        try:
            # 원래 함수를 실행하고 결과를 그대로 반환
            return func(*args, **kwargs)

        except FileNotFoundError as e:
            # 파일이 없을 때 발생하는 에러
            print(f"\n[오류] 파일을 찾을 수 없습니다: {e.filename}")
            print(f"[힌트] 처음 실행이라면 data 폴더가 자동 생성됩니다. 다시 시도하세요.")
            sys.exit(1)   # 1: 오류 종료 코드 (0이 아닌 값 = 비정상 종료)

        except ValueError as e:
            # 잘못된 값이 들어왔을 때 (예: 금액에 문자 입력)
            print(f"\n[오류] 입력값이 올바르지 않습니다: {e}")
            print(f"[힌트] --help 옵션으로 올바른 입력 형식을 확인하세요.")
            sys.exit(1)

        except KeyboardInterrupt:
            # 사용자가 Ctrl+C 를 누른 경우 → 강제 종료
            print("\n\n[취소] 사용자가 입력을 취소했습니다.")
            sys.exit(0)   # 0: 정상 종료 (사용자 의도적 종료)

        except Exception as e:
            # 위에서 잡지 못한 모든 예외
            print(f"\n[오류] 예상치 못한 오류가 발생했습니다: {type(e).__name__}: {e}")
            print(f"[힌트] 입력값과 파일 상태를 확인한 후 다시 시도하세요.")
            sys.exit(1)

    return wrapper


# ──────────────────────────────────────────
# 데코레이터 2: 실행 시간 측정
# ──────────────────────────────────────────
def measure_time(func):
    """
    함수의 실행 시간을 측정해서 출력하는 데코레이터.
    대용량 데이터를 처리할 때 성능을 확인하는 데 유용합니다.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()          # 시작 시점 기록 (고정밀 타이머)
        result = func(*args, **kwargs)        # 원래 함수 실행
        elapsed = time.perf_counter() - start  # 경과 시간 계산
        print(f"[실행시간] {elapsed:.3f}초")   # 소수점 3자리까지 출력
        return result

    return wrapper
