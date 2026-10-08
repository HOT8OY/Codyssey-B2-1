from budget_app.errors import ValidationError
from budget_app.models import Budget
import tempfile
import logging
import os
from json import JSONDecodeError
import json
from typing import Any
from collections.abc import Iterator, Iterable
from pathlib import Path

# print를 대신하여 기록을 남김. 로거 설정은 cli.py의 setup_logging에서 함.
logger = logging.getLogger("budget_app")

# 카테고리 파일이 비어있을 때 자동으로 만들어줄 기본 카테고리
DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "salary", "etc")

# 거래 id 접두사. "TX-" + 6자리 숫자 -> TX-000001
ID_PREFIX = "TX-"

# ===========================================================================
# 1. 공통 JSONL 유틸 함수
# ===========================================================================

def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """JSONL 파일을 한 줄씩 읽어서 dict로 하나씩 돌려주는 제너레이터.
    """

    # 파일이 없으면 아무것도 yield하지 않고 끝
    if not path.exists():
        return
    
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue # 빈 줄 건너뜀

            try:
                record = json.loads(line)   # 문자열 -> dict
            except JSONDecodeError:
                logger.warning("%s %d번째 줄이 올바른 JSON이 아니라서 건너뜁니다.", path.name, line_no)
                continue
        
        if isinstance(record, dict):
            yield record

def append_jsonl(path:Path, record: dict[str, Any]) -> None:
    """JSONL 파일 끝에 한 줄을 추가함. 기존 내용은 건드리지 않음."""
    with path.open("a", encoding="utf-8") as file:
        # ensure_ascii=False : 한글을 변환하지 않고 그대로 저장함
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

def rewrite_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """파일 전체를 새 내용으로 안전하게 원자적 교체.
    
    tmp파일을 만들고 거기에 새 내용을 다 씀.
    다 쓰고난 후 os.replace(임시파일, 원본)로 이름을 바꾸기.
    os.replace는 운영체제 수준에서 한 번에 일어나는 동작이라 안전함.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # mkstemp를 사용하여 이름이 겹치지 않는 임시 파일을 같은 폴더내에 만듦.
    # os.replace는 같은 디스크 내에서만 원자적이기 때문.
    # fd는 파일 번호, tmp_name은 임시 파일 경로
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()            # 파이썬 내부 버퍼 -> 운영체제
            os.fsync(file.fileno()) # 운영체제 버퍼 -> 실제 디스크에 기록
        os.replace(tmp_name, path)  # 바꿔치기
    except BaseException:
        # 실패시 임시파일 지우고 예외 던짐
        Path(tmp_name).unlink(missing_ok=True)
        raise

# ===========================================================================
# 2. CategoryStore — categories.jsonl
# ===========================================================================
# 파일 한 줄 예시: {"name": "food"}

class CategoryStore:
    """카테고리 목록을 파일에 저장/조회하는 클래스."""
    
    def __init__(self, path: Path) -> None:
        self.path = path
        self._ensure_defaults()
    
    def _ensure_defaults(self) -> None:
        """카테고리 파일이 없거나 비어 있으면 기본 카테고리를 만듦."""
        has_any = any(True for _ in iter_jsonl(self.path))
        if not has_any:     # (... for ... in ...)는 제너레이터 표현식
            rewrite_jsonl(self.path, ({"name": name} for name in DEFAULT_CATEGORIES))
            logger.info("기본 카테고리를 생성했습니다: %s", ", ".join(DEFAULT_CATEGORIES))
    
    def list_names(self) -> list[str]:
        """등록된 카테고리 이름 목록.
        """
        names: list[str] = []
        for record in iter_jsonl(self.path):
            name = str(record.get("name", "")).strip().lower()
            if name and name not in names:
                names.append(name)
        return names
    
    def exists(self, name: str) -> bool:
        return name in self.list_names()
    
    def add(self, name: str) -> bool:
        """카테고리 추가. 이미 있으면 False, 새로 추가했으면 True."""
        if self.exists(name):
            return False
        append_jsonl(self.path, {"name": name})
        return True
    
    def remove(self, name: str) -> bool:
        """카테고리 삭제. 없으면 False, 삭제했으면 True.

        사용 중인 카테고리인지 확인하는 정책은 서비스 계층에서.
        """
        names = self.list_names()
        if name not in names:
            return False
        rewrite_jsonl(self.path, ({"name": n} for n in names if n != name))
        return True
        
# ===========================================================================
# 3. BudgetStore — budgets.jsonl
# ===========================================================================
# 파일 한 줄 예시: {"month": "2024-01", "amount": 500000}

class BudgetStore:
    """월별 예산을 저장/조회하는 클래스."""
    def __init__(self, path: Path) -> None:
        self.path = path
        # touch: 파일이 없으면 빈 파일을 만듦.
        self.path.touch(exist_ok=True)
    
    def iter_all(self) -> Iterator[Budget]:
        for record in iter_jsonl(self.path):
            try:
                yield Budget.from_dict(record)
            except ValidationError as error:
                logger.warning("잘못된 예산 데이터를 건너뜁니다: %s (%s)", record, error.message)
    
    def get(self, month: str) -> Budget | None:
        """해당 월의 예산, 없으면 None."""
        for budget in self. iter_all():
            if budget.month == month:
                return budget
        return None
    
    def set(self, budget: Budget) -> None:
        """예산 저장. 같은 월이 있으면 새 금액으로 덮어씀.
        
        저장/덮어쓰기 시 sorted를 사용하지 않음. 마지막에 수정/추가 된 것이 파일의 맨 밑으로."""

        # 기존 예산 중 같은 월은 빼고, 마지막에 새 예산을 추가한 결과를 만듦.
        def updated_records() -> Iterator[dict[str, Any]]:
            for old in self.iter_all():
                if old.month != budget.month:
                    yield old.to_dict()
            yield budget.to_dict()
        
        rewrite_jsonl(self.path, updated_records())
                












