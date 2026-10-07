"""
repository.py — 저장소(Repository) 계층: 파일 입출력 전담
==========================================================

[이 파일의 역할]
"데이터를 파일에 어떻게 저장하고, 어떻게 읽어오는가"만 담당합니다.
서비스(services.py)는 "거래를 하나 추가해줘", "전부 하나씩 줘"라고 요청만 하고,
그게 JSONL인지 CSV인지 DB인지는 신경 쓰지 않습니다.

[JSONL이란?]
JSON Lines. "한 줄 = JSON 객체 하나"인 텍스트 파일입니다.

    {"id": "TX-000001", "type": "expense", "date": "2024-01-15", ...}
    {"id": "TX-000002", "type": "income",  "date": "2024-01-16", ...}

일반 JSON 파일(전체가 하나의 [ ... ] 배열)은 읽으려면 파일 '전체'를 한 번에
메모리에 올려야 하지만, JSONL은 '한 줄씩' 읽고 처리하고 버릴 수 있습니다.
→ 그래서 제너레이터(yield)를 이용한 스트리밍 처리와 궁합이 아주 좋습니다.

[이 파일에 있는 것]
1. 공통 JSONL 유틸 함수: iter_jsonl / append_jsonl / rewrite_jsonl
2. CategoryStore         : categories.jsonl 관리
3. BudgetStore           : budgets.jsonl 관리
4. TransactionRepository : transactions.jsonl 관리
"""

import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from .errors import NotFoundError, ValidationError
from .models import Budget, Transaction

# 로거(logger): print 대신 "기록"을 남기는 도구. 설정은 cli.py의 setup_logging에서 합니다.
# 같은 이름("budget_app")으로 가져오면 어느 파일에서든 같은 로거를 공유합니다.
logger = logging.getLogger("budget_app")

# 카테고리 파일이 비어 있을 때 자동으로 만들어 줄 기본 카테고리 (설계 결정: 안 A)
DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "salary", "etc")

# 거래 id 접두사. "TX-" + 6자리 숫자 → TX-000001
ID_PREFIX = "TX-"


# ===========================================================================
# 1. 공통 JSONL 유틸 함수
# ===========================================================================


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """JSONL 파일을 '한 줄씩' 읽어서 dict를 하나씩 돌려주는 제너레이터.

    [제너레이터(generator)란?]
    함수 안에 `yield`가 있으면 그 함수는 '제너레이터 함수'가 됩니다.
    - return : 값을 돌려주고 함수가 '완전히 끝남'
    - yield  : 값을 하나 돌려주고 함수가 '잠시 멈춤' → 다음 값을 요청하면 멈춘 곳부터 이어서 실행

        for record in iter_jsonl(path):   # 한 바퀴 돌 때마다 파일에서 한 줄만 읽음
            print(record)

    파일에 거래가 100만 건 있어도 메모리에는 '지금 처리 중인 한 줄'만 올라갑니다.
    리스트로 전부 읽어오는 방식(f.readlines())과의 가장 큰 차이입니다.

    [반환 타입 Iterator[dict[str, Any]]]
    "dict를 하나씩 꺼내 줄 수 있는 것"이라는 뜻입니다.
    """
    if not path.exists():
        # 파일이 없으면 아무것도 yield하지 않고 끝 → for문이 0번 돈다.
        return

    # with문: 블록이 끝나면(에러가 나더라도) 파일을 자동으로 닫아줍니다.
    # encoding="utf-8": 한글이 깨지지 않도록 항상 명시합니다. (OS마다 기본값이 다름)
    with path.open("r", encoding="utf-8") as file:
        # 파일 객체를 for문으로 돌리면 '한 줄씩' 읽습니다. (이것 자체가 스트리밍)
        # enumerate(..., start=1): 몇 번째 줄인지 번호도 함께 받기 (로그용)
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue  # 빈 줄은 건너뜀

            try:
                record = json.loads(line)  # 문자열 → dict
            except json.JSONDecodeError:
                # 깨진 줄 처리 정책: 프로그램을 멈추지 않고 '경고 로그만 남기고 건너뛴다'.
                # (사용자가 파일을 직접 편집하다 실수했을 수도 있으므로)
                logger.warning("%s %d번째 줄이 올바른 JSON이 아니라서 건너뜁니다.", path.name, line_no)
                continue

            if isinstance(record, dict):
                yield record  # ← 여기서 잠시 멈추고 record를 바깥 for문에 넘겨줌


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """JSONL 파일 끝에 한 줄을 추가합니다. (기존 내용은 건드리지 않음)"""
    # "a" 모드 = append(이어쓰기). 파일이 없으면 새로 만듭니다.
    with path.open("a", encoding="utf-8") as file:
        # ensure_ascii=False: 한글을 "\uc810\uc2ec" 대신 "점심" 그대로 저장
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """파일 전체를 새 내용으로 '안전하게' 교체합니다. (원자적 교체, atomic replace)

    [왜 그냥 "w" 모드로 덮어쓰면 안 되나요?]
    open(path, "w")는 여는 순간 기존 내용을 '싹 지웁니다'.
    그 상태에서 쓰는 도중 프로그램이 죽거나 정전이 나면 → 데이터가 전부 날아갑니다.

    [안전한 방법: 임시 파일 + os.replace]
    1. 같은 폴더에 임시 파일(.transactions.jsonl.xxxx.tmp)을 만들고 거기에 새 내용을 다 씁니다.
    2. 다 쓰고 나면 os.replace(임시파일, 원본)으로 '이름을 바꿔치기' 합니다.
       os.replace는 운영체제 수준에서 '한 번에' 일어나는 동작(원자적)이라,
       중간 상태(반쯤 쓴 파일)가 원본 자리에 존재하는 순간이 없습니다.
    → 실패하더라도 원본은 멀쩡하거나, 새 파일로 완전히 바뀌었거나 둘 중 하나입니다.

    [보너스 포인트]
    records 인자에 '같은 파일을 읽는 제너레이터'를 넘겨도 안전합니다.
    원본을 읽으면서 → 임시 파일에 쓰고 → 다 끝난 뒤에 교체하기 때문입니다.
    덕분에 update/delete도 파일 전체를 메모리에 올리지 않고 스트리밍으로 처리됩니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # mkstemp: 이름이 겹치지 않는 임시 파일을 '같은 폴더(dir=...)'에 만듭니다.
    # 같은 폴더여야 하는 이유: os.replace는 같은 디스크(파일시스템) 안에서만 원자적이기 때문.
    # 반환값 fd는 '파일 번호(file descriptor)', tmp_name은 임시 파일 경로입니다.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()             # 파이썬 내부 버퍼 → 운영체제로 보내기
            os.fsync(file.fileno())  # 운영체제 버퍼 → 실제 디스크에 기록 보장
        os.replace(tmp_name, path)   # 바꿔치기! (원자적)
    except BaseException:
        # 어떤 이유로든 실패하면(Ctrl+C 포함) 임시 파일을 지우고, 예외는 다시 위로 던집니다.
        # 원본 파일은 전혀 건드리지 않았으므로 안전합니다.
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
        """카테고리 파일이 없거나 비어 있으면 기본 카테고리를 만들어 둡니다.

        메서드 이름 앞의 밑줄(_)은 "클래스 내부에서만 쓰는 메서드"라는 관례적 표시입니다.
        (파이썬이 막지는 않지만, 바깥에서 부르지 말라는 약속)
        """
        # any(...)는 하나라도 True면 즉시 멈춥니다. → 첫 줄만 읽어보고 판단 (효율적)
        has_any = any(True for _ in iter_jsonl(self.path))
        if not has_any:
            # 괄호 안의 (... for ... in ...)는 '제너레이터 표현식'입니다.
            # 리스트 [ ]와 달리 값을 미리 다 만들어 두지 않고 하나씩 만들어 넘깁니다.
            rewrite_jsonl(self.path, ({"name": name} for name in DEFAULT_CATEGORIES))
            logger.info("기본 카테고리를 생성했습니다: %s", ", ".join(DEFAULT_CATEGORIES))

    def list_names(self) -> list[str]:
        """등록된 카테고리 이름 목록. (카테고리는 개수가 적으므로 리스트로 돌려줘도 괜찮습니다)

        참고: 메서드 이름을 `list`로 지으면 클래스 안에서 내장 함수 list와 이름이 겹쳐
        `-> list[str]` 같은 타입 힌트가 꼬일 수 있어서 list_names로 지었습니다.
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

        (사용 중인 카테고리인지 확인하는 '정책'은 서비스 계층의 몫입니다.
         저장소는 시키는 대로 지우기만 합니다.)
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
        # touch: 파일이 없으면 빈 파일을 만듭니다. (요구사항: 저장 파일 3개 이상)
        self.path.touch(exist_ok=True)

    def iter_all(self) -> Iterator[Budget]:
        for record in iter_jsonl(self.path):
            try:
                yield Budget.from_dict(record)
            except ValidationError as error:
                logger.warning("잘못된 예산 데이터를 건너뜁니다: %s (%s)", record, error.message)

    def get(self, month: str) -> Budget | None:
        """해당 월의 예산. 없으면 None."""
        for budget in self.iter_all():
            if budget.month == month:
                return budget  # 찾으면 바로 반환 → 나머지 줄은 읽지 않음
        return None

    def set(self, budget: Budget) -> None:
        """예산 저장. 같은 월이 이미 있으면 새 금액으로 '덮어씁니다'."""

        # 함수 안에 함수를 정의할 수도 있습니다. (중첩 함수)
        # 이 제너레이터는 "기존 예산 중 같은 월은 빼고, 마지막에 새 예산을 추가"한 결과를 만듭니다.
        def updated_records() -> Iterator[dict[str, Any]]:
            for old in self.iter_all():
                if old.month != budget.month:
                    yield old.to_dict()
            yield budget.to_dict()

        rewrite_jsonl(self.path, updated_records())


# ===========================================================================
# 4. TransactionRepository — transactions.jsonl
# ===========================================================================


def format_tx_id(number: int) -> str:
    """12 → 'TX-000012'.  :06d 는 '6자리 정수, 빈자리는 0으로 채움'이라는 서식입니다."""
    return f"{ID_PREFIX}{number:06d}"


class TransactionRepository:
    """거래 내역을 파일에 저장/조회/수정/삭제하는 클래스."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.touch(exist_ok=True)

    # ----- 읽기 ---------------------------------------------------------

    def iter_all(self) -> Iterator[Transaction]:
        """모든 거래를 파일에 '저장된 순서대로' 하나씩 돌려줍니다. (스트리밍)

        list/search/summary/export 등 '읽기' 기능은 전부 이 메서드에서 출발합니다.
        """
        for record in iter_jsonl(self.path):
            try:
                yield Transaction.from_dict(record)
            except ValidationError as error:
                # 검증에 실패한 줄(누군가 파일을 잘못 고친 경우 등)은 경고 후 건너뜀
                logger.warning("잘못된 거래 데이터를 건너뜁니다: %s (%s)", record, error.message)

    def next_number(self) -> int:
        """다음에 쓸 id 번호. (지금까지 나온 가장 큰 번호 + 1)

        '마지막 줄의 번호 + 1'이 아니라 '최댓값 + 1'을 쓰는 이유:
        import나 수동 편집으로 줄 순서가 섞여 있어도 id가 겹치지 않게 하려고.
        파일 전체를 훑지만, 한 줄씩 읽으므로 메모리는 거의 쓰지 않습니다.
        """
        max_number = 0
        for record in iter_jsonl(self.path):
            tx_id = str(record.get("id", ""))
            # "TX-000012" → 접두사 떼고 "000012" → 숫자인지 확인 → 12
            number_part = tx_id.removeprefix(ID_PREFIX)
            if tx_id.startswith(ID_PREFIX) and number_part.isdigit():
                max_number = max(max_number, int(number_part))
        return max_number + 1

    def next_id(self) -> str:
        return format_tx_id(self.next_number())

    # ----- 추가 ---------------------------------------------------------

    def add(self, tx: Transaction) -> None:
        append_jsonl(self.path, tx.to_dict())

    def add_many(self, txs: Iterable[Transaction]) -> int:
        """여러 건을 한 번에 추가 (import용). 파일을 한 번만 열어서 효율적입니다.

        txs에 제너레이터를 넘기면, CSV를 한 줄 읽을 때마다 바로 한 줄씩 기록됩니다.
        """
        count = 0
        with self.path.open("a", encoding="utf-8") as file:
            for tx in txs:
                file.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")
                count += 1
        return count

    # ----- 수정/삭제 (전체 재작성 + 원자적 교체) ---------------------------

    def _rewrite(self, transform: Callable[[dict[str, Any]], dict[str, Any] | None]) -> int:
        """모든 줄에 transform 함수를 적용해서 파일을 다시 씁니다.

        transform(record)의 반환값 규칙:
          - 같은 dict를 그대로 반환 → 변경 없음
          - 다른 dict를 반환       → 그 내용으로 바뀜 (수정)
          - None을 반환            → 그 줄은 빠짐 (삭제)

        반환값: 바뀌거나 삭제된 줄의 개수

        [함수를 인자로 받는다?]
        파이썬에서 함수도 '값'이라서 변수에 담거나 다른 함수에 넘길 수 있습니다.
        Callable[[dict], dict | None] 은 "dict를 받아서 dict 또는 None을 돌려주는 함수"라는 타입입니다.
        update/delete/카테고리 일괄 변경이 모두 '전체 재작성'이라는 같은 뼈대를 쓰므로,
        달라지는 부분(어떻게 바꿀지)만 함수로 받아 중복을 없앴습니다.
        """
        changed = 0  # 바깥 함수의 변수

        def generate() -> Iterator[dict[str, Any]]:
            # nonlocal: 안쪽 함수에서 바깥 함수의 변수 'changed'를 수정하겠다는 선언
            nonlocal changed
            for record in iter_jsonl(self.path):
                new_record = transform(record)
                if new_record is not record:
                    changed += 1
                if new_record is not None:
                    yield new_record

        rewrite_jsonl(self.path, generate())
        return changed

    def update(self, tx_id: str, changes: dict[str, Any]) -> Transaction:
        """id가 tx_id인 거래의 일부 필드를 changes 내용으로 바꿉니다.

        예) update("TX-000001", {"amount": 20000, "memo": "저녁"})
        """
        updated: list[Transaction] = []  # 안쪽 함수에서 결과를 담기 위한 그릇

        def transform(record: dict[str, Any]) -> dict[str, Any]:
            if record.get("id") != tx_id:
                return record  # 대상이 아니면 그대로
            # dataclasses.replace(객체, 필드=새값, ...):
            #   원본은 그대로 두고 일부 필드만 바꾼 '새 객체'를 만듭니다.
            #   이때 __post_init__이 다시 실행되어 새 값도 자동으로 검증됩니다!
            new_tx = replace(Transaction.from_dict(record), **changes)
            updated.append(new_tx)
            return new_tx.to_dict()

        self._rewrite(transform)
        if not updated:
            raise NotFoundError(
                f"id '{tx_id}'에 해당하는 거래가 없습니다.",
                "list 또는 search 명령으로 id를 확인하세요.",
            )
        return updated[0]

    def delete(self, tx_id: str) -> None:
        """id가 tx_id인 거래를 삭제합니다. 없으면 NotFoundError."""
        # lambda: 이름 없는 한 줄짜리 함수.
        #   lambda r: (None if 조건 else r)  ==  def f(r): return None if 조건 else r
        removed = self._rewrite(lambda r: None if r.get("id") == tx_id else r)
        if removed == 0:
            raise NotFoundError(
                f"id '{tx_id}'에 해당하는 거래가 없습니다.",
                "list 또는 search 명령으로 id를 확인하세요.",
            )

    def replace_category(self, old: str, new: str) -> int:
        """카테고리 old를 쓰는 모든 거래를 new로 바꿉니다. 바뀐 건수를 반환."""

        def transform(record: dict[str, Any]) -> dict[str, Any]:
            if record.get("category") == old:
                # {**record, "category": new}: record를 복사하면서 category만 바꾼 새 dict
                return {**record, "category": new}
            return record

        return self._rewrite(transform)

    def count_by_category(self, name: str) -> int:
        """카테고리 name을 쓰는 거래 건수. sum(1 for ...)은 조건에 맞는 개수를 세는 관용구입니다."""
        return sum(1 for tx in self.iter_all() if tx.category == name)
