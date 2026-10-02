"""
cli.py — 커맨드라인 인터페이스 (CLI 계층)
==========================================
이 파일은 터미널 명령어와 사용자 입력을 처리합니다.
"CLI(Command Line Interface)" = 터미널에서 명령어로 조작하는 인터페이스

[argparse란?]
  Python 표준 라이브러리. 터미널 인자(argument)를 파싱해줍니다.
  예) python -m budget_app list --limit 5
       → command="list", limit=5 로 자동 파싱

[이 파일의 구조]
  1. ArgumentParser 설정 (어떤 명령/옵션을 받을지 정의)
  2. 각 명령을 처리하는 cmd_* 함수들
  3. main() 함수: 파싱된 명령에 맞는 함수 호출
"""

import argparse  # 커맨드라인 인자 파싱 표준 라이브러리
import sys       # sys.exit(): 종료 코드와 함께 프로그램 종료

# 다른 계층의 모듈 임포트
from decorators import handle_errors, measure_time
from services import BudgetService


# ──────────────────────────────────────────
# 출력 포맷 헬퍼 함수
# ──────────────────────────────────────────
def fmt_amount(amount: int) -> str:
    """금액을 천 단위 콤마 포함 문자열로 변환합니다. 예: 1500000 → '1,500,000원'"""
    # f-string의 :, 포맷: 숫자에 천 단위 구분자 추가
    return f"{amount:,}원"


def print_transaction(tx) -> None:
    """거래 한 건을 표 형식으로 출력합니다."""
    tags_str = f" [{', '.join(tx.tags)}]" if tx.tags else ""
    memo_str = f" {tx.memo}" if tx.memo else ""
    print(
        f"  {tx.id} | {tx.date} | {tx.type:7s} | "
        f"{tx.category:10s} | {fmt_amount(tx.amount):>12s}{memo_str}{tags_str}"
    )


# ──────────────────────────────────────────
# 각 명령 처리 함수 (cmd_*)
# ──────────────────────────────────────────

# @handle_errors: 이 함수에서 발생하는 모든 예외를 친절한 메시지로 처리
@handle_errors
def cmd_add(args, service: BudgetService) -> None:
    """
    거래 추가 (대화형 입력).
    미션 요구사항: add 실행 시 날짜/타입/카테고리/금액 등을 input()으로 순차 입력
    """
    print("\n──── 새 거래 추가 ────")

    # input(): 사용자로부터 한 줄 입력을 받아 문자열로 반환
    # strip(): 앞뒤 공백 제거 (실수로 스페이스를 누른 경우 처리)
    date = input("날짜(YYYY-MM-DD): ").strip()
    type_ = input("타입(income/expense): ").strip()
    category = input("카테고리: ").strip()
    amount = input("금액(양수 정수): ").strip()
    memo = input("메모(선택, 없으면 엔터): ").strip()
    tags = input("태그(쉼표로 구분, 없으면 엔터): ").strip()

    tx = service.add_transaction(
        type_=type_, date=date, amount=amount,
        category=category, memo=memo, tags=tags
    )
    print(f"\n[저장 완료] id={tx.id}")


@handle_errors
@measure_time  # 실행 시간도 측정 (두 데코레이터 동시 적용)
def cmd_list(args, service: BudgetService) -> None:
    """거래 목록을 최신순으로 출력합니다."""
    limit = args.limit  # argparse가 파싱한 --limit 값
    print(f"\n──── 거래 목록 (최신 {limit}건) ────")
    print(f"  {'ID':12s} | {'날짜':10s} | {'타입':7s} | {'카테고리':10s} | {'금액':>12s} | 메모")
    print("  " + "-" * 72)

    count = 0
    for tx in service.list_transactions(limit=limit):
        print_transaction(tx)
        count += 1

    if count == 0:
        print("  (거래 내역이 없습니다)")
    else:
        print(f"\n  총 {count}건")


@handle_errors
def cmd_search(args, service: BudgetService) -> None:
    """조건에 맞는 거래를 검색합니다."""
    print("\n──── 검색 결과 ────")

    count = 0
    # args에서 각 옵션 값을 가져옴. 지정하지 않으면 None
    for tx in service.search_transactions(
        from_date=args.from_date,
        to_date=args.to_date,
        category=args.category,
        type_=args.type,
        query=args.q,
        tag=args.tag,
    ):
        print_transaction(tx)
        count += 1

    if count == 0:
        print("  (조건에 맞는 거래가 없습니다)")
    else:
        print(f"\n  {count}건 검색됨")


@handle_errors
def cmd_summary(args, service: BudgetService) -> None:
    """월별 요약을 출력합니다."""
    result = service.monthly_summary(month=args.month, top_n=args.top)

    if not result["has_data"]:
        print(f"\n[{args.month}] 데이터 없음")
        return

    print(f"\n──── {args.month} 월별 요약 ────")
    print(f"  총 수입   : {fmt_amount(result['total_income'])}")
    print(f"  총 지출   : {fmt_amount(result['total_expense'])}")
    print(f"  잔  액    : {fmt_amount(result['balance'])}")

    # 예산 정보 출력 (설정되어 있을 때만)
    if result["budget"]:
        print(f"  예  산    : {fmt_amount(result['budget'])} (사용률 {result['usage_rate']}%)")
        if result["over_budget"]:
            # 예산 초과 경고
            over = result["total_expense"] - result["budget"]
            print(f"  ⚠️  경고   : 예산을 {fmt_amount(over)} 초과했습니다!")

    # 카테고리별 지출 TOP N
    if result["top_categories"]:
        print(f"\n  지출 TOP {args.top}")
        for i, (cat, amount) in enumerate(result["top_categories"], start=1):
            # enumerate(이터러블, start=1): (1, 첫번째값), (2, 두번째값)... 으로 반환
            print(f"  {i}) {cat:10s} {fmt_amount(amount)}")


@handle_errors
def cmd_budget(args, service: BudgetService) -> None:
    """예산 설정/조회 명령을 처리합니다."""
    if args.budget_cmd == "set":
        budget = service.set_budget(month=args.month, amount=args.amount)
        print(f"\n[저장 완료] {budget.month} 예산 {fmt_amount(budget.amount)}")
    else:
        print(f"[오류] 알 수 없는 budget 하위 명령: {args.budget_cmd}")
        sys.exit(1)


@handle_errors
def cmd_category(args, service: BudgetService) -> None:
    """카테고리 관리 명령을 처리합니다."""
    if args.category_cmd == "list":
        cats = service.list_categories()
        print("\n──── 카테고리 목록 ────")
        if not cats:
            print("  (등록된 카테고리가 없습니다)")
        for cat in cats:
            print(f"  - {cat}")

    elif args.category_cmd == "add":
        # 카테고리 이름은 대화형 입력
        name = input("카테고리명: ").strip()
        success = service.add_category(name)
        if success:
            print(f"\n[저장 완료] category={name}")
        else:
            print(f"\n[안내] '{name}' 카테고리가 이미 존재합니다.")

    elif args.category_cmd == "remove":
        name = input("삭제할 카테고리명: ").strip()
        success, msg = service.remove_category(name)
        print(f"\n{msg}")
        if not success:
            sys.exit(1)


@handle_errors
def cmd_update(args, service: BudgetService) -> None:
    """
    거래 수정 (옵션 기반).
    예) python -m budget_app update --id TX-000001 --amount 20000
    """
    # 수정할 필드만 dict에 담기
    # vars(args): Namespace 객체를 dict로 변환
    # 예) Namespace(id='TX-1', amount=20000, memo=None) → {'id': 'TX-1', 'amount': 20000, ...}
    update_fields = {}
    if args.date:
        update_fields["date"] = args.date
    if args.type:
        update_fields["type"] = args.type
    if args.amount:
        update_fields["amount"] = args.amount
    if args.category:
        update_fields["category"] = args.category
    if args.memo is not None:  # memo는 빈 문자열로 수정할 수도 있으므로 None 체크
        update_fields["memo"] = args.memo
    if args.tags is not None:
        update_fields["tags"] = args.tags

    if not update_fields:
        print("[안내] 수정할 필드를 하나 이상 지정하세요.")
        print("       예: --amount 20000 --memo '수정된 메모'")
        sys.exit(1)

    success = service.update_transaction(args.id, **update_fields)
    if success:
        print(f"\n[수정 완료] {args.id}")
    else:
        print(f"\n[오류] '{args.id}' 거래를 찾을 수 없습니다.")
        sys.exit(1)


@handle_errors
def cmd_delete(args, service: BudgetService) -> None:
    """거래를 삭제합니다."""
    # 삭제 전 확인 (실수 방지)
    confirm = input(f"'{args.id}' 거래를 삭제하시겠습니까? (y/N): ").strip().lower()
    if confirm != "y":
        print("[취소] 삭제를 취소했습니다.")
        return

    success = service.delete_transaction(args.id)
    if success:
        print(f"\n[삭제 완료] {args.id}")
    else:
        print(f"\n[오류] '{args.id}' 거래를 찾을 수 없습니다.")
        sys.exit(1)


@handle_errors
def cmd_export(args, service: BudgetService) -> None:
    """거래를 CSV 파일로 내보냅니다."""
    count = service.export_csv(
        out_path=args.out,
        month=args.month,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    print(f"\n[완료] {args.out} ({count} records)")


@handle_errors
def cmd_import(args, service: BudgetService) -> None:
    """CSV 파일에서 거래를 가져옵니다."""
    imported, skipped = service.import_csv(in_path=args.from_path)
    print(f"\n[완료] imported={imported}, skipped={skipped}")


# ──────────────────────────────────────────
# ArgumentParser 설정 — 명령어와 옵션 정의
# ──────────────────────────────────────────
def build_parser(data_dir: str) -> argparse.ArgumentParser:
    """
    ArgumentParser를 생성하고 모든 서브커맨드를 등록합니다.

    argparse 기본 개념:
      - ArgumentParser: 최상위 파서 (프로그램 설명 포함)
      - add_subparsers: 서브커맨드 그룹 생성 (add/list/search 등)
      - add_parser: 개별 서브커맨드 파서 추가
      - add_argument: 옵션 또는 위치 인자 추가
    """
    # 최상위 파서
    parser = argparse.ArgumentParser(
        prog="budget_app",
        description="나만의 용돈 기입장 — 파일 기반 가계부 CLI 프로그램",
    )

    # --data-dir: 저장 폴더 경로를 변경할 수 있는 글로벌 옵션
    parser.add_argument(
        "--data-dir",
        default=data_dir,
        metavar="PATH",
        help="데이터 저장 폴더 경로 (기본값: ./data)",
    )

    # 서브커맨드 그룹 생성
    # dest="command": 어떤 서브커맨드가 선택됐는지 args.command 로 접근
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True  # 서브커맨드를 반드시 지정해야 함

    # ── add ─────────────────────────────────
    subparsers.add_parser("add", help="거래 추가 (대화형 입력)")

    # ── list ─────────────────────────────────
    p_list = subparsers.add_parser("list", help="거래 목록 조회")
    p_list.add_argument(
        "--limit", type=int, default=20, metavar="N",
        help="최대 출력 건수 (기본값: 20)"
    )

    # ── search ───────────────────────────────
    p_search = subparsers.add_parser("search", help="거래 검색")
    p_search.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD", help="시작 날짜")
    p_search.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD", help="종료 날짜")
    p_search.add_argument("--category", metavar="NAME", help="카테고리 필터")
    p_search.add_argument("--type", metavar="income|expense", help="거래 타입 필터")
    p_search.add_argument("--q", metavar="KEYWORD", help="메모 키워드 검색")
    p_search.add_argument("--tag", metavar="TAG", help="태그 필터")

    # ── summary ──────────────────────────────
    p_summary = subparsers.add_parser("summary", help="월별 요약")
    p_summary.add_argument("--month", required=True, metavar="YYYY-MM", help="대상 월")
    p_summary.add_argument("--top", type=int, default=5, metavar="N", help="TOP N 카테고리 (기본값: 5)")

    # ── budget ───────────────────────────────
    p_budget = subparsers.add_parser("budget", help="예산 설정")
    budget_sub = p_budget.add_subparsers(dest="budget_cmd", metavar="<set>")
    budget_sub.required = True
    p_budget_set = budget_sub.add_parser("set", help="예산 설정")
    p_budget_set.add_argument("--month", required=True, metavar="YYYY-MM", help="대상 월")
    p_budget_set.add_argument("--amount", required=True, metavar="금액", help="예산 금액")

    # ── category ─────────────────────────────
    p_cat = subparsers.add_parser("category", help="카테고리 관리")
    cat_sub = p_cat.add_subparsers(dest="category_cmd", metavar="<add|list|remove>")
    cat_sub.required = True
    cat_sub.add_parser("list", help="카테고리 목록")
    cat_sub.add_parser("add", help="카테고리 추가 (대화형)")
    cat_sub.add_parser("remove", help="카테고리 삭제 (대화형)")

    # ── update ───────────────────────────────
    p_update = subparsers.add_parser("update", help="거래 수정 (옵션 기반)")
    p_update.add_argument("--id", required=True, metavar="TX-ID", help="수정할 거래 ID")
    p_update.add_argument("--date", metavar="YYYY-MM-DD")
    p_update.add_argument("--type", metavar="income|expense")
    p_update.add_argument("--category", metavar="NAME")
    p_update.add_argument("--amount", metavar="금액")
    p_update.add_argument("--memo", metavar="텍스트")
    p_update.add_argument("--tags", metavar="태그1,태그2")

    # ── delete ───────────────────────────────
    p_delete = subparsers.add_parser("delete", help="거래 삭제")
    p_delete.add_argument("--id", required=True, metavar="TX-ID", help="삭제할 거래 ID")

    # ── export ───────────────────────────────
    p_export = subparsers.add_parser("export", help="CSV 내보내기")
    p_export.add_argument("--out", required=True, metavar="파일.csv", help="출력 CSV 파일 경로")
    p_export.add_argument("--month", metavar="YYYY-MM")
    p_export.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD")
    p_export.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD")

    # ── import ───────────────────────────────
    p_import = subparsers.add_parser("import", help="CSV 가져오기")
    p_import.add_argument("--from", dest="from_path", required=True, metavar="파일.csv")

    return parser


# ──────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────
def main() -> None:
    """
    프로그램의 시작점.
    1. 명령어 파싱
    2. 서비스 초기화
    3. 해당 명령 함수 호출
    """
    # 우선 --data-dir 만 먼저 파싱해서 서비스 초기화에 사용
    # parse_known_args: 알 수 없는 인자는 무시하고 나머지를 반환
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--data-dir", default="./data")
    pre_args, _ = pre_parser.parse_known_args()

    # 전체 파서 생성
    parser = build_parser(pre_args.data_dir)

    # sys.argv: 터미널에서 입력한 인자 목록
    # 예) python -m budget_app list --limit 5
    #   → sys.argv = ['-m', 'list', '--limit', '5']  (첫 번째는 모듈명)
    args = parser.parse_args()

    # 서비스 초기화 (data 폴더 생성 포함)
    service = BudgetService(data_dir=args.data_dir)

    # 명령에 맞는 함수 실행
    # args.command: 사용자가 입력한 서브커맨드 이름 (예: "list", "add")
    command_map = {
        "add": cmd_add,
        "list": cmd_list,
        "search": cmd_search,
        "summary": cmd_summary,
        "budget": cmd_budget,
        "category": cmd_category,
        "update": cmd_update,
        "delete": cmd_delete,
        "export": cmd_export,
        "import": cmd_import,
    }

    cmd_func = command_map.get(args.command)
    if cmd_func:
        cmd_func(args, service)
    else:
        parser.print_help()
        sys.exit(1)
