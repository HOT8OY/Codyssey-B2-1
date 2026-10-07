"""
__main__.py — 프로그램 실행 진입점
===================================

[python -m 패키지명 은 어떻게 동작하나요?]
    python -m budget_app list
위 명령을 실행하면 파이썬은
  1. 현재 폴더에서 budget_app 이라는 '패키지(폴더)'를 찾고
  2. 그 안의 __main__.py 파일을 실행합니다. (← 바로 이 파일)
  3. 이때 __name__ 변수의 값은 "__main__"이 됩니다.

[왜 `from cli import main`이 아니라 `from .cli import main`인가요?]
`python -m`으로 실행하면 이 파일은 패키지의 '일부'로 실행됩니다.
  - from cli import main  → "파이썬 검색 경로 어딘가에 있는 cli 모듈"을 찾음 → 보통 실패 (ModuleNotFoundError)
  - from .cli import main → "같은 패키지 안의 cli.py" (점 = 현재 패키지) → 정확히 찾음
"""

# sys.exit(코드): 프로그램을 끝내면서 운영체제에 종료 코드를 알려줍니다.
#   0 = 정상, 0이 아님 = 오류  (셸에서 `echo $?`로 확인 가능)
import sys

from .cli import main

# "이 파일이 직접 실행될 때만" 아래 코드를 실행하라는 관용구입니다.
# (다른 파일에서 import 될 때는 실행되지 않음)
if __name__ == "__main__":
    # main()이 반환한 종료 코드를 sys.exit에 넘겨야 오류 시 0이 아닌 값으로 끝납니다.
    # main()만 호출하고 끝내면 오류가 나도 항상 0(정상)으로 종료되어 버립니다!
    sys.exit(main())
