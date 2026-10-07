# 용돈 기입장(budget_app) 직접 구현 계획

## 확정된 설계 결정

| 항목 | 결정 |
| --- | --- |
| 저장 포맷 | **JSONL** (`transactions.jsonl`, `categories.jsonl`, `budgets.jsonl`) |
| update 방식 | **옵션 기반** `update --id <id> [--date] [--type] [--category] [--amount] [--memo] [--tags]` |
| 빈 카테고리 | **안 A** 기본 카테고리 자동 생성 (food, transport, rent, salary, etc) |
| 실행 방식 | `python -m budget_app <command> [options]` (전역 옵션 `--data-dir`, `--verbose`는 명령 **앞에**) |
| 라이브러리 | 표준 라이브러리만 (`argparse`, `json`, `csv`, `dataclasses`, `datetime`, `pathlib`, `os`, `tempfile`, `heapq`, `functools`, `time`, `logging`) |
| Python 버전 | **3.10 이상 필수**. 이 Mac의 `python3`는 3.9라서 `python3.12` 사용 (`ParamSpec`, `X \| Y` 문법 때문) |
| 카테고리 삭제 | 사용 중이면 **삭제 차단**, `--replace <대체>`를 주면 거래를 옮긴 뒤 삭제 |
| 최신순 기준 | `(date, id)` 내림차순. 날짜가 같으면 나중에 추가된(id가 큰) 거래가 위로 |
| import 오류 행 | 해당 줄만 skip, 줄 번호와 사유 출력 |
| 깨진 저장 데이터 | 경고 로그만 남기고 건너뜀 (프로그램은 멈추지 않음) |
| 로그 | `data/app.log`에 기록, `--verbose`면 화면에도 출력 |
| 종료 코드 | 정상 0 / 앱 오류 1 / argparse 옵션 오류 2 / Ctrl+C 130 |

## 목표 폴더 구조

```text
Codyssey-B2-1/
├── budget_app/
│   ├── __init__.py
│   ├── __main__.py      # 진입점: main() 호출 + sys.exit(code)
│   ├── models.py        # Transaction, Budget 데이터클래스 + 검증 함수
│   ├── errors.py        # 사용자 정의 예외 (message + hint)
│   ├── decorators.py    # 예외 처리 / 로그 / 시간 측정
│   ├── repository.py    # 파일 I/O (JSONL 읽기/쓰기, 스트리밍)
│   ├── services.py      # 비즈니스 로직 (검색, 요약, 예산, import/export)
│   └── cli.py           # argparse 정의 + 대화형 입력 + 출력
├── data/                # 실행 시 자동 생성 (.gitignore 권장)
└── README.md
```

> 계층 의존 방향: `cli → services → repository → models` (역방향 import 금지)

## 📎 참고 구현 (`example/`)

[example/](../example/README.md)에 이 계획대로 만든 참고 코드가 있습니다. 모든 줄에 초보자용 주석을 달아 두었습니다.

```bash
python3.12 -m example --help
python3.12 -m example --data-dir /tmp/demo category list
```

> [!TIP]
> **먼저 직접 짜고, 막히거나 다 짠 뒤에 비교하세요.** 각 Step의 `📎 참고`에 볼 위치를 적어 두었습니다.

| Step | 참고 파일 | 주요 심볼 |
| --- | --- | --- |
| 0 | `__main__.py`, `cli.py` | `main`, `build_parser`, `dispatch` |
| 1 | `errors.py`, `models.py` | `AppError`, `parse_*`, `Transaction.__post_init__` |
| 2 | `repository.py` | `iter_jsonl`, `rewrite_jsonl`, `TransactionRepository._rewrite` |
| 3 | `decorators.py` | `handle_errors`, `log_execution`, `timed` |
| 4 | `services.py`, `cli.py` | `BudgetService.latest`, `ask`, `cmd_add`, `cmd_list` |
| 5 | `services.py` | `BudgetService.search` |
| 6 | `services.py`, `models.py` | `summarize`, `MonthlySummary` |
| 7 | `services.py`, `cli.py` | `remove_category`, `update_transaction`, `cmd_update` |
| 8 | `services.py` | `export_csv`, `import_csv` |

---

# Part 1. 기본 코드 구축

## Step 0. 프로젝트 뼈대 만들기

**목표:** `python -m budget_app --help`가 실행되는 상태

- [ ] `budget_app/` 패키지와 빈 모듈 파일 생성
- [ ] `__main__.py`에서 `cli.main()`을 호출하고 반환값으로 `sys.exit()`
- [ ] `cli.py`에 `argparse.ArgumentParser` + `add_subparsers(dest="command")` 기본 틀
- [ ] 전역 옵션 `--data-dir` (기본값 `./data`) 추가

💡 **핵심 개념**
- `python -m 패키지명`은 패키지 안의 `__main__.py`를 실행한다.
- argparse는 서브커맨드마다 `--help`를 자동 생성해준다 → 요구사항 "모든 명령 `--help`"를 공짜로 충족.
- `add_subparsers(..., required=True)`로 명령 없이 실행하는 것을 막고, `set_defaults(handler=cmd_xxx)`를 쓰면 if/elif 없이 `args.handler(...)`로 실행할 수 있다.

> [!WARNING]
> **`__main__.py`에서 자주 하는 실수 두 가지**
> 1. `from cli import main` ❌ → `from .cli import main` ✅ (`python -m`으로 실행하면 패키지 안에서는 상대 import를 써야 함)
> 2. `main()`만 호출 ❌ → `sys.exit(main())` ✅ (이렇게 해야 오류 종료 코드가 운영체제에 전달됨)

```python
def main(argv: list[str] | None = None) -> int: ...
```

📎 **참고:** `example/__main__.py`, `example/cli.py`의 `build_parser`, `main`

---

## Step 1. 모델 계층 (`models.py`, `errors.py`)

**목표:** 데이터 구조와 검증 규칙을 한 곳에 정의

- [ ] `Transaction` dataclass: `id, type, date, amount, category, memo="", tags=list`
- [ ] `Budget` dataclass: `month, amount`
- [ ] `to_dict()` / `from_dict()` 메서드 (JSON 직렬화용)
- [ ] 검증 함수: 날짜(YYYY-MM-DD), 월(YYYY-MM), 타입(income/expense), 금액(양의 정수), 태그 파싱("a,b" → `["a","b"]`)
- [ ] `errors.py`에 `AppError(message, hint)` 기본 예외 + 필요 시 하위 클래스 (`ValidationError`, `NotFoundError`)

💡 **핵심 개념**
- 날짜 검증은 정규식보다 `datetime.strptime(s, "%Y-%m-%d")`가 정확하다 (`2024-13-40` 같은 값도 걸러냄).
- 리스트 기본값은 `field(default_factory=list)` 사용 (가변 기본값 함정 주의).
- `Literal["income", "expense"]` 타입 힌트로 허용 값을 명시할 수 있다.
- `__post_init__`에서 검증하면 잘못된 `Transaction`은 아예 만들어지지 않는다. `dataclasses.replace()`로 수정할 때도 검증이 다시 실행되므로 update 검증이 저절로 해결된다.
- `parse_date`는 `strftime`으로 다시 문자열로 만들어 `2024-1-5` → `2024-01-05`로 통일한다. 그래야 Step 5에서 문자열 비교가 날짜 비교가 된다.
- `parse_amount`에서 `bool`부터 거르기 (`True`도 `int`라서 1원으로 통과함).
- 서비스 결과용 dataclass(`MonthlySummary`, `ImportResult`)도 여기에 두면 편하다.

```python
@dataclass
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

def parse_date(value: str) -> str: ...
def parse_amount(value: str) -> int: ...
```

✅ **확인:** 파이썬 REPL에서 객체 생성 → `to_dict()` → `from_dict()` 왕복이 되는지

📎 **참고:** `example/errors.py`, `example/models.py`

---

## Step 2. 저장소 계층 (`repository.py`)

**목표:** 파일 I/O를 전담하는 클래스 3개 (요구사항 "2개 이상 클래스" 충족)

### 2-1. 공통 JSONL 유틸
- [ ] `data_dir` 없으면 `mkdir(parents=True, exist_ok=True)`
- [ ] 한 줄씩 `yield`하는 읽기 함수 (빈 줄 무시, 깨진 줄 처리 정책 결정)
- [ ] 한 줄 추가(append) 함수
- [ ] 전체 재작성 함수: **임시 파일에 쓰고 `os.replace()`로 교체** (원자적 교체)

### 2-2. `CategoryStore`
- [ ] 파일이 없거나 비면 기본 카테고리 생성 (안 A)
- [ ] `list_names() / exists() / add() / remove()`
  - ⚠️ 메서드 이름을 `list`로 지으면 클래스 안에서 `-> list[str]` 타입 힌트가 그 메서드를 가리키게 되어 꼬인다.

### 2-3. `BudgetStore`
- [ ] `set(month, amount)` (같은 월이면 덮어쓰기) / `get(month)`

### 2-4. `TransactionRepository`
- [ ] `iter_all()` → `Iterator[Transaction]` (제너레이터)
- [ ] `add(tx)` → append
- [ ] `next_id()` → `TX-000001` 형식 (**최댓값** + 1, 6자리 0 채움 → 문자열 정렬 순서 = 숫자 순서)
- [ ] `add_many(txs)` → import용, 파일을 한 번만 열기
- [ ] `update(id, changes)` / `delete(id)` / `replace_category(old, new)` → 스트리밍으로 읽으며 임시 파일에 쓰고 교체, 대상 없으면 `NotFoundError`
  - 세 메서드 모두 "한 줄씩 변환해서 다시 쓰기"라서 `_rewrite(transform)` 헬퍼 하나로 묶을 수 있다.

💡 **핵심 개념**
- `with open(...) as f: for line in f: yield ...` → 파일 전체를 메모리에 올리지 않는다.
- `os.replace(tmp, target)`는 같은 파일시스템에서 원자적이다 → 쓰다가 죽어도 원본이 깨지지 않음.
- 인코딩은 항상 `encoding="utf-8"` 명시, JSON은 `ensure_ascii=False`로 한글 유지.

```python
def iter_all(self) -> Iterator[Transaction]: ...
def delete(self, tx_id: str) -> None: ...
```

- `rewrite_jsonl(path, 같은_파일을_읽는_제너레이터)`도 안전하다. 원본을 읽으면서 임시 파일에 쓰고, 다 끝난 뒤에 교체하기 때문.

✅ **확인:** 직접 `data/transactions.jsonl`을 열어 한 줄 = 한 거래인지 눈으로 확인

📎 **참고:** `example/repository.py`

---

## Step 3. 데코레이터 (`decorators.py`)

**목표:** 공통 관심사를 비즈니스 로직에서 분리

- [ ] `@handle_errors`: `AppError` → `[오류] ... / [힌트] ...` 출력 후 종료 코드 1 반환, 예상치 못한 예외도 스택트레이스 없이 처리, `KeyboardInterrupt` 처리
- [ ] `@log_execution`: 명령 실행 기록 (`logging`으로 파일 또는 stderr)
- [ ] `@timed`: `time.perf_counter()`로 실행 시간 측정 (디버그 모드에서만 출력 등)

💡 **핵심 개념**
- `functools.wraps`를 꼭 써야 원래 함수의 이름/docstring이 유지된다.
- 타입 힌트: `Callable[..., int]` 또는 `ParamSpec`/`TypeVar`로 래퍼 시그니처 보존.
- `except` 순서: `AppError` → `KeyboardInterrupt` → `EOFError` → `OSError` → `Exception` (구체적인 것부터).
- 오류 메시지는 `print(..., file=sys.stderr)`로 정상 출력과 분리한다.
- `@handle_errors`는 **`dispatch()` 한 곳**에 붙이면 로깅 설정, 서비스 생성, 명령 실행 중 어디서 난 예외든 모두 잡힌다. `@log_execution`/`@timed`는 명령 함수마다 붙여서 로그에 함수 이름이 남게 한다.
- 스택트레이스는 `logger.debug(..., exc_info=True)`로 **로그 파일에만** 남긴다.

```python
def handle_errors(func: Callable[P, int]) -> Callable[P, int]: ...
```

📎 **참고:** `example/decorators.py`, `example/cli.py`의 `setup_logging`, `dispatch`

---

## Step 4. 첫 번째 수직 슬라이스: `category` + `add` + `list`

**목표:** 끝에서 끝까지(CLI→서비스→저장소) 한 번 관통하기

- [ ] `services.py`에 서비스 클래스(예: `BudgetService`) 생성, 저장소 3개를 주입받기
- [ ] `category add / list / remove` CLI 연결 (remove는 Step 7에서 보강)
- [ ] `add`: `input()`으로 순차 입력, **잘못된 값이면 해당 필드만 재입력** 루프
  - 카테고리가 없으면 목록 안내 후 재입력
  - 저장 후 `[저장 완료] id=TX-000012`
- [ ] `list --limit N` (기본값 예: 20): 최신순 출력

💡 **핵심 개념: "스트리밍 + 최신순"**
- 파일은 추가 순서(오래된 순)로 쌓이는데, 최신순 출력이 필요하다.
- 전체를 정렬하면 스트리밍이 깨지므로, `heapq.nlargest(limit, iterable, key=...)` 또는 `collections.deque(maxlen=limit)`를 사용하면 **메모리에 N개만** 유지하면서 처리할 수 있다.
- 정렬 기준(date, id)을 미리 정하고 README에 명시할 것.
- `ask(prompt, parse)` 헬퍼: 올바른 값이 들어올 때까지 `while True`로 반복한다. `parse`에 `service.validate_category`를 넘기면 카테고리 재입력도 같은 함수로 처리된다.
- argparse `type=`에 검증 함수를 쓰려면 `ValidationError`를 `argparse.ArgumentTypeError`로 바꿔 주는 어댑터(`argtype`)가 필요하다 → 옵션 방식과 대화형 방식이 같은 검증 규칙을 쓴다.

✅ **확인:** 실행 예시 화면(미션 문서 8번)과 비교

📎 **참고:** `example/services.py`의 `BudgetService.latest`, `example/cli.py`의 `ask`, `argtype`, `cmd_add`, `cmd_list`

---

## Step 5. `search`

- [ ] 옵션: `--from --to --category --type --q --tag --limit`
- [ ] 필터를 **제너레이터 체인**으로 구성 (`iter_all()` → 조건 필터 → 최신순 상위 N)
- [ ] 날짜 옵션도 Step 1의 검증 함수 재사용
- [ ] 결과 0건이면 "검색 결과 없음"

💡 날짜가 `YYYY-MM-DD` 문자열이면 문자열 비교로도 범위 비교가 된다.

💡 `--from`은 파이썬 예약어라 `args.from`으로 못 쓴다 → `dest="date_from"` 지정.

💡 `--from`이 `--to`보다 늦으면 오류로 처리한다.

```python
def search(self, *, date_from: str | None, date_to: str | None, ...) -> Iterator[Transaction]: ...
```

📎 **참고:** `example/services.py`의 `search`, `example/cli.py`의 `cmd_search`

---

## Step 6. `budget` + `summary`

- [ ] `budget set --month --amount`, (선택) `budget get --month`
- [ ] `summary --month YYYY-MM --top N`
  - 스트리밍하며 총수입/총지출 누적, 카테고리별 지출은 `dict`/`Counter`로 집계
  - 잔액 = 수입 − 지출
  - 데이터 없으면 "데이터 없음"
  - 예산 있으면 사용률(%) 출력, 초과 시 경고
- [ ] 집계 결과는 dataclass(예: `MonthlySummary`)로 반환 → CLI는 출력만 담당

💡 서비스는 **값을 반환**, CLI는 **출력**만. 이렇게 나누면 나중에 테스트가 쉬워진다.

💡 `summary`는 `search(month=...)`를 재사용하면 필터 코드를 다시 짤 필요가 없다.

📎 **참고:** `example/services.py`의 `summarize`, `example/models.py`의 `MonthlySummary`, `example/cli.py`의 `print_summary`

---

## Step 7. `update` / `delete` / `category remove` 보강

- [ ] `delete --id <id>`: 없으면 "해당 id 없음" + 종료 코드 ≠ 0
- [ ] `update --id <id> [--date ...]...`: 전달된 옵션만 변경, 각 값 검증, 카테고리 존재 확인, 아무 옵션도 없으면 안내
  - ⚠️ `if args.memo:`가 아니라 `if args.memo is not None:`으로 검사해야 `--memo ""`(메모 지우기)가 동작한다.
- [ ] `category remove <name> [--replace <대체>]`: 사용 중이면 **삭제 차단**, `--replace`를 주면 거래를 먼저 옮긴 뒤 카테고리 삭제
  - 순서가 중요하다: 거래 이동 → 카테고리 삭제. 반대로 하면 중간에 실패했을 때 없는 카테고리를 쓰는 거래가 남는다.

📎 **참고:** `example/services.py`의 `remove_category`, `update_transaction`, `example/cli.py`의 `cmd_update`

---

## Step 8. `import` / `export`

- [ ] `export --out <csv> (--month | --from/--to)`: 조건 없으면 오류, `csv.DictWriter`로 헤더 포함 UTF-8 저장, `[완료] export.csv (N records)`
- [ ] `import --from <csv>`: `csv.DictReader`로 한 줄씩 검증 → 정상은 추가, 오류 행은 skip(행 번호와 사유 출력), `[완료] imported=N, skipped=M`
- [ ] tags는 CSV에서 쉼표 문자열 ↔ 내부 리스트 변환
- [ ] 파일 없음 / 헤더 누락 시 원인 + 힌트

💡 CSV에 쉼표가 들어간 tags 필드는 `csv` 모듈이 자동으로 따옴표 처리한다 (직접 split 하지 말 것). `open(..., newline="")` 필수.

💡 import는 `encoding="utf-8-sig"`로 읽으면 엑셀이 붙이는 BOM도 처리된다. 줄 번호는 헤더가 1번이므로 `enumerate(reader, start=2)`.

📎 **참고:** `example/services.py`의 `export_csv`, `import_csv`

---

## Step 9. 마무리: 예외/종료 코드 점검 + README

- [ ] 모든 명령이 `@handle_errors`가 붙은 `dispatch()`를 거치는지 확인, 정상 0 / 오류 ≠ 0 (`echo $?`로 확인)
- [ ] 대화형 입력 중 Ctrl+C / Ctrl+D를 눌러도 스택트레이스가 안 나오는지 확인
- [ ] 모든 서브커맨드 `--help` 확인
- [ ] 모든 옵션이 `--` 표기인지 확인
- [ ] `README.md` 작성
  - 실행 방법 (Python 3.10+)
  - 저장 파일 위치/형식 (JSONL 한 줄 예시)
  - 주요 명령 예시
  - import/export CSV 스키마
  - 설계 결정 (update 옵션 방식, 기본 카테고리, 카테고리 삭제 정책, 최신순 기준)

### 최종 수동 테스트 시나리오
1. `data/` 삭제 후 `category list` → 기본 카테고리 생성 확인
2. `add` 3~5건 (잘못된 날짜/금액/카테고리 입력 섞어서)
3. `list --limit 3`, `search --category food`, `search --q 점심`
4. `budget set` → `summary` (초과/미초과 둘 다)
5. `update` / `delete` (없는 id 포함)
6. `category remove food` (사용 중)
7. `export` → 생성된 CSV를 `import` → 건수 확인

---

# Part 2. 기본 구축 이후 추가 작업

## A. Git 커밋 / 브랜치 전략

> Part 1을 진행하면서 이미 커밋은 하되, 아래 규칙을 정리해 적용합니다.

- **브랜치:** `main`(제출용) ← `feature/<기능>` (예: `feature/repository`, `feature/summary`)
- **커밋 단위:** Step 하나 = 1개 이상 커밋, "동작하는 상태"에서만 커밋
- **메시지 규칙 예시:** `feat: add 명령 대화형 입력 구현`, `fix: ...`, `refactor: ...`, `docs: README CSV 스키마 추가`, `test: ...`
- [ ] `.gitignore`: `data/`, `__pycache__/`, `*.pyc`, `*.log`, 내보낸 CSV
- [ ] 기능 단위로 PR(또는 `git merge --no-ff`)해 히스토리를 남기기
- [ ] 완료 시 `git tag v1.0`

## B. 테스트 (`unittest`)

```text
tests/
├── test_models.py       # 검증 함수 (날짜/금액/타입/태그)
├── test_repository.py   # tempfile.TemporaryDirectory 사용, add/iter/update/delete
├── test_services.py     # search 필터, summary 집계, 예산 사용률
└── test_cli.py          # main([...]) 호출 → 종료 코드 확인, input은 unittest.mock.patch
```

- [ ] 실행: `python -m unittest discover tests`
- [ ] 우선순위: models → repository → services → cli
- 💡 서비스가 값을 반환하도록 설계했다면(Step 6) 테스트가 쉽다.

## C. 보너스 과제 (권장 순서)

| 순서 | 과제 | 메모 |
| --- | --- | --- |
| 1 | 저장 원자성 강화 | Step 2에서 이미 `os.replace` 적용 시 거의 완료 → README에 설명만 추가 |
| 2 | 출력 테이블 정렬 | `formatters.py` 분리, `str.ljust/rjust`, 한글 폭은 `unicodedata.east_asian_width` |
| 3 | 백업 기능 | `backup` 명령, `data/backup/20261007-132700/`에 `shutil.copy2` |
| 4 | 반복 내역 | `recurring.jsonl` 추가, `recurring add/list`, `recurring apply --month` (중복 생성 방지 필요) |
