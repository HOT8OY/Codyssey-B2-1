import argparse

from pathlib import Path


# 기본값
DEFAULT_DATA_DIR = Path("data") # 상대 경로 -> '명령을 실행한 위치' 기준의 data 폴더



# ===========================================================================
# 3. argparse 설정
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    """명령줄 인자를 해석할 파서(설계도)를 만듦."""
    parser = argparse.ArgumentParser(
        prog = f"python -m {__package__}",
        description = "나만의 용동 기입장 - 파일 기반 콘솔 가계부",
        epilog = f"각 명령의 자세한 사용법: python -m {__package__} <명령> --help",
    )

    # 1. 전역 옵션 (--data-dir) 추가
    parser.add_argument(
        "--data-dir",
        type = Path,
        default = DEFAULT_DATA_DIR,
        help = "데이터 저장 폴더 (기본: ./data)"
    )

    parser.add_argument(
        "--verbose",
        action = "store_true", # 옵션을 쓰면 True, 안 쓰면 False
        help = "실행 로그를 화면에도 출력"
    )

    # 2. 서브커멘트 틀 (나중에 add, list 등을 추가할 자리)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<명령>")

    return parser





# ===========================================================================
# 4. 로깅 설정 / 실행 진입점
# ===========================================================================

def main(argv: list[str] | None = None) -> int:
    """프로그램 진입점 함수"""
    parser = build_parser()
    args = parser.parse_args(argv)
    # return dispatch(args)
    return 0
