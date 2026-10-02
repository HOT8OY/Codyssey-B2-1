"""
models.py — 데이터 모델 정의
==============================
이 파일은 프로그램에서 다루는 데이터의 "설계도(모델)"를 담습니다.
Python의 dataclass를 사용해 각 데이터 구조를 선언합니다.

[계층 구조]
  models.py       ← 지금 이 파일 (데이터 구조 정의)
  repository.py   ← 파일 입출력 (저장/읽기)
  services.py     ← 비즈니스 로직 (계산, 검증)
  cli.py          ← 터미널 명령어 처리 (사용자 인터페이스)
"""

# dataclass: 데이터를 담는 클래스를 간편하게 만들어주는 데코레이터
# 일반 클래스를 만들면 __init__, __repr__ 등을 직접 써야 하지만,
# @dataclass를 붙이면 자동으로 생성해줍니다.
from dataclasses import dataclass, field

# field: dataclass에서 기본값을 동적으로 설정할 때 사용 (예: 빈 리스트)
# List: 타입 힌트에서 리스트 타입을 표현하기 위해 임포트
from typing import List, Optional


# ──────────────────────────────────────────
# 1. 거래 내역 모델 (Transaction)
# ──────────────────────────────────────────
@dataclass
class Transaction:
    """
    거래 한 건을 표현하는 데이터 클래스.
    
    JSONL 파일의 한 줄이 이 객체 하나와 1:1로 대응됩니다.
    예시 JSON:
        {"id": "TX-000001", "type": "expense", "date": "2024-01-15",
         "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}
    """

    # 필수 필드 (기본값 없음 → 반드시 값을 넣어야 함)
    id: str          # 고유 식별자. 예: "TX-000001"
    type: str        # 거래 종류. "income"(수입) 또는 "expense"(지출)만 허용
    date: str        # 날짜. YYYY-MM-DD 형식 문자열. 예: "2024-01-15"
    amount: int      # 금액. 반드시 양수 정수. 예: 15000
    category: str    # 카테고리 이름. categories.jsonl에 등록된 것만 허용

    # 선택 필드 (기본값 있음 → 입력하지 않아도 됨)
    memo: str = ""                          # 메모. 비어있으면 빈 문자열
    tags: List[str] = field(default_factory=list)
    # tags에 기본값으로 [] 를 쓰면 안 됩니다!
    # Python dataclass에서 리스트/딕셔너리 같은 "가변 객체"를 기본값으로 쓰면
    # 모든 인스턴스가 같은 리스트를 공유하는 버그가 생깁니다.
    # field(default_factory=list) 를 쓰면 인스턴스마다 새 리스트를 만들어줍니다.


# ──────────────────────────────────────────
# 2. 카테고리 모델 (Category)
# ──────────────────────────────────────────
@dataclass
class Category:
    """
    카테고리 하나를 표현하는 데이터 클래스.
    
    예시 JSON:
        {"name": "food"}
    """
    name: str    # 카테고리 이름. 유일해야 함. 예: "food", "transport"


# ──────────────────────────────────────────
# 3. 예산 모델 (Budget)
# ──────────────────────────────────────────
@dataclass
class Budget:
    """
    특정 월의 예산을 표현하는 데이터 클래스.
    
    예시 JSON:
        {"month": "2024-01", "amount": 500000}
    """
    month: str   # 예산 적용 월. YYYY-MM 형식. 예: "2024-01"
    amount: int  # 해당 월의 예산 금액 (원 단위). 예: 500000
