"""
services.py — 서비스(Service) 계층: 비즈니스 로직
==================================================

[이 파일의 역할]
"가계부 프로그램이 무엇을 할 수 있는가"를 정의함.
  - 거래 추가/조회/검색/수정/삭제
  - 월별 요약 계산, 예산 사용률 계산
  - 카테고리 관리 정책 (사용 중인 카테고리는 함부로 못 지움)
  - CSV 가져오기/내보내기

[다른 계층과의 관계]
  cli.py        → (입출력 담당)
  services.py   → (판단 담당)
  repository.py → (저장 담당)
"""


from budget_app.repository import format_tx_id
from budget_app.models import ImportResult
from budget_app.models import MonthlySummary
from budget_app.models import Budget
from collections.abc import Iterator
from budget_app.models import TxType
from collections.abc import Iterable
from pathlib import Path
from budget_app.repository import BudgetStore, CategoryStore, TransactionRepository
import csv
import heapq


from .errors import NotFoundError, ValidationError
from .models import (
    Transaction,
    parse_amount, parse_category_name, parse_date, parse_tags
    )

# import/export CSV 스키마 (미션 문서 기준)
CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")
REQUIRED_CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount")

# 저장 파일 이름
TRANSACTIONS_FILE = "transactions.jsonl"
CATEGORIES_FILE = "categories.jsonl"
BUDGETS_FILE = "budgets.jsonl"


class BudgetService:
    """가계부의 모든 기능을 제공하는 서비스 클래스.

    서비스가 저장소를 직접 만들지 않고 바깥에서 의존성 주입을 받아서 씀.
    """

    def __init__(
        self, transactions: TransactionRepository, categories: CategoryStore,
        budgets: BudgetStore) -> None:
        self.transactions = transactions
        self.categories = categories
        self.budgets = budgets
    
    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "BudgetService":
        """저장 폴더 경로만 주면 저장소 3개를 만들어 서비스를 조립해 줍니다."""
        data_dir.mkdir(parents=True, exist_ok=True) # 중간 폴더 함께 생성 / 이미 있어도 에러 X
        return cls(
            transactions=TransactionRepository(data_dir / TRANSACTIONS_FILE),
            categories=CategoryStore(data_dir / CATEGORIES_FILE),
            budgets=BudgetStore(data_dir / BUDGETS_FILE),
        )
    
    # =======================================================================
    # 카테고리
    # =======================================================================

    def list_categories(self) -> list[str]:
        return self.categories.list_names()
    
    def validate_category(self, name: str) -> str:
        """카테고리 이름이 등록된 것인지 확인하고, 정리된 이름을 돌려줍니다.

        models의 parse...은 형식만 보고, 이 메서드는 파일을 읽어와야 하기 때문에 등록 여부까지 봅니다.
        """
        category = parse_category_name(name)
        if not self.categories.exists(category):
            available = ", ".join(self.list_categories())
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: '{category}'",
                f"사용 가능: {available} / 새로 만들려면: category add {category}",
            )
        return category
    
    def add_category(self, name: str) -> str:
        category = parse_category_name(name)
        if not self.categories.add(category):
            raise ValidationError(
                f"'{category}' 카테고리는 이미 존재합니다.",
                "category list로 목록을 확인하세요.",
            )
        return category
    
    def remove_category(self, name: str, replace_with: str | None = None) -> int:
        """카테고리를 삭제합니다. 반환값: 다른 카테고리로 옮겨진 거래 건수.

        [정책] 사용 중인 카테고리는
          - replace_with가 없으면 -> 삭제를 막는다(ValidationError)
          - replace_with가 있으면 -> 해당 거래들을 그 카테고리로 옮긴 뒤 삭제한다
        """
        category = parse_category_name(name)
        if not self.categories.exists(category):
            raise NotFoundError(
                f"'{category}' 카테고리가 존재하지 않습니다.",
                "category list 로 목록을 확인하세요.",
            )
        
        used = self.transactions.count_by_category(category)
        moved = 0
        if used > 0:
            if replace_with is None:
                raise ValidationError(
                    f"'{category}' 카테고리를 사용하는 거래가 {used}건 있어 삭제할 수 없습니다.",
                    f"다른 카테고리로 옮기며 삭제하려면: category remove {category} --replace etc",
                )
            target = self.validate_category(replace_with)
            if target == category:
                raise ValidationError(
                    "대체 카테고리는 삭제할 카테고리와 달라야 합니다.",
                    "예: category remove food --replace etc",
                )
            # 순서 중요! 거래를 먼저 옮기고 ->  카테고리를 지워야 함!
            moved = self.transactions.replace_category(category, target)
        
        self.categories.remove(category)
        return moved
    
    # =======================================================================
    # 거래 추가 / 조회 / 검색
    # =======================================================================

    def add_transaction(
        self,
        *,  # 별표 뒤 매개변수는 '이름=값' 형태로만 넘길 것
        date: str,
        tx_type: str,
        category: str,
        amount: int | str,
        memo: str = "",
        tags: list[str] | str | None = None,
    ) -> Transaction:
        """새 거래를 저장하고, 생성된 Transaction(id 포함)을 돌려줍니다."""
        tx = Transaction(
            id=self.transactions.next_id(),
            type=tx_type, # type: ignore[arg-type]  (Transaction.__post_init_에서 검증됨)
            date=date,
            amount=amount,
            category=self.validate_category(category),
            memo=memo,
            tags=parse_tags(tags),
        )
        self.transactions.add(tx)
        return tx

    @staticmethod
    def latest(items: Iterable[Transaction], limit: int | None) -> list[Transaction]:
        """거래들을 최신순으로 정렬해 앞에서 limit개만 돌려줍니다.
        """
        if limit is None:
            # 개수 제한이 없으면 전부 정렬함
            return sorted(items, key=lambda tx: tx.sort_key, reverse=True)
        return heapq.nlargest(limit, items, key=lambda tx: tx.sort_key)
    
    def list_recent(self, limit: int) -> list[Transaction]:
        return self.latest(self.transactions.iter_all(), limit)
    
    def search(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        month: str | None = None,
        category: str | None = None,
        tx_type: TxType | None = None,
        keyword: str | None = None,
        tag: str | None = None,
    ) -> Iterator[Transaction]:
        """조건에 맞는 거래를 하나씩 돌려주는 제너레이터.
        조건이 None이면 해당 조건은 무시.

        [제너레이터 체인]
        iter_all() -> search(조건 필터) -> latest(최신순 상위 N)
        파일 한 줄씩 읽어옴 -> 조건에 맞는것만 -> N개만 기억
        """
        if date_from and date_to and date_from > date_to:
            raise ValidationError(
                f"시작일({date_from})이 종료일({date_to})보다 늦습니다.",
                "--from 은 --to 보다 같거나 이른 날짜여야 합니다.",
            )
        # 비교를 위해 미리 정리 (대소문자 무시)
        category = parse_category_name(category) if category else None
        keyword = keyword.lower() if keyword else None
        tag = tag.strip().lower() if tag else None

        for tx in self.transactions.iter_all():
            # 날짜는 문자열 비교
            if date_from and tx.date < date_from:
                continue
            if date_to and tx.date > date_to:
                continue
            if month and tx.month != month:
                continue
            if category and tx.category != category:
                continue
            if tx_type and tx.type != tx_type:
                continue
            if keyword and keyword not in tx.memo.lower():
                continue
            if tag and tag not in (t.lower() for t in tx.tags):
                continue
            yield tx    # 모든 조건을 통과한 거래만 내보냄
    
    # =======================================================================
    # 거래 수정 / 삭제
    # =======================================================================

    def update_transaction(self, tx_id: str, changes: dict[str, object]) -> Transaction:
        """거래의 일부 필드를 수정합니다.

        changes 예: {"amount": 20000, "memo": 저녁}
        - 형식 검증은 Transaction.__post_init__으로 자동 처리
        - 카테고리 등록 여부는 서비스가 확인
        """
        allowed = {"date", "type", "category", "amount", "memo", "tags"}
        unknown = set(changes) - allowed # 집합의 차집합 -> 허용되지 않은 키만 남음
        if unknown:
            raise ValidationError(f"수정할 수 없는 항목입니다: {','.join(sorted(unknown))}")
        if not changes:
            raise ValidationError(
                "수정할 항목이 없습니다.",
                "예: update --id TX-000001 --amount 20000 --memo 저녁",
            )
        
        if "category" in changes:
            changes = {**changes, "category": self.validate_category(str(changes["category"]))}
        if "tags" in changes:
            changes = {**changes, "tags": parse_tags(changes["tags"])} # type: ignore[arg-type]
        
        return self.transactions.update(tx_id, changes)

    def delete_transaction(self, tx_id: str) -> None:
        self.transactions.delete(tx_id.strip())
    
    # =======================================================================
    # 예산 / 월별 요약
    # =======================================================================

    def set_budget(self, month: str, amount: int | str) -> Budget:
        budget = Budget(month=month, amount=amount) # type: ignore[arg-type]
        self.budgets.set(budget)
        return budget
    
    def get_budget(self, month: str) -> Budget | None:
        return self.budgets.get(month)
    
    def summarize(self, month: str) -> MonthlySummary:
        """해당 월의 수입/지출/카테고리별 지출을 한 번 흝으면서 계산합니다.

        거래 목록을 리스트로 모으지 않고, 한 건씩 받으면서 합계에 더하기만 합니다.
        """
        summary = MonthlySummary(month=month)
        for tx in self.search(month=month):
            summary.count += 1
            if tx.type == "income":
                summary.total_income += tx.amount
            else:
                summary.total_expense += tx.amount
                # dict.get(키, 0): 처음 나온 카테고리면 0에서 시작
                summary.expense_by_category[tx.category] = (
                    summary.expense_by_category.get(tx.category, 0) + tx.amount
                )
        
        budget = self.budgets.get(month)
        summary.budget = budget.amount if budget else None
        return summary

    # =======================================================================
    # CSV 가져오기 / 내보내기
    # =======================================================================

    def export_csv(
        self,
        out_path: Path,
        *,
        month: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """조건에 맞는 거래를 CSV로 저장하고, 저장한 건수를 돌려줍니다.

        요구사항: --month 또는 --from/--to 중 하나 이상의 조건이 필수.
        결과는 파일에 저장된 순서 그대로 스트리밍으로 기록.
        """
        if not (month or date_from or date_to):
            raise ValidationError(
                "내보낼 기간 조건이 없습니다.",
                "--month 2026-10 또는 --from 2026-10-01 --to 2026-10-31 을 지정하세요."
            )
        
        count = 0
        # newline"": csv 모듈이 줄바꿈을 직접 관리하도록 맡기는 옵션.
        # 이걸 빼면 Windows에서 줄 사이에 빈 줄이 하나씩 끼는 문제가 생김.
        with out_path.open("w", encoding="utf-8", newline="") as file:
            # DicWriter: dict를 받아 CSV 한 줄로 써주는 도구. fieldnaems가 열 순서가 된다.
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()    # 첫 줄: date,type,category,amount,memo,tags
            for tx in self.search(month=month, date_from=date_from, date_to=date_to):
                writer.writerow(
                    {
                        "date": tx.date,
                        "type": tx.type,
                        "category": tx.category,
                        "amount": tx.amount,
                        "memo": tx.memo,
                        # 리스트 값 안에 쉼표가 있으면 "a,b"처럼 따옴표로 감싸준다.
                        "tags": ",".join(tx.tags)
                    }
                )
                count += 1
            return count
        
    def import_csv(self, src: Path) -> ImportResult:
        """CSV 파일의 거래들을 일괄 등록합니다.

        [정책] 잘못된 줄이 있어도 전체를 실패시키지 않고,
        그 줄만 건너뛴 뒤 사유를 기록합니다.
        """
        if not src.is_file():
            raise NotFoundError(
                f"가져올 CSV 파일을 찾을 수 없습니다: {src}",
                "파일 경로를 확인하세요. 예: import --from ./import.csv"
            )
        
        result = ImportResult()
        # encoding="utf-8-sig": 엑셀이 저장한 UTF-8 CSV 맨 앞에 붙는 보이지 않는 문자(BOM)를
        # 자동으로 제거해 줍니다. 일반 UTF-8 파일도 문제없이 읽습니다.
        with src.open("r", encoding="utf-8-sig", newline="") as file:
            # DictReader: 첫 줄(헤더)을 키로 삼아 각 줄을 dict로 돌려줍니다.
            #   {"date": "2026-10-15", "type": "expense", ...}
            reader = csv.DictReader(file)
            header = reader.fieldnames or []
            missing = [col for col in REQUIRED_CSV_COLUMNS if col not in header]
            if missing:
                raise ValidationError(
                    f"CSV 헤더에 필수 컬럼이 없습니다. {', '.join(missing)}",
                    f"첫 줄(헤더)은 다음과 같아야 합니다: {','.join(CSV_COLUMNS)}"
                )
            
            start_number = self.transactions.next_number()

            def valid_transactions() -> Iterator[Transaction]:
                """CSV를 한 줄씩 검증해서 올바른 거래만 내보내는 제너레이터."""
                number = start_number
                # start=2: 1번째 줄은 헤더이므로 데이터는 2번째 줄부터
                for line_no, row in enumerate(reader, start=2):
                    try:
                        tx=Transaction(
                            id=format_tx_id(number),
                            type=(row.get("type") or ""), # type: ignore[arg-type]
                            date=parse_date(row.get("date") or ""),
                            amount=parse_amount(row.get("amount") or ""),
                            category=self.validate_category(row.get("category") or ""),
                            memo=row.get("memo") or "",
                            tags=parse_tags(row.get("tags"))
                        )
                    except ValidationError as error:
                        result.skipped += 1
                        result.errors.append(f"{line_no}번째 줄: {error.message}")
                        continue
                    number += 1
                    result.imported += 1
                    yield tx
            
            self.transactions.add_many(valid_transactions())
        return result