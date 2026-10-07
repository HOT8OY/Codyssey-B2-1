from dataclasses import dataclass
from .errors import ValidationError
from datetime import datetime
from typing import Literal, cast

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

