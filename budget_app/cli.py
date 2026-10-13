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
from budget_app.models import parse_category_name
from budget_app.models import MonthlySummary
from budget_app.decorators import EXIT_OK
from budget_app.models import parse_tags
from budget_app.models import parse_amount
from budget_app.models import parse_type
from budget_app.models import parse_date
from .services import BudgetService
from .decorators import print_error, timed, log_execution
from .models import Transaction
from .errors import ValidationError

import argparse
import logging
from datetime import date
from collections.abc import Callable
from typing import TypeVar

from pathlib import Path

T = TypeVar("T")

# 기본값
DEFAULT_DATA_DIR = Path("data") # 상대 경로 -> '명령을 실행한 위치' 기준의 data 폴더
DEFAULT_LIST_LIMIT = 20
DEFAULT_TOP = 5

# ===========================================================================
# 1. 작은 도우미 함수들
# ===========================================================================

def argtype(parse: Callable[[str], T]) -> Callable[[str], T]:
    """models의 parse_xxx 함수를 argparse의 type= 으로 쓸 수 있게 바꿔주는 어댑터.

    argparse는 type= 함수가 argparse.ArgumentTypeError를 던지면 그 메시지르 보여주고
    종료코드 2로 끝냅니다. 우리 함수는 ValidationError를 던지므로 '번역'이 필요합니다.

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
        raise ValidationError("1이상의 정수여야 합니다.", "예: 10")
    return value

def ask(prompt: str, parse: Callable[[str], T], *, default: str | None = None) -> T:
    """올바른 값이 들어올 때까지 반복해서 입력받는 함수.

    - parse: 입력 문자열을 검증/반환하는 함수 (실패 시 ValidationError)
    - default: 그냥 엔터를 쳤을 때 쓸 기본값

    잘못 입력하면 잘못 입력한 항목만 다시 물음.
    """
    while True:
        raw = input(prompt).strip()
        if (not raw) and (default is not None):
            raw = default
        try:
            return parse(raw)
        except ValidationError as error:
            print_error(error.message, error.hint)

def format_transaction(tx: Transaction) -> str:
    """거래 1건을 한 줄 문자열로 만듭니다.
    """
    # f-string 서식 지정자:
    #   {값:<9}   왼쪽 정렬, 최소 9칸
    #   {값:>10,} 오른쪽 정렬, 최소 10칸, 천 단위 쉼표 (15000 → "    15,000")
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
    print("새 거래를 입력합니다. (취소: Ctrl + C)")
    today = date.today().isoformat()

    tx_date = ask(f"날짜(YYYY-MM-DD, 엔터={today}: ", parse_date, default=today)
    tx_type = ask("타입(income/expense): ", parse_type)

    print(f"  (등록된 카테고리: {', '.join(service.list_categories())})")
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
    matches = service.search(
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
        tx_type=args.type,
        keyword=args.q,
        tag=args.tag,
        )
    rows = service.latest(matches, args.limit) # 한 줄씩 읽기 시작
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
    else: # "get"
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
    
    else:   # "remove"
        name = args.name or ask("삭제할 카테고리명: ", parse_category_name)
        moved = service.remove_category(name, replace_with=args.replace)
        if moved:
            print(f"[안내] 거래 {moved}건의 카테고리를 '{args.replace}'(으)로 변경했습니다.")
        print(f"[삭제 완료] category={parse_category_name(name)}")
    return EXIT_OK

@log_execution
@timed
def cmd_update(args: argparse.Namespace, service: BudgetService) -> int:
    """update: 옵션 방식으로 거래를 수정합니다.

    지정한 옵션만 바꿉니다.
      update --id TX-000001 --amount 20000         → 금액만 변경
      update --id TX-000001 --memo ""              → 메모를 비움
    """
    # argparse 옵션 이름 -> Transaction 필드 이름
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
        value = getattr(args, option) # args.date, args.type ... 를 이름(문자열)으로 꺼내기

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
      - 모든 명령에 --help 를 자동으로 만들어 줌
      - 필수 옵션 누락, 잘못된 값 등은 알아서 오류 메시지 + 종료 코드 2로 처리
    """
    parser = argparse.ArgumentParser(
        prog = f"python -m {__package__}", # prog: 도움말에 표시될 실행 방법. __package__는 현재 패키지 이름(budget_app 등)
        description = "나만의 용동 기입장 - 파일 기반 콘솔 가계부",
        epilog = f"각 명령의 자세한 사용법: python -m {__package__} <명령> --help",
    )

    # ── 전역 옵션: 서브커맨드보다 '앞에' 써야 합니다.
    #    python -m budget_app --data-dir ./mydata list   (O)
    #    python -m budget_app list --data-dir ./mydata   (X)
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
    p.add_argument("--limit", type=argtype(parse_date), default=DEFAULT_LIST_LIMIT,
                    help=f"표시할 최대 건수 (기본: {DEFAULT_LIST_LIMIT})")
    p.set_defaults(handler=cmd_list)

    # search

    dsdsdsdsdsdsd











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
