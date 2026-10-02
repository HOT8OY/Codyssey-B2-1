"""
repository.py — 파일 입출력 (저장소 계층)
==========================================
이 파일은 JSONL 파일에 데이터를 읽고 쓰는 역할만 담당합니다.
"저장소(Repository)" 패턴: 데이터를 어디에 어떻게 저장하는지를 한 곳에 모읍니다.
  덕분에 나중에 저장 방식을 바꾸더라도 이 파일만 수정하면 됩니다.

[담당 역할]
  - JSONL 파일 생성 및 초기화
  - 데이터 읽기 (제너레이터 스트리밍)
  - 데이터 쓰기 (추가/수정/삭제, 원자적 교체)
  - models.py 의 dataclass ↔ dict(JSON) 변환

[사용하는 파일]
  data/transactions.jsonl  ← 거래 내역
  data/categories.jsonl    ← 카테고리 목록
  data/budgets.jsonl       ← 월별 예산
"""

import json       # JSON 파싱 및 직렬화
import os         # 파일/폴더 존재 확인, 경로 조작
import tempfile   # 원자적 파일 교체를 위한 임시 파일 생성

# dataclasses.asdict: dataclass 객체를 dict로 변환해줍니다.
# 예) asdict(Transaction(...)) → {"id": "TX-000001", "type": "expense", ...}
from dataclasses import asdict

# Generator: 제너레이터 함수의 반환 타입을 명시하기 위해 임포트
# Optional: 값이 있을 수도 없을 수도 있는 타입 (None 허용)
from typing import Generator, List, Optional

# 같은 패키지의 models.py 에서 dataclass 정의를 가져옵니다
from models import Transaction, Category, Budget


# ──────────────────────────────────────────
# 기본 설정값
# ──────────────────────────────────────────
DEFAULT_DATA_DIR = "./data"  # 저장 폴더 기본 경로

# 초기 실행 시 자동으로 만들어줄 기본 카테고리 목록
DEFAULT_CATEGORIES = [
    "food",       # 식비
    "transport",  # 교통비
    "salary",     # 급여 (수입)
    "rent",       # 월세
    "shopping",   # 쇼핑
    "health",     # 의료/건강
    "education",  # 교육
    "etc",        # 기타
]


# ──────────────────────────────────────────
# 공통 유틸리티 함수
# ──────────────────────────────────────────
def ensure_data_dir(data_dir: str = DEFAULT_DATA_DIR) -> None:
    """
    data 폴더와 JSONL 파일들이 존재하는지 확인하고,
    없으면 자동으로 만들어줍니다. (초기 실행 처리)
    """
    # os.makedirs: 중간 폴더까지 한 번에 만들어줌
    # exist_ok=True: 이미 있어도 오류를 내지 않음
    os.makedirs(data_dir, exist_ok=True)

    # 각 JSONL 파일이 없으면 빈 파일 생성
    for filename in ["transactions.jsonl", "categories.jsonl", "budgets.jsonl"]:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            # "x" 모드: 파일이 없을 때만 생성 (이미 있으면 오류 → but os.path.exists로 이미 체크)
            with open(filepath, "w", encoding="utf-8") as f:
                pass  # 빈 파일만 만들면 됨

    # 카테고리 파일이 비어있으면 기본 카테고리를 자동으로 넣어줌
    categories_path = os.path.join(data_dir, "categories.jsonl")
    if os.path.getsize(categories_path) == 0:
        print("[초기화] 기본 카테고리를 생성합니다:", ", ".join(DEFAULT_CATEGORIES))
        for name in DEFAULT_CATEGORIES:
            _append_line(categories_path, {"name": name})


def _append_line(filepath: str, data: dict) -> None:
    """
    JSONL 파일의 맨 끝에 dict 하나를 JSON 한 줄로 추가합니다.
    이 함수는 모듈 내부에서만 쓰이는 헬퍼 함수입니다.
    (함수 이름이 _로 시작하면 "내부용"이라는 파이썬 관례입니다.)

    "a" 모드 = append(추가) 모드: 기존 내용을 지우지 않고 뒤에 이어씁니다.
    """
    with open(filepath, "a", encoding="utf-8") as f:
        # ensure_ascii=False: 한글이 \uXXXX 로 깨지지 않고 그대로 저장됨
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _stream_lines(filepath: str) -> Generator[dict, None, None]:
    """
    JSONL 파일을 한 줄씩 읽어 dict를 yield하는 제너레이터 함수.

    [핵심 개념: 스트리밍 처리]
    readlines()로 전체를 읽으면 100만 건도 한꺼번에 메모리에 올라옵니다.
    하지만 이 함수는 한 줄을 읽고 → yield(반환) → 다음 줄로 이동합니다.
    메모리에는 항상 한 줄 분량만 올라옵니다.

    Generator[dict, None, None] 타입 힌트 해석:
      - 첫 번째 dict: yield로 내보내는 값의 타입
      - 두 번째 None: send()로 받는 값 (사용 안 함)
      - 세 번째 None: return으로 반환하는 값 (없음)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:          # 파일을 한 줄씩 읽음 (파이썬 파일 객체 자체가 이터러블)
            line = line.strip() # 앞뒤 공백/줄바꿈 제거
            if not line:
                continue        # 빈 줄은 건너뜀
            yield json.loads(line)  # JSON 문자열 → dict 로 파싱 후 반환


def _rewrite_file(filepath: str, rows: List[dict]) -> None:
    """
    파일 전체를 새 내용으로 덮어씁니다. (수정/삭제 시 사용)

    [원자적 교체 방식 - 데이터 안전성]
    파일을 직접 수정하면 중간에 오류가 나면 파일이 깨질 수 있습니다.
    대신:
      1. 임시 파일에 새 내용을 전부 씀
      2. 성공하면 임시 파일을 원본 파일로 교체
    → 오류가 나도 원본은 손대지 않아 안전합니다 (전부 성공 or 전부 실패).
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))

    # tempfile.NamedTemporaryFile: 임시 파일을 안전하게 생성
    # delete=False: with 블록이 끝나도 파일을 자동 삭제하지 않음 (교체에 필요)
    # suffix=".tmp": 파일 이름 끝에 .tmp 붙여서 임시 파일임을 표시
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8",
        dir=dir_name, delete=False, suffix=".tmp"
    ) as tmp_file:
        tmp_path = tmp_file.name  # 나중에 교체할 때 필요하므로 경로를 기억

        for row in rows:
            tmp_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    # os.replace: 임시 파일을 원본 파일 자리로 이동 (원자적 연산)
    # 이 한 줄이 실행되는 순간에만 파일이 바뀝니다.
    os.replace(tmp_path, filepath)


# ──────────────────────────────────────────
# TransactionRepository — 거래 내역 저장소
# ──────────────────────────────────────────
class TransactionRepository:
    """
    transactions.jsonl 파일에 대한 모든 읽기/쓰기를 담당합니다.
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.filepath = os.path.join(data_dir, "transactions.jsonl")

    def next_id(self) -> str:
        """
        현재 파일에서 가장 큰 ID를 찾아 다음 ID를 생성합니다.
        예: 마지막 ID가 TX-000003 이면 TX-000004 반환.
        파일이 비어있으면 TX-000001 반환.
        """
        max_num = 0
        for row in _stream_lines(self.filepath):
            # ID 형식: "TX-XXXXXX" → 숫자 부분만 추출
            try:
                num = int(row["id"].split("-")[1])  # "TX-000003" → 3
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass  # 잘못된 ID 형식은 무시
        # zfill(6): 숫자를 6자리로 맞추고 앞을 0으로 채움 (예: 4 → "000004")
        return f"TX-{str(max_num + 1).zfill(6)}"

    def add(self, tx: Transaction) -> None:
        """거래 한 건을 파일 끝에 추가합니다."""
        # asdict(): dataclass 객체를 dict로 변환
        _append_line(self.filepath, asdict(tx))

    def stream_all(self) -> Generator[Transaction, None, None]:
        """
        파일의 모든 거래를 스트리밍으로 하나씩 yield합니다.
        메모리에 전체를 올리지 않아 대용량 파일도 처리 가능합니다.
        """
        for row in _stream_lines(self.filepath):
            # **row: dict의 키-값을 Transaction의 인자로 풀어서 전달
            # 예) Transaction(**{"id": "TX-1", "type": "expense", ...})
            #   = Transaction(id="TX-1", type="expense", ...)
            yield Transaction(**row)

    def find_by_id(self, tx_id: str) -> Optional[Transaction]:
        """ID로 특정 거래를 찾아 반환합니다. 없으면 None 반환."""
        for tx in self.stream_all():
            if tx.id == tx_id:
                return tx
        return None  # 찾지 못한 경우

    def update(self, tx_id: str, **fields) -> bool:
        """
        특정 ID의 거래를 수정합니다.
        **fields: 수정할 필드만 키워드 인자로 전달합니다.
          예) repo.update("TX-000001", amount=20000, memo="수정된 메모")

        반환값: 수정 성공이면 True, 해당 ID 없으면 False
        """
        rows = []    # 수정된 내용을 담을 리스트
        found = False

        for row in _stream_lines(self.filepath):
            if row["id"] == tx_id:
                # 해당 ID를 찾으면 전달받은 필드만 업데이트
                row.update(fields)  # dict.update(): 지정한 키-값만 덮어씀
                found = True
            rows.append(row)

        if found:
            _rewrite_file(self.filepath, rows)  # 원자적 교체로 파일 덮어쓰기
        return found

    def delete(self, tx_id: str) -> bool:
        """
        특정 ID의 거래를 삭제합니다.
        반환값: 삭제 성공이면 True, 해당 ID 없으면 False
        """
        rows = []
        found = False

        for row in _stream_lines(self.filepath):
            if row["id"] == tx_id:
                found = True
                # 이 행을 rows에 추가하지 않음 = 삭제 효과
            else:
                rows.append(row)

        if found:
            _rewrite_file(self.filepath, rows)
        return found


# ──────────────────────────────────────────
# CategoryStore — 카테고리 저장소
# ──────────────────────────────────────────
class CategoryStore:
    """
    categories.jsonl 파일에 대한 모든 읽기/쓰기를 담당합니다.
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.filepath = os.path.join(data_dir, "categories.jsonl")

    def list_all(self) -> List[str]:
        """등록된 모든 카테고리 이름을 리스트로 반환합니다."""
        # 리스트 컴프리헨션: [표현식 for 변수 in 이터러블]
        # _stream_lines로 스트리밍 읽기 후 name 필드만 추출
        return [row["name"] for row in _stream_lines(self.filepath)]

    def exists(self, name: str) -> bool:
        """해당 이름의 카테고리가 등록되어 있는지 확인합니다."""
        return name in self.list_all()

    def add(self, name: str) -> bool:
        """
        카테고리를 추가합니다.
        반환값: 추가 성공이면 True, 이미 존재하면 False
        """
        if self.exists(name):
            return False  # 중복 허용 안 함
        _append_line(self.filepath, {"name": name})
        return True

    def remove(self, name: str) -> bool:
        """
        카테고리를 삭제합니다.
        반환값: 삭제 성공이면 True, 없는 카테고리면 False
        """
        rows = []
        found = False

        # 파일을 한 번만 읽으면서 해당 카테고리를 제외한 나머지를 수집
        for row in _stream_lines(self.filepath):
            if row["name"] == name:
                found = True  # 삭제 대상 발견 → rows에 넣지 않음 (= 삭제)
            else:
                rows.append(row)

        if not found:
            return False  # 삭제할 항목이 없었음

        _rewrite_file(self.filepath, rows)
        return True


# ──────────────────────────────────────────
# BudgetStore — 예산 저장소
# ──────────────────────────────────────────
class BudgetStore:
    """
    budgets.jsonl 파일에 대한 모든 읽기/쓰기를 담당합니다.
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.filepath = os.path.join(data_dir, "budgets.jsonl")

    def get(self, month: str) -> Optional[Budget]:
        """특정 월의 예산을 찾아 반환합니다. 없으면 None."""
        for row in _stream_lines(self.filepath):
            if row["month"] == month:
                return Budget(**row)
        return None

    def set(self, month: str, amount: int) -> None:
        """
        특정 월의 예산을 설정합니다.
        이미 설정된 달이면 수정, 없으면 새로 추가합니다.
        """
        rows = []
        found = False

        for row in _stream_lines(self.filepath):
            if row["month"] == month:
                row["amount"] = amount  # 기존 예산 업데이트
                found = True
            rows.append(row)

        if found:
            _rewrite_file(self.filepath, rows)  # 기존 항목 수정
        else:
            _append_line(self.filepath, {"month": month, "amount": amount})  # 새로 추가
