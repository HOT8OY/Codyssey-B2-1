from dataclasses import dataclass, field, asdict
from .errors import ValidationError
from datetime import datetime
from typing import Literal, cast, Any

# ---------------------------------------------------------------------------
# 상수와 타입 별칭
# ---------------------------------------------------------------------------
TxType = Literal["income", "expense"]

VALID_TYPES: tuple[str, ...] = ("income", "expense")

DATE_FORMAT = "%Y-%m-%d"    # 2024-01-15
MONTH_FORMAT = "%Y-%m"      # 2024- 01


# ===========================================================================
# 1. 검증(파싱) 함수들
# ===========================================================================

def parse_date(value: str) -> str:
    """ YYYY-MM_DD 형식의 날짜 문자열을 검증하고 정리하여 반환.
    ex: parse_date(2024-1-5) -> 2024-01-05"""

    text = value.strip() # 앞뒤 공백 제거

    try:
        # striptime은 실제 달력 기준으로 검사, 문자열을 실제 날짜 객체로 바꿈.
        parsed = datetime.strptime(text, DATE_FORMAT)

    except ValueError:
        raise ValidationError(
            "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).",
            "예: 2024-01-15"
        ) from None # 여기서 작성한 메시지로 바꿔 던지기 위해 원래 발생한 ValueError 정보를 숨김

    # strftime으로 문자열을 2024-01-05처럼 10글자 형식으로 통일
    # 추후 문자열 비교만으로 크기 비교가 가능해짐.
    return parsed.strftime(DATE_FORMAT)

def parse_month(value: str) -> str:
    """ 'YYYY-MM' 형식의 월 문자열을 검증. (summary, budget, export에서 사용)"""

    text = value.strip()

    try:
        parsed = datetime.strptime(text, MONTH_FORMAT)
    
    except ValueError:
        raise ValidationError(
            "월 형식이 올바르지 않습니다 (YYYY-MM).",
            "예: 2024-01",
        ) from None
    return parsed.strftime(MONTH_FORMAT)

def parse_type(value: str) -> TxType:
    """거래 타입(income/expense)을 검증. 대소문자는 구분하지 않음."""    
    text = value.strip().lower()
    if text not in VALID_TYPES:
        raise ValidationError(
            f"허용되지 않은 타입입니다: '{value}'",
            "income(수입) 또는 expense(지출) 중 하나를 입력하세요.",
        )
    return cast(TxType, text)

def parse_amount(value:str | int) -> int:
    """금액을 검증. 0보다 큰 정수여야 함.

    - 입력될 값이 "15000", "15,000", int(15000)일 수도 있기 때문에,
    매개변수 타입을 'str | int'로 적음"""
    # 파이썬에서 bool은 int의 자식 클래스이므로 True가 1원으로 저장되는걸 걸러내야함
    if isinstance(value, bool):
        raise ValidationError("금액은 숫자여야 합니다.", "예: 15000")

    if isinstance(value, int):
        amount = value
    else:
        text = str(value).strip().replace(",", "") # 15,000 -> 15000
        try:
            amount = int(text)
        except ValueError:
            raise ValidationError(
                f"금액은 정수로 입력해야 합니다: '{value}'",
                "예: 15000 또는 15,000 (소수점, 문자 불가)",
            ) from None
    
    if amount <= 0:
        raise ValidationError(
            "금액은 0보다 큰 양수여야 합니다.",
            "지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다."
        )
    
    return amount

def parse_category_name(value: str) -> str:
    """카테고리 이름 '형식'만 검증합니다.
    등록 여부는 service.py에서 확인.

    - 앞뒤 공백 제거, 소문자로 통일 -> "Food", "food" 모두 "food"로 취급
    """
    text = value.strip().lower()
    if not text:
        raise ValidationError("카테고리 이름이 비어있습니다.", "예: food")
    if "," in text:
        # 쉽표는 CSV의 구분자라서 이름에 들어가면 햇갈리기에 금지.
        raise ValidationError("카테고리 이름에는 쉽표(,)를 쓸 수 없습니다.", "예: food")
    return text

def parse_tags(value: str | list[str] | None) -> list[str]:
    """태그를 리스트로 정리합니다. 이 함수는 실패하지 않습니다.

    >>> parse_tags("meal, 회식,,meal")
    ['meal', '회식']
    >>> parse_tags(None)
    []
    """
    if value is None:
        return []
    # 문자열이면 쉼표로 쪼개고, 이미 리스트면 그대로 사용
    raw_items = value.split(",") if isinstance(value, str) else value
    
    tags: list[str] = []
    for item in raw_items:
        tag = str(item).strip()
        # 빈 문자열("")과 중복 태그는 건너뜀. (입력 순서는 유지)
        if tag and tag not in tags:
            tags.append(tag)
    return tags

# ===========================================================================
# 2. 데이터 클래스들
# ===========================================================================

@dataclass
class Transaction:
    """거래 내역 1건을 표현하는 데이터 클래스.
    """
    # 생성자
    id: str
    type: TxType
    date: str
    amount: int
    category: str
    memo: str = ""
    # list같은 mutable한 값은 기본값 '=[]'로 쓰면 모든 객체가 같은 리스트 하나를 공유하는 버그 발생함.
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """dataclass가 자동 생성한 __init__이 끝난 직후 자동 호출.
        여기서 검증에 통과하면 Transaction 객체가 만들어지고 이는 값이 올바르다는것을 보증함.
        """
        self.type = parse_type(self.type)
        self.date = parse_date(self.date)
        self.amount = parse_amount(self.amount)
        self.category = parse_category_name(self.category)
        self.memo = (self.memo or "").strip()
        self.tags = parse_tags(self.tags)
    
    @property
    def month(self) -> str:
        """'2024-01-15' -> '2024-01' (월별 요약에서 사용)"""
        return self.date[:7]
    
    @property
    def sort_key(self) -> tuple[str, str]:
        """최신순 정렬 기준: (날짜, id)

        같은 날짜에 여러 거래가 있으면 id가 큰 순으로 정렬"""
        return (self.date, self.id)
    
    def to_dict(self) -> dict[str, Any]:
        """객체 -> 딕셔너리 변환. json.dump()는 객체를 저장할 수 없음."""
        return asdict(self)

@dataclass
class MonthlySummary:
    """월별 요약 '결과'를 담는 데이터 클래스.

    서비스(services.py)는 계산만 해서 이 객체를 돌려주고,
    출력은 CLI(cli.py)가 담당함.
    """
    month: str
    total_income: int = 0
    total_expense: int = 0
    count: int = 0 # 해당 월의 거래 건수
    expense_by_category: dict[str, int] = field(default_factory=dict)
    budget: int | None = None   # 예산이 설정되지 않앗다면 None

    @property
    def has_data(self) -> bool:
        return self.count > 0
    
    @property
    def balance(self) -> int:
        """잔액 = 총수입 - 총지출"""
        return self.total_income - self.total_expense
    
    @property
    def budget_usage(self) -> float | None:
        """예산 사용률(%). 예산이 없으면 None."""
        if self.budget is None:
            return None
        # budget은 parse_amount를 거쳐 항상 양수이므로 0으로 나눌 걱정이 없음.
        return self.total_expense / self.budget * 100
    
    @property
    def is_over_budget(self) -> bool:
        """예산이 None이 아니며 예산보다 총 지출이 클 경우 True"""
        return self.budget is not None and self.total_expense > self.budget
    
    def top_categories(self, n: int) -> list[tuple[str,int]]:
        """지출이 큰 카테고리 상위 n개를 [(이름, 금액), ...] 형태로 반환.

        sorted의 key에 (-금액, 이름)을 주면
          1순위: 금액 내림차순 (음수로 바꿔서 오름차순 정렬 = 원래 값 내림차순)
          2순위: 금액이 같으면 이름 오름차순 (결과가 항상 같은 순서로 나오도록)
        """
        items = sorted(self.expense_by_category.items(), key=lambda kv: (-kv[1], kv[0]))
        return items[:n]

@dataclass
class ImportResult:
    """CSV 가져오기 결과. 몇 건 성공/실패했는지와 실패 사유를 담음."""
    
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
