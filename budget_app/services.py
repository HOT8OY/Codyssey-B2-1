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
