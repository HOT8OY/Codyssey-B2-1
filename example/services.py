"""
services.py — 비즈니스 로직 계층
===================================
이 파일은 프로그램의 핵심 동작 로직을 담당합니다.
"비즈니스 로직"이란 실제 업무 규칙을 코드로 표현한 것입니다.
  예) 카테고리가 등록됐는지 검증, 월별 통계 계산, 예산 초과 경고 등

[왜 repository.py와 분리하나요?]
  repository.py: "파일에 어떻게 저장하나?" (저장 방법)
  services.py  : "어떤 규칙으로 처리하나?" (업무 규칙)
  두 역할을 분리하면 각자 독립적으로 수정/테스트할 수 있습니다.

[import 관계]
  cli.py → services.py → repository.py → models.py
  (상위 계층이 하위 계층만 사용합니다.)
"""

import csv          # CSV 파일 읽기/쓰기
import datetime     # 날짜 유효성 검사
import uuid         # (사용하지 않지만 참고용: UUID 기반 ID 생성 방법)

from typing import Dict, Generator, List, Optional, Tuple

from models import Budget, Category, Transaction
from repository import (
    BudgetStore,
    CategoryStore,
    TransactionRepository,
    ensure_data_dir,
    DEFAULT_DATA_DIR,
)


# ──────────────────────────────────────────
# 입력 검증 함수들 (Validation)
# ──────────────────────────────────────────
def validate_date(date_str: str) -> str:
    """
    날짜 문자열이 YYYY-MM-DD 형식인지 검증합니다.
    유효하면 그대로 반환, 유효하지 않으면 ValueError 발생.
    """
    try:
        # strptime: 문자열을 날짜 객체로 파싱. 형식이 맞지 않으면 ValueError 발생.
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        # 예외를 잡아서 더 친절한 메시지로 다시 발생
        raise ValueError(f"날짜 형식이 올바르지 않습니다 (YYYY-MM-DD): '{date_str}'\n[힌트] 예: 2024-01-15")


def validate_type(type_str: str) -> str:
    """거래 타입이 income 또는 expense인지 검증합니다."""
    if type_str not in ("income", "expense"):
        raise ValueError(f"타입은 'income' 또는 'expense'만 허용됩니다: '{type_str}'")
    return type_str


def validate_amount(amount_str: str) -> int:
    """
    금액 문자열을 정수로 변환하고 양수인지 검증합니다.
    숫자가 아니거나 0 이하면 ValueError 발생.
    """
    try:
        amount = int(amount_str)
    except ValueError:
        raise ValueError(f"금액은 숫자여야 합니다: '{amount_str}'")
    if amount <= 0:
        raise ValueError(f"금액은 양수여야 합니다: {amount}")
    return amount


def validate_month(month_str: str) -> str:
    """YYYY-MM 형식의 월 문자열을 검증합니다."""
    try:
        datetime.datetime.strptime(month_str, "%Y-%m")
        return month_str
    except ValueError:
        raise ValueError(f"월 형식이 올바르지 않습니다 (YYYY-MM): '{month_str}'\n[힌트] 예: 2024-01")


# ──────────────────────────────────────────
# BudgetService — 핵심 비즈니스 로직
# ──────────────────────────────────────────
class BudgetService:
    """
    가계부의 모든 비즈니스 로직을 담당합니다.
    내부적으로 세 저장소(Repository/Store)를 사용합니다.
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        # 초기화 시 data 폴더와 파일이 없으면 자동 생성
        ensure_data_dir(data_dir)
        # 세 저장소 인스턴스 생성 (의존성 주입 패턴)
        self.tx_repo = TransactionRepository(data_dir)
        self.cat_store = CategoryStore(data_dir)
        self.budget_store = BudgetStore(data_dir)

    # ── 거래 추가 ───────────────────────────
    def add_transaction(
        self,
        type_: str,
        date: str,
        amount: str,
        category: str,
        memo: str = "",
        tags: str = "",
    ) -> Transaction:
        """
        새 거래를 추가합니다.
        입력값을 검증한 후 저장합니다.

        tags 파라미터: 쉼표로 구분된 문자열 (예: "meal,lunch")
                      빈 문자열이면 빈 리스트로 처리
        """
        # 각 필드 검증 (검증 실패 시 ValueError 발생 → handle_errors 데코레이터가 처리)
        validated_type = validate_type(type_)
        validated_date = validate_date(date)
        validated_amount = validate_amount(amount)

        # 카테고리가 등록된 목록에 있는지 확인
        if not self.cat_store.exists(category):
            cats = ", ".join(self.cat_store.list_all())
            raise ValueError(
                f"등록되지 않은 카테고리입니다: '{category}'\n"
                f"[힌트] 사용 가능한 카테고리: {cats}\n"
                f"       또는 'category add' 명령으로 추가하세요."
            )

        # 태그 파싱: "meal,lunch" → ["meal", "lunch"]
        # 빈 문자열 태그는 필터링 (strip(): 앞뒤 공백 제거)
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        # 고유 ID 생성
        tx_id = self.tx_repo.next_id()

        # Transaction 객체 생성
        tx = Transaction(
            id=tx_id,
            type=validated_type,
            date=validated_date,
            amount=validated_amount,
            category=category,
            memo=memo,
            tags=tag_list,
        )

        # 파일에 저장
        self.tx_repo.add(tx)
        return tx

    # ── 거래 목록 조회 (스트리밍) ─────────────
    def list_transactions(
        self, limit: int = 20
    ) -> Generator[Transaction, None, None]:
        """
        최신순으로 거래를 스트리밍합니다.
        limit: 최대 반환 건수 (기본값 20)

        [스트리밍 vs 전체 로드]
        전체 목록을 date 기준 정렬하려면 일단 모두 읽어야 합니다.
        따라서 여기서는 전체 읽기 후 정렬하고, limit 개만 yield합니다.
        (필터링 없는 단순 목록은 메모리 절약 효과가 제한적이지만,
         제너레이터 인터페이스를 유지해서 search 등과 일관성을 맞춥니다.)
        """
        all_txs = list(self.tx_repo.stream_all())

        # sorted(): 리스트를 정렬한 새 리스트 반환
        # key=lambda tx: tx.date: 정렬 기준 = date 필드
        # reverse=True: 내림차순 (최신 날짜가 먼저)
        sorted_txs = sorted(all_txs, key=lambda tx: tx.date, reverse=True)

        count = 0
        for tx in sorted_txs:
            if count >= limit:
                return  # 제너레이터에서 return = 종료 (StopIteration 발생)
            yield tx
            count += 1

    # ── 거래 검색 ───────────────────────────
    def search_transactions(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: Optional[str] = None,
        type_: Optional[str] = None,
        query: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Generator[Transaction, None, None]:
        """
        조건에 맞는 거래를 최신순으로 스트리밍합니다.
        모든 조건은 선택사항입니다 (None이면 해당 조건 무시).
        """
        all_txs = list(self.tx_repo.stream_all())
        sorted_txs = sorted(all_txs, key=lambda tx: tx.date, reverse=True)

        for tx in sorted_txs:
            # 조건 검사: 모든 조건을 통과해야 yield
            # from_date 조건: tx.date >= from_date (날짜 문자열 비교 가능, YYYY-MM-DD 형식이므로)
            if from_date and tx.date < from_date:
                continue
            if to_date and tx.date > to_date:
                continue
            if category and tx.category != category:
                continue
            if type_ and tx.type != type_:
                continue
            # query: memo 필드에 키워드 포함 여부 (대소문자 무시)
            if query and query.lower() not in tx.memo.lower():
                continue
            # tag: tags 리스트에 특정 태그 포함 여부
            if tag and tag not in tx.tags:
                continue
            yield tx

    # ── 월별 요약 ───────────────────────────
    def monthly_summary(
        self, month: str, top_n: int = 5
    ) -> Dict:
        """
        특정 월의 수입/지출 요약과 카테고리별 통계를 반환합니다.

        반환 형태 (dict):
        {
          "month": "2024-01",
          "total_income": 3000000,
          "total_expense": 215000,
          "balance": 2785000,
          "budget": 500000,          # 예산 없으면 None
          "usage_rate": 43.0,        # 예산 사용률(%), 없으면 None
          "over_budget": False,      # 예산 초과 여부
          "top_categories": [("rent", 150000), ("food", 45000), ...]
        }
        """
        validate_month(month)

        total_income = 0
        total_expense = 0
        category_totals: Dict[str, int] = {}  # {"food": 45000, "rent": 150000, ...}

        # 스트리밍으로 해당 월 거래만 집계
        for tx in self.tx_repo.stream_all():
            # tx.date[:7]: "2024-01-15" → "2024-01" (앞 7글자)
            if tx.date[:7] != month:
                continue  # 다른 달 거래는 무시

            if tx.type == "income":
                total_income += tx.amount
            else:
                total_expense += tx.amount
                # dict.get(key, 기본값): 키가 없으면 기본값 반환
                category_totals[tx.category] = (
                    category_totals.get(tx.category, 0) + tx.amount
                )

        # 카테고리별 지출 TOP N: 금액 기준 내림차순 정렬 후 상위 N개
        # sorted(iterable, key, reverse): 정렬
        # dict.items(): {key: value} → [(key, value), ...] 형태로 변환
        top_categories = sorted(
            category_totals.items(),  # [("food", 45000), ("rent", 150000), ...]
            key=lambda x: x[1],       # 금액(두 번째 값) 기준
            reverse=True,             # 내림차순
        )[:top_n]                     # 상위 N개만

        # 예산 조회
        budget_obj = self.budget_store.get(month)
        budget_amount = budget_obj.amount if budget_obj else None

        # 예산 사용률 계산
        usage_rate = None
        over_budget = False
        if budget_amount:
            # round(값, 소수점자리): 반올림
            usage_rate = round(total_expense / budget_amount * 100, 1)
            over_budget = total_expense > budget_amount

        return {
            "month": month,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
            "budget": budget_amount,
            "usage_rate": usage_rate,
            "over_budget": over_budget,
            "top_categories": top_categories,
            "has_data": total_income > 0 or total_expense > 0,
        }

    # ── 거래 수정 ───────────────────────────
    def update_transaction(self, tx_id: str, **fields) -> bool:
        """
        특정 ID의 거래를 수정합니다.
        수정할 필드만 키워드 인자로 전달합니다.
        예) service.update_transaction("TX-000001", amount=20000)
        """
        # 전달받은 필드 검증
        if "date" in fields:
            fields["date"] = validate_date(fields["date"])
        if "type" in fields:
            fields["type"] = validate_type(fields["type"])
        if "amount" in fields:
            # 수정 시 amount는 이미 int 또는 str로 올 수 있음
            fields["amount"] = validate_amount(str(fields["amount"]))
        if "category" in fields and not self.cat_store.exists(fields["category"]):
            raise ValueError(f"등록되지 않은 카테고리입니다: '{fields['category']}'")
        if "tags" in fields and isinstance(fields["tags"], str):
            # 태그가 문자열로 오면 리스트로 변환
            fields["tags"] = [t.strip() for t in fields["tags"].split(",") if t.strip()]

        return self.tx_repo.update(tx_id, **fields)

    # ── 거래 삭제 ───────────────────────────
    def delete_transaction(self, tx_id: str) -> bool:
        """특정 ID의 거래를 삭제합니다. 없는 ID면 False 반환."""
        return self.tx_repo.delete(tx_id)

    # ── 예산 설정 ───────────────────────────
    def set_budget(self, month: str, amount: str) -> Budget:
        """특정 월의 예산을 설정합니다."""
        validate_month(month)
        validated_amount = validate_amount(amount)
        self.budget_store.set(month, validated_amount)
        return Budget(month=month, amount=validated_amount)

    # ── 카테고리 관리 ───────────────────────
    def list_categories(self) -> List[str]:
        """등록된 모든 카테고리 이름을 반환합니다."""
        return self.cat_store.list_all()

    def add_category(self, name: str) -> bool:
        """카테고리를 추가합니다. 이미 있으면 False."""
        if not name.strip():
            raise ValueError("카테고리 이름은 빈 문자열일 수 없습니다.")
        return self.cat_store.add(name.strip())

    def remove_category(self, name: str) -> Tuple[bool, str]:
        """
        카테고리를 삭제합니다.
        사용 중인 카테고리(거래에서 참조 중)는 삭제를 막습니다.
        반환값: (성공 여부, 메시지)
        """
        # 해당 카테고리를 사용하는 거래가 있는지 확인
        for tx in self.tx_repo.stream_all():
            if tx.category == name:
                return False, (
                    f"'{name}' 카테고리를 사용하는 거래가 있어 삭제할 수 없습니다.\n"
                    f"[힌트] 해당 거래의 카테고리를 먼저 변경한 후 삭제하세요."
                )

        removed = self.cat_store.remove(name)
        if not removed:
            return False, f"'{name}' 카테고리가 존재하지 않습니다."
        return True, f"[완료] '{name}' 카테고리를 삭제했습니다."

    # ── CSV 내보내기 ─────────────────────────
    def export_csv(
        self,
        out_path: str,
        month: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> int:
        """
        조건에 맞는 거래를 CSV 파일로 내보냅니다.
        month 또는 from_date/to_date 중 하나는 반드시 지정해야 합니다.

        CSV 스키마 (미션 요구사항):
          date, type, category, amount, memo, tags
        """
        if not month and not (from_date or to_date):
            raise ValueError(
                "--month 또는 --from/--to 옵션 중 하나는 반드시 지정하세요."
            )

        # 내보낼 월의 날짜 범위 계산
        if month:
            validate_month(month)
            # 해당 월의 첫날~마지막날 계산
            from_date = f"{month}-01"
            # 다음 달 첫날 - 1일 = 이번 달 마지막날
            year, mon = int(month[:4]), int(month[5:])
            next_month = datetime.date(year + (mon // 12), (mon % 12) + 1, 1)
            last_day = next_month - datetime.timedelta(days=1)
            to_date = str(last_day)

        # CSV 파일 작성
        # csv.writer: 리스트를 CSV 형식으로 써주는 표준 라이브러리
        count = 0
        with open(out_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            # 헤더 행 작성 (미션 요구 스키마)
            writer.writerow(["date", "type", "category", "amount", "memo", "tags"])

            for tx in self.tx_repo.stream_all():
                if from_date and tx.date < from_date:
                    continue
                if to_date and tx.date > to_date:
                    continue
                # tags 리스트를 쉼표로 구분된 문자열로 변환
                writer.writerow([
                    tx.date, tx.type, tx.category, tx.amount,
                    tx.memo, ",".join(tx.tags)
                ])
                count += 1

        return count

    # ── CSV 가져오기 ─────────────────────────
    def import_csv(self, in_path: str) -> Tuple[int, int]:
        """
        CSV 파일에서 거래를 일괄 등록합니다.
        반환값: (imported 건수, skipped 건수)

        CSV 최소 스키마: date, type, category, amount, memo(선택), tags(선택)
        """
        imported = 0
        skipped = 0

        with open(in_path, "r", encoding="utf-8") as csvfile:
            # DictReader: 헤더 행을 키로 사용해 각 행을 dict로 읽어줌
            reader = csv.DictReader(csvfile)

            for row in reader:
                try:
                    # 필수 필드 검증
                    validate_date(row["date"])
                    validate_type(row["type"])
                    validate_amount(row["amount"])

                    # 카테고리 자동 추가 (없으면 추가 후 진행)
                    if not self.cat_store.exists(row["category"]):
                        self.cat_store.add(row["category"])

                    self.add_transaction(
                        type_=row["type"],
                        date=row["date"],
                        amount=row["amount"],
                        category=row["category"],
                        memo=row.get("memo", ""),      # 선택 필드는 get()으로 안전하게
                        tags=row.get("tags", ""),
                    )
                    imported += 1

                except (ValueError, KeyError):
                    # 검증 실패한 행은 건너뜀 (skipped 카운트)
                    skipped += 1

        return imported, skipped
