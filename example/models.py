"""
models.py — 데이터 모델(Model) 계층
=====================================

[이 파일의 역할]
"가계부에 저장되는 데이터가 어떻게 생겼는지"와 "어떤 값이 올바른 값인지"를 정의합니다.

- 파일을 읽거나 쓰지 않습니다.      → repository.py 담당
- 화면에 출력하거나 입력받지 않습니다. → cli.py 담당
- 오직 "데이터의 모양"과 "검증 규칙"만 다룹니다.

이렇게 역할을 좁혀 두면, 예를 들어 저장 포맷을 JSONL → CSV로 바꾸더라도
이 파일은 전혀 고칠 필요가 없습니다. 이것이 "계층을 나누는" 가장 큰 이유입니다.

[의존 방향]
    cli → services → repository → models
models는 가장 안쪽 계층이라 다른 계층을 import 하지 않습니다. (errors.py만 예외)
"""

# ---------------------------------------------------------------------------
# import 구역
# ---------------------------------------------------------------------------
# dataclass : 클래스에 @dataclass를 붙이면 __init__, __repr__, __eq__ 등을
#             자동으로 만들어 주는 표준 라이브러리 기능입니다.
# field     : dataclass 필드의 세부 옵션(기본값 생성 방법 등)을 지정할 때 사용합니다.
# asdict    : dataclass 객체를 dict로 바꿔줍니다. (JSON 저장용)
from dataclasses import asdict, dataclass, field
from datetime import datetime

# typing: "타입 힌트"를 위한 도구들입니다.
#   Any     : 아무 타입이나 올 수 있음
#   Literal : 특정 '값'만 허용함을 표현 (예: "income" 또는 "expense"만)
#   cast    : "이 값은 이 타입이 맞아"라고 타입 검사기에게 알려주는 함수 (실행 시엔 아무 일도 안 함)
from typing import Any, Literal, cast

# 같은 패키지(폴더) 안의 errors.py에서 가져옵니다.
# 앞의 점(.)은 "현재 패키지 기준"이라는 뜻의 '상대 import'입니다.
from .errors import ValidationError

# ---------------------------------------------------------------------------
# 상수와 타입 별칭
# ---------------------------------------------------------------------------
# 타입 별칭(Type Alias): 긴 타입 표현에 이름을 붙여 재사용합니다.
# TxType 이라고 쓰면 "income 또는 expense 문자열"이라는 뜻이 됩니다.
TxType = Literal["income", "expense"]

# 허용되는 타입 목록. 튜플(tuple)은 수정할 수 없어서 상수에 적합합니다.
VALID_TYPES: tuple[str, ...] = ("income", "expense")

DATE_FORMAT = "%Y-%m-%d"   # 2024-01-15
MONTH_FORMAT = "%Y-%m"     # 2024-01


# ===========================================================================
# 1. 검증(파싱) 함수들
# ===========================================================================
# "parse_xxx" 함수들은 공통 규칙을 따릅니다.
#   - 입력: 사용자가 입력한 문자열 (또는 파일에서 읽은 값)
#   - 출력: 검증을 통과하고 '정리된(normalized)' 값
#   - 실패: ValidationError를 발생시킴 (message + hint 포함)
#
# 검증 로직을 함수로 분리해 두면 add(대화형), update(옵션), import(CSV)
# 어디서든 "똑같은 규칙"을 재사용할 수 있습니다. → 규칙이 한 곳에만 존재!
# ===========================================================================


def parse_date(value: str) -> str:
    """'YYYY-MM-DD' 형식의 날짜 문자열을 검증하고 정리해서 돌려줍니다.

    >>> parse_date("2024-1-5")
    '2024-01-05'
    """
    text = value.strip()  # 앞뒤 공백 제거 (" 2024-01-15 " → "2024-01-15")
    try:
        # strptime(문자열, 형식): 문자열을 실제 날짜 객체로 바꿔봅니다.
        # 정규식으로 "숫자4-숫자2-숫자2"만 검사하면 2024-13-40 같은
        # '형식은 맞지만 존재하지 않는 날짜'를 걸러낼 수 없습니다.
        # strptime은 실제 달력 기준으로 검사하므로 13월, 40일, 2023-02-29 등을 모두 거릅니다.
        parsed = datetime.strptime(text, DATE_FORMAT)
    except ValueError:
        # `from None`: 원래 발생한 ValueError 정보를 숨깁니다.
        # (우리가 더 친절한 메시지로 바꿔서 다시 던지는 것이므로)
        raise ValidationError(
            "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).",
            "예: 2024-01-15",
        ) from None

    # strftime으로 다시 문자열로 만들면 "2024-1-5" → "2024-01-05"처럼 항상
    # 10글자 형식으로 통일됩니다. 이렇게 통일해 두면 나중에 날짜를
    # '문자열 비교'만으로 크기 비교할 수 있습니다. ("2024-01-05" < "2024-01-15")
    return parsed.strftime(DATE_FORMAT)


def parse_month(value: str) -> str:
    """'YYYY-MM' 형식의 월 문자열을 검증합니다. (summary, budget, export에서 사용)"""
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
    """거래 타입(income/expense)을 검증합니다. 대소문자는 구분하지 않습니다."""
    text = value.strip().lower()  # "Income" → "income"
    if text not in VALID_TYPES:
        raise ValidationError(
            f"허용되지 않은 타입입니다: '{value}'",
            "income(수입) 또는 expense(지출) 중 하나를 입력하세요.",
        )
    # 위 if문을 통과했다면 text는 반드시 "income" 또는 "expense"입니다.
    # 하지만 타입 검사기는 그걸 모르므로 cast로 알려줍니다.
    return cast(TxType, text)


def parse_amount(value: str | int) -> int:
    """금액을 검증합니다. 반드시 0보다 큰 정수여야 합니다.

    - 사용자는 "15000" 또는 "15,000"처럼 입력할 수 있습니다.
    - 파일에서 읽을 때는 이미 int(15000)일 수도 있습니다.
    그래서 매개변수 타입을 `str | int` (str 또는 int)로 적었습니다.
    """
    # 주의! 파이썬에서 bool은 int의 자식 클래스라서 True == 1 입니다.
    # True가 금액 1원으로 저장되는 실수를 막기 위해 먼저 걸러냅니다.
    if isinstance(value, bool):
        raise ValidationError("금액은 숫자여야 합니다.", "예: 15000")

    if isinstance(value, int):
        amount = value
    else:
        text = str(value).strip().replace(",", "")  # "15,000" → "15000"
        try:
            amount = int(text)
        except ValueError:
            raise ValidationError(
                f"금액은 정수로 입력해야 합니다: '{value}'",
                "예: 15000 또는 15,000 (소수점·문자 불가)",
            ) from None

    if amount <= 0:
        raise ValidationError(
            "금액은 0보다 큰 양수여야 합니다.",
            "지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다.",
        )
    return amount


def parse_category_name(value: str) -> str:
    """카테고리 이름 '형식'만 검증합니다. (등록 여부는 services.py에서 확인)

    - 앞뒤 공백 제거, 소문자로 통일 → "Food", " food " 모두 "food"로 취급
    """
    text = value.strip().lower()
    if not text:
        raise ValidationError("카테고리 이름이 비어 있습니다.", "예: food")
    if "," in text:
        # 쉼표는 CSV의 구분자라서 이름에 들어가면 헷갈리므로 금지합니다.
        raise ValidationError("카테고리 이름에는 쉼표(,)를 쓸 수 없습니다.", "예: food")
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
    # 문자열이면 쉼표로 쪼개고, 이미 리스트면 그대로 사용합니다.
    raw_items = value.split(",") if isinstance(value, str) else value

    tags: list[str] = []
    for item in raw_items:
        tag = str(item).strip()
        # 빈 문자열("")과 중복 태그는 건너뜁니다. (입력 순서는 유지)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


# ===========================================================================
# 2. 데이터 클래스들
# ===========================================================================


@dataclass
class Transaction:
    """거래 내역 1건을 표현하는 데이터 클래스.

    @dataclass 덕분에 아래처럼 쓸 수 있습니다. (__init__을 직접 안 써도 됨!)
        tx = Transaction(id="TX-000001", type="expense", date="2024-01-15",
                         amount=15000, category="food", memo="점심", tags=["meal"])
        print(tx.amount)  # 15000
    """

    # "필드이름: 타입" 형태로 적으면 dataclass가 이것을 생성자 매개변수로 만듭니다.
    id: str
    type: TxType
    date: str
    amount: int
    category: str
    # 기본값이 있는 필드는 반드시 기본값 없는 필드 '뒤에' 와야 합니다.
    memo: str = ""
    # ⚠️ 리스트 같은 '변경 가능한(mutable)' 기본값은 `= []`로 쓰면 안 됩니다!
    # 모든 객체가 같은 리스트 하나를 공유하는 버그가 생기기 때문입니다.
    # default_factory=list 는 "객체를 만들 때마다 새 빈 리스트를 만들어라"는 뜻입니다.
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """dataclass가 자동 생성한 __init__이 끝난 '직후'에 자동으로 호출됩니다.

        여기서 검증을 하면 "Transaction 객체가 존재한다 = 값이 올바르다"가 보장됩니다.
        잘못된 객체는 아예 만들어질 수 없습니다.

        또한 dataclasses.replace()로 일부 필드만 바꾼 복사본을 만들 때도
        __init__ → __post_init__이 다시 실행되므로, update 시에도 검증이 자동으로 됩니다.
        """
        self.type = parse_type(self.type)
        self.date = parse_date(self.date)
        self.amount = parse_amount(self.amount)
        self.category = parse_category_name(self.category)
        self.memo = (self.memo or "").strip()
        self.tags = parse_tags(self.tags)

    # @property: 메서드를 '속성처럼' 괄호 없이 쓸 수 있게 해줍니다.
    #   tx.month   (O)      tx.month()  (X)
    @property
    def month(self) -> str:
        """'2024-01-15' → '2024-01'  (월별 요약에서 사용)"""
        return self.date[:7]  # 문자열 앞 7글자 자르기(슬라이싱)

    @property
    def sort_key(self) -> tuple[str, str]:
        """최신순 정렬 기준: (날짜, id)

        같은 날짜에 여러 거래가 있으면 id가 큰(= 나중에 추가된) 것이 더 최신입니다.
        id가 "TX-000012"처럼 0으로 채워진 고정 길이라서 문자열 비교로도 순서가 맞습니다.
        (만약 "TX-12"처럼 저장했다면 "TX-9" > "TX-12"가 되어버려 순서가 틀어집니다!)
        """
        return (self.date, self.id)

    def to_dict(self) -> dict[str, Any]:
        """객체 → dict 변환. json.dumps()는 dict는 저장할 수 있지만 객체는 못 하기 때문입니다."""
        return asdict(self)

    # @classmethod: 객체가 아니라 '클래스 자체'에서 호출하는 메서드입니다.
    #   Transaction.from_dict({...})  처럼 씁니다.
    # 첫 매개변수 cls에는 Transaction 클래스가 들어옵니다.
    # "dict를 받아 새 객체를 만드는" 대체 생성자 용도로 자주 쓰입니다.
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """dict → 객체 변환. (파일에서 읽은 JSON 한 줄을 객체로 바꿀 때 사용)

        반환 타입을 "Transaction"처럼 따옴표로 감싼 이유:
        클래스를 정의하는 '도중'이라 아직 Transaction이라는 이름이 완성되지 않았기 때문입니다.
        """
        try:
            return cls(
                id=str(data["id"]),
                type=data["type"],
                date=data["date"],
                amount=data["amount"],
                category=data["category"],
                # .get(키, 기본값): 키가 없어도 에러 대신 기본값을 돌려줍니다. (선택 필드용)
                memo=data.get("memo") or "",
                tags=data.get("tags") or [],
            )
        except KeyError as error:
            # data["id"]처럼 필수 키가 없으면 KeyError가 납니다.
            raise ValidationError(
                f"거래 데이터에 필수 항목 {error.args[0]!r}이(가) 없습니다.",
                "저장 파일이 손상되었을 수 있습니다.",
            ) from None


@dataclass
class Budget:
    """월 예산 1건. 예) Budget(month="2024-01", amount=500000)"""

    month: str
    amount: int

    def __post_init__(self) -> None:
        self.month = parse_month(self.month)
        self.amount = parse_amount(self.amount)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budget":
        try:
            return cls(month=data["month"], amount=data["amount"])
        except KeyError as error:
            raise ValidationError(
                f"예산 데이터에 필수 항목 {error.args[0]!r}이(가) 없습니다.",
                "저장 파일이 손상되었을 수 있습니다.",
            ) from None


@dataclass
class MonthlySummary:
    """월별 요약 '결과'를 담는 데이터 클래스.

    서비스(services.py)는 계산만 해서 이 객체를 돌려주고,
    출력은 CLI(cli.py)가 담당합니다.
    → "계산"과 "출력"을 분리하면, 나중에 출력 모양만 바꾸거나
      계산 결과만 따로 테스트하기가 쉬워집니다.
    """

    month: str
    total_income: int = 0
    total_expense: int = 0
    count: int = 0  # 해당 월의 거래 건수
    expense_by_category: dict[str, int] = field(default_factory=dict)
    budget: int | None = None  # 예산이 설정되지 않았으면 None

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
        # budget은 parse_amount를 거쳐 항상 양수이므로 0으로 나눌 걱정이 없습니다.
        return self.total_expense / self.budget * 100

    @property
    def is_over_budget(self) -> bool:
        return self.budget is not None and self.total_expense > self.budget

    def top_categories(self, n: int) -> list[tuple[str, int]]:
        """지출이 큰 카테고리 상위 n개를 [(이름, 금액), ...] 형태로 돌려줍니다.

        sorted의 key에 (-금액, 이름)을 주면
          1순위: 금액 내림차순 (음수로 바꿔서 오름차순 정렬 = 원래 값 내림차순)
          2순위: 금액이 같으면 이름 오름차순 (결과가 항상 같은 순서로 나오도록)
        """
        items = sorted(self.expense_by_category.items(), key=lambda kv: (-kv[1], kv[0]))
        return items[:n]


@dataclass
class ImportResult:
    """CSV 가져오기 결과. 몇 건 성공/실패했는지와 실패 사유를 담습니다."""

    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
