"""
__main__.py — 패키지 진입점
=============================
이 파일이 있으면 `python -m budget_app` 으로 실행할 수 있습니다.

[왜 __main__.py가 필요한가?]
  Python에서 `python 파일.py` 로 실행하면 그 파일이 바로 실행됩니다.
  하지만 `python -m 패키지명` 으로 실행하려면
  패키지 폴더 안에 __main__.py 가 있어야 합니다.

  이 프로젝트에서는 budget_app 폴더 안의 __main__.py 가 아니라
  example 폴더를 직접 실행하므로:
    python -m example    (example 폴더 내의 __main__.py 실행)
  또는 example 폴더 안에서:
    python cli.py 로도 실행 가능합니다.
"""

from cli import main

# __name__ == "__main__": 이 파일이 직접 실행될 때만 True
# 다른 파일에서 import 될 때는 False → main()이 실행되지 않음
if __name__ == "__main__":
    main()
