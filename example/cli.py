"""
cli.py — CLI(Command Line Interface) 계층: 사용자 입출력 담당
==============================================================

[이 파일의 역할]
사용자와 '대화'하는 유일한 곳입니다.
  1. 명령어와 옵션 해석       (argparse)
  2. 대화형 입력 받기          (input)
  3. 서비스 호출               (services.BudgetService)
  4. 결과를 보기 좋게 출력      (print)

계산이나 저장 규칙은 여기 두지 않습니다. 그건 서비스/저장소의 일입니다.
"받아서 → 넘기고 → 보여준다"만 합니다.

[전체 흐름]
    python -m budget_app list --limit 3
          │
          ▼
    __main__.py ──► main(argv)
                     ├─ build_parser().parse_args()   : "list", limit=3 으로 해석
                     └─ dispatch(args)                : @handle_errors로 감싸짐
                          ├─ setup_logging()
                          ├─ BudgetService.from_data_dir()
                          └─ args.handler(args, service)  → cmd_list 실행
"""

import argparse
import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TypeVar

from .decorators import EXIT_OK, LOGGER_NAME, handle_errors, log_execution, print_error, timed
from .errors import ValidationError
from .models import (
    VALID_TYPES,
    MonthlySummary,
    Transaction,
    parse_amount,
    parse_category_name,
    parse_date,
    parse_month,
    parse_tags,
    parse_type,
)
from .services import CSV_COLUMNS, BudgetService

T = TypeVar("T")

# 타입 별칭: "명령 처리 함수"의 모양. (args, service)를 받아 종료 코드 int를 돌려줌
Handler = Callable[[argparse.Namespace, BudgetService], int]

DEFAULT_DATA_DIR = Path("data")  # 상대 경로 → '명령을 실행한 위치' 기준의 data 폴더
DEFAULT_LIST_LIMIT = 20
DEFAULT_TOP = 5


# ===========================================================================
# 1. 작은 도우미 함수들
# ===========================================================================


def argtype(parse: Callable[[str], T]) -> Callable[[str], T]:
    """models의 parse_xxx 함수를 argparse의 type= 으로 쓸 수 있게 바꿔주는 어댑터.

    argparse는 type= 함수가 argparse.ArgumentTypeError를 던지면 그 메시지를 보여주고
    종료 코드 2로 끝냅니다. 우리 함수는 ValidationError를 던지므로 '번역'이 필요합니다.

        parser.add_argument("--month", type=argtype(parse_month))
        → --month 2024-13 입력 시: "argument --month: 월 형식이 올바르지 않습니다 (YYYY-MM). 예: 2024-01"

    이렇게 하면 '옵션 방식'과 '대화형 방식'이 같은 검증 함수를 공유합니다.
    """

    def convert(text: str) -> T:
        try:
            return parse(text)
        except ValidationError as error:
            raise argparse.ArgumentTypeError(f"{error.message} {error.hint}".strip()) from None

    return convert


def parse_positive_int(text: str) -> int:
    """--limit, --top 처럼 1 이상의 정수여야 하는 옵션용."""
    try:
        value = int(text)
    except ValueError:
        raise ValidationError(f"정수가 아닙니다: '{text}'", "예: 10") from None
    if value < 1:
        raise ValidationError("1 이상의 정수여야 합니다.", "예: 10")
    return value


def ask(prompt: str, parse: Callable[[str], T], *, default: str | None = None) -> T:
    """올바른 값이 들어올 때까지 반복해서 입력받는 함수. (대화형 입력의 핵심)

    - parse: 입력 문자열을 검증/변환하는 함수 (실패 시 ValidationError)
    - default: 그냥 엔터를 쳤을 때 쓸 기본값

    잘못 입력하면 '그 항목만' 다시 묻습니다. (처음부터 다시 입력할 필요 없음)
    """
    while True:  # 무한 반복 → return을 만나야 빠져나감
        raw = input(prompt).strip()
        if not raw and default is not None:
            raw = default
        try:
            return parse(raw)
        except ValidationError as error:
            print_error(error.message, error.hint)
            # return하지 않았으므로 while문이 다시 돌아 같은 질문을 반복


def format_transaction(tx: Transaction) -> str:
    """거래 1건을 한 줄 문자열로 만듭니다.

    f-string 서식 지정자:
      {값:<9}   왼쪽 정렬, 최소 9칸
      {값:>10,} 오른쪽 정렬, 최소 10칸, 천 단위 쉼표 (15000 → "    15,000")
    """
    memo = tx.memo
    if tx.tags:
        memo = f"{memo} " + " ".join(f"#{t}" for t in tx.tags)
    return f"{tx.id} | {tx.date} | {tx.type:<7} | {tx.category:<10} | {tx.amount:>10,}원 | {memo.strip()}"


def print_transactions(rows: list[Transaction], empty_message: str) -> None:
    if not rows:
        print(empty_message)
        return
    for tx in rows:
        print(format_transaction(tx))
    print(f"(최신순 {len(rows)}건)")


# ===========================================================================
# 2. 명령 처리 함수들 (cmd_xxx)
# ===========================================================================
# 규칙:
#   - 모두 (args, service)를 받아 종료 코드(int)를 반환합니다. 정상이면 EXIT_OK(0).
#   - 문제가 생기면 return 1 대신 '예외를 던집니다'. → dispatch의 @handle_errors가 처리
#   - @log_execution, @timed 데코레이터로 실행 로그와 시간이 자동 기록됩니다.
#
# 데코레이터를 여러 개 쌓으면 '아래에서 위로' 감쌉니다.
#   @log_execution
#   @timed
#   def cmd_add(...)   →   cmd_add = log_execution(timed(cmd_add))
# ===========================================================================


@log_execution
@timed
def cmd_add(args: argparse.Namespace, service: BudgetService) -> int:
    """add: 대화형으로 거래를 하나 추가합니다."""
    print("새 거래를 입력합니다. (취소: Ctrl+C)")
    today = date.today().isoformat()  # 오늘 날짜 "2026-10-07"

    tx_date = ask(f"날짜(YYYY-MM-DD, 엔터={today}): ", parse_date, default=today)
    tx_type = ask("타입(income/expense): ", parse_type)

    print(f"  (등록된 카테고리: {', '.join(service.list_categories())})")
    # service.validate_category를 parse 함수로 넘김 → 등록되지 않은 카테고리면 재입력
    category = ask("카테고리: ", service.validate_category)

    amount = ask("금액(양수): ", parse_amount)
    memo = input("메모(선택): ").strip()
    tags = ask("태그(쉼표로 구분, 없으면 엔터): ", parse_tags)

    tx = service.add_transaction(
        date=tx_date, tx_type=tx_type, category=category, amount=amount, memo=memo, tags=tags
    )
    print(f"[저장 완료] id={tx.id}")
    return EXIT_OK


@log_execution
@timed
def cmd_list(args: argparse.Namespace, service: BudgetService) -> int:
    """list: 최신 거래 N건을 보여줍니다."""
    rows = service.list_recent(args.limit)
    print_transactions(rows, "[안내] 저장된 거래가 없습니다. 'add' 명령으로 추가해 보세요.")
    return EXIT_OK


@log_execution
@timed
def cmd_search(args: argparse.Namespace, service: BudgetService) -> int:
    """search: 조건에 맞는 거래를 최신순으로 보여줍니다."""
    matches = service.search(  # ← 아직 아무것도 읽지 않음! (제너레이터는 '요청할 때' 실행됨)
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
        tx_type=args.type,
        keyword=args.q,
        tag=args.tag,
    )
    rows = service.latest(matches, args.limit)  # ← 여기서 비로소 파일을 한 줄씩 읽기 시작
    print_transactions(rows, "[안내] 검색 결과가 없습니다.")
    return EXIT_OK


def print_summary(summary: MonthlySummary, top: int) -> None:
    """월별 요약 결과 출력. (계산은 서비스가 이미 끝냄)"""
    print(f"──── {summary.month} 월별 요약 ────")
    if not summary.has_data:
        print("데이터 없음")
    else:
        print(f"총 수입: {summary.total_income:,}원")
        print(f"총 지출: {summary.total_expense:,}원")
        print(f"잔액:   {summary.balance:,}원")

    if summary.budget is not None and summary.budget_usage is not None:
        print(f"예산:   {summary.budget:,}원 (사용률 {summary.budget_usage:.1f}%)")
        if summary.is_over_budget:
            over = summary.total_expense - summary.budget
            print(f"[경고] 예산을 {over:,}원 초과했습니다!")
        elif summary.budget_usage >= 80:
            print("[주의] 예산의 80% 이상을 사용했습니다.")

    top_items = summary.top_categories(top)
    if top_items:
        print(f"\n지출 TOP {top}")
        # enumerate(..., start=1): 1부터 번호 매기기
        for rank, (category, amount) in enumerate(top_items, start=1):
            print(f"{rank}) {category} {amount:,}원")


@log_execution
@timed
def cmd_summary(args: argparse.Namespace, service: BudgetService) -> int:
    """summary: 월별 수입/지출/잔액과 지출 TOP N, 예산 사용률을 보여줍니다."""
    print_summary(service.summarize(args.month), args.top)
    return EXIT_OK


@log_execution
@timed
def cmd_budget(args: argparse.Namespace, service: BudgetService) -> int:
    """budget set/get"""
    if args.budget_cmd == "set":
        budget = service.set_budget(args.month, args.amount)
        print(f"[저장 완료] {budget.month} 예산 {budget.amount:,}원")
    else:  # "get"
        found = service.get_budget(args.month)
        if found is None:
            print(f"[안내] {args.month} 예산이 설정되어 있지 않습니다.")
        else:
            print(f"{found.month} 예산: {found.amount:,}원")
    return EXIT_OK


@log_execution
@timed
def cmd_category(args: argparse.Namespace, service: BudgetService) -> int:
    """category add/list/remove

    이름을 옵션으로 주지 않으면 대화형으로 물어봅니다.
      category add          → "카테고리명: " 입력
      category add hobby    → 바로 추가
    """
    if args.category_cmd == "list":
        for name in service.list_categories():
            print(f"- {name}")

    elif args.category_cmd == "add":
        name = args.name or ask("카테고리명: ", parse_category_name)
        added = service.add_category(name)
        print(f"[저장 완료] category={added}")

    else:  # "remove"
        name = args.name or ask("삭제할 카테고리명: ", parse_category_name)
        moved = service.remove_category(name, replace_with=args.replace)
        if moved:
            print(f"[안내] 거래 {moved}건의 카테고리를 '{args.replace}'(으)로 변경했습니다.")
        print(f"[삭제 완료] category={parse_category_name(name)}")
    return EXIT_OK


@log_execution
@timed
def cmd_update(args: argparse.Namespace, service: BudgetService) -> int:
    """update: 옵션 방식으로 거래를 수정합니다. (설계 결정: 옵션 기반 고정)

    지정한 옵션만 바뀝니다.
      update --id TX-000001 --amount 20000         → 금액만 변경
      update --id TX-000001 --memo ""              → 메모를 비움
    """
    # argparse 옵션 이름 → Transaction 필드 이름
    option_to_field = {
        "date": "date",
        "type": "type",
        "category": "category",
        "amount": "amount",
        "memo": "memo",
        "tags": "tags",
    }
    changes: dict[str, object] = {}
    for option, field_name in option_to_field.items():
        value = getattr(args, option)  # args.date, args.type ... 를 이름(문자열)으로 꺼내기
        # ⚠️ `if value:`가 아니라 `is not None`으로 검사해야 합니다.
        #    --memo "" (빈 문자열로 지우기)는 '거짓'으로 취급되어 무시되는 버그가 생기기 때문.
        if value is not None:
            changes[field_name] = value

    tx = service.update_transaction(args.id, changes)
    print(f"[수정 완료] {format_transaction(tx)}")
    return EXIT_OK


@log_execution
@timed
def cmd_delete(args: argparse.Namespace, service: BudgetService) -> int:
    """delete: id로 거래를 삭제합니다."""
    service.delete_transaction(args.id)
    print(f"[삭제 완료] id={args.id}")
    return EXIT_OK


@log_execution
@timed
def cmd_import(args: argparse.Namespace, service: BudgetService) -> int:
    """import: CSV 파일에서 거래를 일괄 등록합니다."""
    result = service.import_csv(args.src)
    for message in result.errors:
        print(f"  [건너뜀] {message}")
    print(f"[완료] imported={result.imported}, skipped={result.skipped}")
    return EXIT_OK


@log_execution
@timed
def cmd_export(args: argparse.Namespace, service: BudgetService) -> int:
    """export: 조건에 맞는 거래를 CSV로 저장합니다."""
    count = service.export_csv(
        args.out, month=args.month, date_from=args.date_from, date_to=args.date_to
    )
    print(f"[완료] {args.out} ({count} records)")
    return EXIT_OK


# ===========================================================================
# 3. argparse 설정
# ===========================================================================


def build_parser() -> argparse.ArgumentParser:
    """명령어와 옵션의 '설계도'를 만듭니다.

    argparse가 해주는 일:
      - sys.argv(명령줄 문자열 목록)를 해석해서 args 객체로 만들어 줌
      - 모든 명령에 --help 를 자동으로 만들어 줌  ← 요구사항 충족!
      - 필수 옵션 누락, 잘못된 값 등은 알아서 오류 메시지 + 종료 코드 2로 처리
    """
    parser = argparse.ArgumentParser(
        # prog: 도움말에 표시될 실행 방법. __package__는 현재 패키지 이름(budget_app 등)
        prog=f"python -m {__package__}",
        description="나만의 용돈 기입장 — 파일 기반 콘솔 가계부",
        epilog=f"각 명령의 자세한 사용법: python -m {__package__} <명령> --help",
    )
    # ── 전역 옵션: 서브커맨드보다 '앞에' 써야 합니다.
    #    python -m budget_app --data-dir ./mydata list   (O)
    #    python -m budget_app list --data-dir ./mydata   (X)
    parser.add_argument(
        "--data-dir",
        type=Path,  # 문자열을 Path 객체로 자동 변환
        default=DEFAULT_DATA_DIR,
        help="데이터 저장 폴더 (기본: ./data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",  # 옵션을 쓰면 True, 안 쓰면 False (값을 받지 않는 '스위치')
        help="실행 로그를 화면에도 출력",
    )

    # ── 서브커맨드(add, list, ...) 등록
    # dest="command": 어떤 서브커맨드가 선택됐는지 args.command에 저장
    # required=True: 서브커맨드 없이 실행하면 오류
    sub = parser.add_subparsers(dest="command", required=True, metavar="<명령>")

    # set_defaults(handler=cmd_xxx): 이 서브커맨드가 선택되면 args.handler에 함수를 담아둠
    # → dispatch에서 if/elif 없이 args.handler(...) 한 줄로 실행할 수 있습니다.

    # add
    p = sub.add_parser("add", help="거래 추가 (대화형)")
    p.set_defaults(handler=cmd_add)

    # list
    p = sub.add_parser("list", help="최신순 거래 목록")
    p.add_argument("--limit", type=argtype(parse_positive_int), default=DEFAULT_LIST_LIMIT,
                   help=f"표시할 최대 건수 (기본: {DEFAULT_LIST_LIMIT})")
    p.set_defaults(handler=cmd_list)

    # search
    p = sub.add_parser("search", help="조건 검색 (최신순)")
    # dest="date_from": "--from"은 파이썬 예약어 from과 겹쳐서 args.from 으로 쓸 수 없으므로 이름을 바꿈
    p.add_argument("--from", dest="date_from", type=argtype(parse_date), help="시작일 YYYY-MM-DD (포함)")
    p.add_argument("--to", dest="date_to", type=argtype(parse_date), help="종료일 YYYY-MM-DD (포함)")
    p.add_argument("--category", help="카테고리")
    p.add_argument("--type", choices=VALID_TYPES, help="income 또는 expense")
    p.add_argument("--q", help="메모 키워드 (대소문자 무시)")
    p.add_argument("--tag", help="태그")
    p.add_argument("--limit", type=argtype(parse_positive_int), default=None,
                   help="표시할 최대 건수 (기본: 전체)")
    p.set_defaults(handler=cmd_search)

    # summary
    p = sub.add_parser("summary", help="월별 요약 + 예산 사용률")
    p.add_argument("--month", type=argtype(parse_month), required=True, help="YYYY-MM")
    p.add_argument("--top", type=argtype(parse_positive_int), default=DEFAULT_TOP,
                   help=f"지출 상위 카테고리 개수 (기본: {DEFAULT_TOP})")
    p.set_defaults(handler=cmd_summary)

    # budget (하위 명령: set / get) — 서브커맨드 안에 또 서브커맨드를 둘 수 있습니다.
    p = sub.add_parser("budget", help="월 예산 설정/조회")
    budget_sub = p.add_subparsers(dest="budget_cmd", required=True, metavar="<set|get>")
    bp = budget_sub.add_parser("set", help="월 예산 저장 (같은 월이면 덮어씀)")
    bp.add_argument("--month", type=argtype(parse_month), required=True, help="YYYY-MM")
    bp.add_argument("--amount", type=argtype(parse_amount), required=True, help="예산 금액 (양수)")
    bp = budget_sub.add_parser("get", help="월 예산 조회")
    bp.add_argument("--month", type=argtype(parse_month), required=True, help="YYYY-MM")
    p.set_defaults(handler=cmd_budget)

    # category (하위 명령: add / list / remove)
    p = sub.add_parser("category", help="카테고리 관리")
    cat_sub = p.add_subparsers(dest="category_cmd", required=True, metavar="<add|list|remove>")
    cat_sub.add_parser("list", help="카테고리 목록")
    cp = cat_sub.add_parser("add", help="카테고리 추가")
    # nargs="?": 값이 있어도 되고 없어도 되는 위치 인자. 없으면 default(None) → 대화형으로 물어봄
    cp.add_argument("name", nargs="?", help="카테고리명 (생략하면 대화형 입력)")
    cp = cat_sub.add_parser("remove", help="카테고리 삭제 (사용 중이면 차단)")
    cp.add_argument("name", nargs="?", help="카테고리명 (생략하면 대화형 입력)")
    cp.add_argument("--replace", help="사용 중인 거래를 옮길 대체 카테고리")
    p.set_defaults(handler=cmd_category)

    # update (옵션 기반)
    p = sub.add_parser("update", help="거래 수정 (옵션 방식)")
    p.add_argument("--id", required=True, help="수정할 거래 id (예: TX-000001)")
    p.add_argument("--date", type=argtype(parse_date), help="YYYY-MM-DD")
    p.add_argument("--type", choices=VALID_TYPES, help="income 또는 expense")
    p.add_argument("--category", help="등록된 카테고리")
    p.add_argument("--amount", type=argtype(parse_amount), help="양수 금액")
    p.add_argument("--memo", help='메모 (빈 값 "" 으로 지우기 가능)')
    p.add_argument("--tags", help='쉼표 구분 태그 (빈 값 "" 으로 지우기 가능)')
    p.set_defaults(handler=cmd_update)

    # delete
    p = sub.add_parser("delete", help="거래 삭제")
    p.add_argument("--id", required=True, help="삭제할 거래 id")
    p.set_defaults(handler=cmd_delete)

    # import — 명령 이름이 파이썬 예약어(import)여도 '문자열'이므로 문제없습니다.
    p = sub.add_parser("import", help="CSV 가져오기",
                       description=f"CSV 헤더: {','.join(CSV_COLUMNS)} (UTF-8)")
    p.add_argument("--from", dest="src", type=Path, required=True, help="가져올 CSV 경로")
    p.set_defaults(handler=cmd_import)

    # export
    p = sub.add_parser("export", help="CSV 내보내기 (기간 조건 필수)",
                       description="--month 또는 --from/--to 중 하나 이상이 필요합니다.")
    p.add_argument("--out", type=Path, required=True, help="저장할 CSV 경로")
    p.add_argument("--month", type=argtype(parse_month), help="YYYY-MM")
    p.add_argument("--from", dest="date_from", type=argtype(parse_date), help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", type=argtype(parse_date), help="YYYY-MM-DD")
    p.set_defaults(handler=cmd_export)

    return parser


# ===========================================================================
# 4. 로깅 설정 / 실행 진입점
# ===========================================================================


def setup_logging(data_dir: Path, verbose: bool) -> None:
    """로그 설정.

    - 항상: data/app.log 파일에 기록 (DEBUG 이상 = 전부)
    - --verbose: 화면(stderr)에도 INFO 이상을 출력

    로그 레벨 순서: DEBUG < INFO < WARNING < ERROR < CRITICAL
    핸들러의 레벨보다 '낮은' 로그는 그 핸들러에서 무시됩니다.
    → 스택트레이스(DEBUG)는 파일에만 남고 화면에는 절대 나오지 않습니다.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # 상위(root) 로거로 전달하지 않음 → 중복 출력 방지

    # main()이 여러 번 호출될 때(테스트 등) 핸들러가 계속 쌓이지 않도록 기존 것 정리
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()

    file_handler = logging.FileHandler(data_dir / "app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    if verbose:
        console = logging.StreamHandler()  # 기본 출력 대상: stderr
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("[로그] %(message)s"))
        logger.addHandler(console)


@handle_errors
def dispatch(args: argparse.Namespace) -> int:
    """준비 작업을 하고, 선택된 명령 함수를 실행합니다.

    @handle_errors를 '여기 한 곳'에만 붙인 이유:
      로깅 설정, 서비스 생성(폴더/파일 만들기), 명령 실행 —
      이 중 어디서 예외가 나든 모두 이 지점을 지나가므로 한 번에 처리됩니다.
      명령 함수마다 붙이지 않아도 '모든 명령'에 적용되는 효과입니다.
    """
    setup_logging(args.data_dir, args.verbose)
    service = BudgetService.from_data_dir(args.data_dir)
    handler: Handler = args.handler
    return handler(args, service)


def main(argv: list[str] | None = None) -> int:
    """프로그램 진입점. 종료 코드를 반환합니다.

    argv=None이면 argparse가 sys.argv[1:](실제 명령줄 입력)을 사용합니다.
    테스트에서는 main(["list", "--limit", "3"])처럼 직접 넘길 수 있습니다.

    참고: --help 나 옵션 오류는 parse_args() 안에서 argparse가 직접
    SystemExit(0 또는 2)를 발생시켜 종료합니다. (스택트레이스 없이 깔끔하게)
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)
