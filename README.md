# Codyssey-B2-1
나만의 용돈 기입장 프로그램 만들기

파일(JSONL) 기반으로 데이터를 영구 저장하는 **콘솔 가계부**입니다.
거래 추가/조회/검색/수정/삭제, 월별 요약, 예산 경고, 카테고리 관리, CSV 가져오기/내보내기를 지원합니다.
표준 라이브러리만 사용합니다.

---

## 목차

1. [실행 방법](#1-실행-방법)
2. [프로젝트 구조](#2-프로젝트-구조)
3. [저장 파일 위치 / 형식](#3-저장-파일-위치--형식)
4. [주요 명령 예시](#4-주요-명령-예시)
5. [import / export CSV 스키마](#5-import--export-csv-스키마)
6. [오류 처리와 종료 코드](#6-오류-처리와-종료-코드)
7. [설계 포인트](#7-설계-포인트)
8. [실행 검증 로그 (체크리스트)](#8-실행-검증-로그-체크리스트)

---

## 1. 실행 방법

### 요구 환경

- **Python 3.10 이상** (`X | None` 타입 문법, `typing.ParamSpec` 사용)
- 외부 라이브러리 없음 (`pip install` 필요 없음)

> [!IMPORTANT]
> macOS 기본 `python3`는 3.9이므로 실행되지 않습니다.
> `python3.12`처럼 3.10 이상 버전을 직접 지정하거나, 3.10 이상으로 가상환경을 만들어 실행하세요.

### 실습 환경

이 README의 실행 로그를 만든 환경입니다.

| 항목 | 내용 |
| --- | --- |
| OS | macOS 15.7.4 (Build 24G517) |
| CPU 아키텍처 | x86_64 (Intel) |
| Python | 3.12.13 (`/usr/local/opt/python@3.12/bin/python3.12`, Homebrew) |
| 시스템 기본 Python | 3.9.6 (`/usr/bin/python3`, 이 프로젝트 실행 불가) |
| 셸 | zsh 5.9 |
| Git | 2.53.0 |
| 외부 패키지 | 없음 (표준 라이브러리만 사용) |

### 실행

저장소 루트(`Codyssey-B2-1/`)에서 아래처럼 실행합니다.

```bash
python3.12 -m budget_app --help                  # 전체 명령 목록
python3.12 -m budget_app <명령> --help           # 명령별 사용법
python3.12 -m budget_app --data-dir ./mydata list  # 저장 폴더 변경 (전역 옵션은 명령보다 앞에)
python3.12 -m budget_app --verbose list          # 실행 로그를 화면(stderr)에도 출력
```

| 전역 옵션 | 설명 |
| --- | --- |
| `--data-dir DIR` | 데이터 저장 폴더 (기본: `./data`, 실행한 위치 기준) |
| `--verbose` | 실행 시작/종료/소요 시간 로그를 화면에도 출력 |

---

## 2. 프로젝트 구조

```text
budget_app/
├── __main__.py    # 진입점: python -m budget_app → sys.exit(main())
├── cli.py         # CLI 계층: argparse 명령/옵션, 대화형 입력, 출력
├── services.py    # 서비스 계층: 검색/요약/예산/카테고리 정책/CSV
├── repository.py  # 저장소 계층: JSONL 파일 읽기/쓰기 (스트리밍, 원자적 교체)
├── models.py      # 모델 계층: dataclass(Transaction, Budget, ...) + 입력 검증
├── decorators.py  # 공통 관심사: @handle_errors, @log_execution, @timed
└── errors.py      # 사용자 정의 예외: AppError / ValidationError / NotFoundError
```

| 계층 | 주요 클래스/함수 | 책임 |
| --- | --- | --- |
| CLI | `build_parser`, `cmd_xxx`, `ask` | 입력을 받아 서비스에 넘기고 결과를 출력 |
| 서비스 | `BudgetService` | 비즈니스 규칙 (카테고리 사용 중 삭제 차단, 예산 사용률 계산 등) |
| 저장소 | `TransactionRepository`, `CategoryStore`, `BudgetStore` | 파일 I/O 전담 |
| 모델 | `Transaction`, `Budget`, `MonthlySummary`, `ImportResult` | 데이터 구조 + `__post_init__` 검증 |

---

## 3. 저장 파일 위치 / 형식

- **위치**: 기본 `./data/` (명령을 실행한 위치 기준). `--data-dir`로 변경할 수 있습니다.
- **형식**: **JSONL** (한 줄에 JSON 객체 하나, UTF-8)
- **초기 실행**: 폴더와 파일이 없으면 자동으로 생성합니다.
  카테고리 파일이 비어 있으면 기본 카테고리(`food, transport, rent, salary, etc`)를 자동 생성합니다. (미션의 안 A)

| 파일 | 내용 | 한 줄 예시 |
| --- | --- | --- |
| `transactions.jsonl` | 거래 내역 | `{"id": "TX-000001", "type": "expense", "date": "2026-10-15", "amount": 17000, "category": "food", "memo": "점심 김밥", "tags": ["meal", "lunch"]}` |
| `categories.jsonl` | 카테고리 목록 | `{"name": "food"}` |
| `budgets.jsonl` | 월별 예산 | `{"month": "2026-10", "amount": 600000}` |
| `app.log` | 실행 로그 (데이터 아님) | `2026-10-20 15:15:01,123 [INFO] 실행 시작: cmd_list` |

### 거래(Transaction) 필드

| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| `id` | str | `TX-` + 6자리 숫자, 자동 생성 (가장 큰 번호 + 1) |
| `type` | str | `income` 또는 `expense` |
| `date` | str | `YYYY-MM-DD` (실제 달력 기준 검증) |
| `amount` | int | 양수 정수 (`15,000`처럼 쉼표 입력 허용) |
| `category` | str | 등록된 카테고리 (소문자로 통일) |
| `memo` | str | 선택 |
| `tags` | list[str] | 선택, 입력 시 쉼표로 구분 |

---

## 4. 주요 명령 예시

| 명령 | 입력 방식 | 예시 |
| --- | --- | --- |
| `add` | 대화형 | `add` |
| `list` | 옵션 | `list --limit 5` (기본 20건) |
| `search` | 옵션 | `search --from 2026-10-01 --to 2026-10-31 --category food --type expense --q 점심 --tag meal` |
| `summary` | 옵션 | `summary --month 2026-10 --top 3` (기본 TOP 5) |
| `budget set` / `budget get` | 옵션 | `budget set --month 2026-10 --amount 500000` |
| `category list` | - | `category list` |
| `category add` | 위치 인자 또는 대화형 | `category add hobby` / `category add` |
| `category remove` | 위치 인자 또는 대화형 | `category remove hobby --replace etc` |
| `update` | **옵션 방식으로 고정** | `update --id TX-000001 --amount 17000 --memo "점심 김밥"` |
| `delete` | 옵션 | `delete --id TX-000007` |
| `import` | 옵션 | `import --from import.csv` |
| `export` | 옵션 | `export --out export.csv --month 2026-10` 또는 `--from ... --to ...` |

- `update`는 지정한 옵션의 필드만 바꿉니다. `--memo ""`, `--tags ""`로 값을 지울 수 있습니다.
- `category remove`에서 해당 카테고리를 쓰는 거래가 있으면 **삭제를 막습니다.**
  `--replace <대체 카테고리>`를 주면 거래를 그 카테고리로 옮긴 뒤 삭제합니다.
- `export`는 `--month` 또는 `--from/--to` 중 하나 이상이 **필수**입니다.

---

## 5. import / export CSV 스키마

**공통: UTF-8, 첫 줄 헤더 포함** (import는 엑셀이 붙이는 BOM이 있는 UTF-8도 읽음)

| column | required | 설명 |
| --- | --- | --- |
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` / `expense` |
| `category` | Y | 등록된 카테고리 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표(`,`) 구분 문자열 (CSV 안에서는 `"meal,friend"`처럼 따옴표로 감쌈) |

```csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,3000000,10월 월급,
2026-10-02,expense,rent,450000,월세,"fixed,house"
```

- **import**: 필수 컬럼이 헤더에 없으면 전체를 중단합니다.
  잘못된 행(형식 오류, 미등록 카테고리 등)은 **그 행만 건너뛰고** 사유와 건수를 출력합니다.
- **export**: 헤더 순서는 위 표와 같습니다. 출력한 건수를 알려줍니다.

---

## 6. 오류 처리와 종료 코드

모든 오류는 스택트레이스 대신 `[오류] 원인` + `[힌트] 해결 방법` 형태로 출력합니다.
예상하지 못한 예외의 스택트레이스는 화면에 출력하지 않고 `data/app.log`에만 기록합니다.

| 종료 코드 | 의미 | 예 |
| --- | --- | --- |
| `0` | 정상 종료 | 모든 성공 |
| `1` | 실행 중 오류 (`AppError`, 파일 오류 등) | 없는 id, 사용 중 카테고리 삭제, CSV 파일 없음 |
| `2` | 명령/옵션 형식 오류 (argparse) | `--month 2026-13`, 필수 옵션 누락 |
| `130` | 사용자가 Ctrl+C로 중단 | `add` 입력 중 Ctrl+C |

---

## 7. 설계 포인트

- **제너레이터 스트리밍**: `iter_jsonl()` → `TransactionRepository.iter_all()` → `BudgetService.search()`가
  `yield`로 한 줄씩 전달합니다. `list`/`search`는 `heapq.nlargest`로 최신 N건만 메모리에 유지하고,
  `summary`는 한 건씩 합계에 더하기만 합니다.
- **데코레이터**: `@handle_errors`(예외 → 메시지 + 종료 코드), `@log_execution`(시작/종료/실패 로그),
  `@timed`(소요 시간 측정). `@handle_errors`는 `dispatch` 한 곳에만 붙여 모든 명령에 적용됩니다.
- **타입 힌트**: `TxType = Literal["income", "expense"]`, `Callable[P, R]` + `ParamSpec`으로
  데코레이터가 원래 함수의 시그니처를 유지합니다.
- **원자적 저장**: update/delete/카테고리 삭제/예산 덮어쓰기는 같은 폴더의 임시 파일에 전부 쓴 뒤
  `os.replace()`로 교체합니다. 중간에 실패해도 원본 파일이 깨지지 않습니다.
- **검증 일원화**: `models.py`의 `parse_xxx` 함수를 대화형 입력(`ask`)과 argparse 옵션(`argtype`)이
  함께 사용합니다.

---

## 8. 실행 검증 로그 (체크리스트)

> [!NOTE]
> **검증 환경**: macOS, Python 3.12.13, 2026-10-20 실행
> 빈 폴더에서 `data/`가 없는 상태로 시작해 아래 순서대로 실행했습니다.
> 저장소 밖의 빈 폴더에서 실행하려고 `PYTHONPATH`를 저장소 루트로 지정했습니다.
> 대화형 입력은 실제 터미널(pty)에서 입력했고, 입력한 값이 화면에 그대로 보입니다.
> 각 명령 뒤의 `echo $?`는 종료 코드입니다.

### 체크리스트 요약

- [x] add/list/search/summary/export/import/update/delete가 요구사항대로 동작하는가? → [8-1](#8-1-addlistsearchsummaryexportimportupdatedelete)
- [x] 프로그램 재실행 후에도 거래/카테고리/예산 데이터가 유지되는가? (저장 파일 3개 이상) → [8-2](#8-2-재실행-후-데이터-유지-저장-파일-3개)
- [x] category add/list/remove가 정상 동작하는가? (삭제 시 사용 중인 카테고리 처리 포함) → [8-3](#8-3-category-addlistremove)
- [x] budget set이 저장되며, summary에서 예산 사용률/초과 여부가 출력되는가? → [8-4](#8-4-budget-set--summary-예산-사용률초과)
- [x] import/export가 명시된 CSV 스키마(UTF-8, 헤더, 컬럼)로 동작하는가? → [8-5](#8-5-importexport-csv-스키마)
- [x] 잘못된 입력/파일 오류에서 스택트레이스 없이 오류 메시지와 해결 힌트를 출력하는가? → [8-6](#8-6-잘못된-입력파일-오류--스택트레이스-없음)
- [x] 오류 상황에서 종료 코드가 0이 아님을 확인할 수 있는가? → [8-7](#8-7-오류-시-종료-코드)

---

### 8-0. `--help`

```text
$ python3.12 -m budget_app --help
usage: python -m budget_app [-h] [--data-dir DATA_DIR] [--verbose] <명령> ...

나만의 용돈 기입장 - 파일 기반 콘솔 가계부

positional arguments:
  <명령>
    add                거래 추가 (대화형)
    list               최신순 거래 목록
    search             조건 검색 (최신순)
    summary            월별 요약 + 예산 사용률
    budget             월 예산 설정/조회
    category           카테고리 관리
    update             거래 수정 (옵션 방식)
    delete             거래 삭제
    import             CSV 가져오기
    export             CSV 내보내기 (기간 조건 필수)

options:
  -h, --help           show this help message and exit
  --data-dir DATA_DIR  데이터 저장 폴더 (기본: ./data)
  --verbose            실행 로그를 화면에도 출력

각 명령의 자세한 사용법: python -m budget_app <명령> --help
$ echo $?
0

$ python3.12 -m budget_app search --help
usage: python -m budget_app search [-h] [--from DATE_FROM] [--to DATE_TO]
                                   [--category CATEGORY]
                                   [--type {income,expense}] [--q Q]
                                   [--tag TAG] [--limit LIMIT]

options:
  -h, --help            show this help message and exit
  --from DATE_FROM      시작일 YYYY-MM-DD (포함)
  --to DATE_TO          종료일 YYYY-MM-DD (포함)
  --category CATEGORY   카테고리
  --type {income,expense}
                        income 또는 expense
  --q Q                 메모 키워드 (대소문자 무시)
  --tag TAG             태그
  --limit LIMIT         표시할 최대 건수(기본: 전체)
$ echo $?
0

$ python3.12 -m budget_app update --help
usage: python -m budget_app update [-h] --id ID [--date DATE]
                                   [--type {income,expense}]
                                   [--category CATEGORY] [--amount AMOUNT]
                                   [--memo MEMO] [--tags TAGS]

options:
  -h, --help            show this help message and exit
  --id ID               수정할 거래 id (예: TX-000001)
  --date DATE           YYYY-MM-DD
  --type {income,expense}
                        income 또는 expense
  --category CATEGORY   등록된 카테고리
  --amount AMOUNT       양수 금액
  --memo MEMO           메모 (빈 값 "" 으로 지우기 가능)
  --tags TAGS           쉼표 구분 태그 (빈 값 "" 으로 지우기 가능)
$ echo $?
0

$ python3.12 -m budget_app export --help
usage: python -m budget_app export [-h] --out OUT [--month MONTH]
                                   [--from DATE_FROM] [--to DATE_TO]

--month 또는 --from/--to 중 하나 이상이 필요합니다.

options:
  -h, --help        show this help message and exit
  --out OUT         저장할 CSV 경로
  --month MONTH     YYYY-MM
  --from DATE_FROM  YYYY-MM-DD
  --to DATE_TO      YYYY-MM-DD
$ echo $?
0
```

---

### 8-1. add/list/search/summary/export/import/update/delete

#### add (대화형) — 정상 입력

```text
$ python3.12 -m budget_app add
새 거래를 입력합니다. (취소: Ctrl + C)
날짜(YYYY-MM-DD, 엔터=2026-10-20): 2026-10-15
타입(income/expense): expense
  (등록된 카테고리: food, transport, rent, salary, etc, hobby)
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
$ echo $?
0
```

#### add (대화형) — 잘못 입력하면 그 항목만 다시 묻기

```text
$ python3.12 -m budget_app add
새 거래를 입력합니다. (취소: Ctrl + C)
날짜(YYYY-MM-DD, 엔터=2026-10-20): 2026-13-40
[오류] 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[힌트] 예: 2026-10-15
날짜(YYYY-MM-DD, 엔터=2026-10-20): 2026-10-16
타입(income/expense): spend
[오류] 허용되지 않은 타입입니다: 'spend'
[힌트] income(수입) 또는 expense(지출) 중 하나를 입력하세요.
타입(income/expense): expense
  (등록된 카테고리: food, transport, rent, salary, etc, hobby)
카테고리: coffee
[오류] 등록되지 않은 카테고리입니다: 'coffee'
[힌트] 사용 가능: food, transport, rent, salary, etc, hobby / 새로 만들려면: category add coffee
카테고리: hobby
금액(양수): -3000
[오류] 금액은 0보다 큰 양수여야 합니다.
[힌트] 지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다.
금액(양수): 0
[오류] 금액은 0보다 큰 양수여야 합니다.
[힌트] 지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다.
금액(양수): abc
[오류] 금액은 정수로 입력해야 합니다: 'abc'
[힌트] 예: 15000 또는 15,000 (소수점, 문자 불가)
금액(양수): 25,000
메모(선택): 보드게임
태그(쉼표로 구분, 없으면 엔터): friend, weekend
[저장 완료] id=TX-000002
$ echo $?
0
```

#### import (CSV에서 한꺼번에 등록)

```text
$ cat import.csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,3000000,10월 월급,
2026-10-02,expense,rent,450000,월세,"fixed,house"
2026-10-05,expense,transport,62000,교통카드 충전,
2026-10-08,expense,food,18000,친구랑 저녁,"meal,friend"
2026-09-25,expense,food,12000,9월 점심,meal
2026-10-10,expense,shopping,30000,옷,
2026-10-11,expense,food,-5000,음수 금액,
2026-13-01,income,salary,1000,잘못된 날짜,

$ python3.12 -m budget_app import --from import.csv
  [건너뜀] 7번째 줄: 등록되지 않은 카테고리입니다: 'shopping'
  [건너뜀] 8번째 줄: 금액은 0보다 큰 양수여야 합니다.
  [건너뜀] 9번째 줄: 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[완료] imported=5, skipped=3
$ echo $?
0
```

#### list (최신순, `--limit`)

```text
$ python3.12 -m budget_app list --limit 3
TX-000002 | 2026-10-16 | expense | hobby      |     25,000원 | 보드게임 #friend #weekend
TX-000001 | 2026-10-15 | expense | food       |     15,000원 | 점심 #meal
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
(최신순 3건)
$ echo $?
0

$ python3.12 -m budget_app list
TX-000002 | 2026-10-16 | expense | hobby      |     25,000원 | 보드게임 #friend #weekend
TX-000001 | 2026-10-15 | expense | food       |     15,000원 | 점심 #meal
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
TX-000005 | 2026-10-05 | expense | transport  |     62,000원 | 교통카드 충전
TX-000004 | 2026-10-02 | expense | rent       |    450,000원 | 월세 #fixed #house
TX-000003 | 2026-10-01 | income  | salary     |  3,000,000원 | 10월 월급
TX-000007 | 2026-09-25 | expense | food       |     12,000원 | 9월 점심 #meal
(최신순 7건)
$ echo $?
0
```

#### search (`--from/--to`, `--category`, `--type`, `--q`, `--tag`, 조건 조합)

```text
$ python3.12 -m budget_app search --from 2026-10-01 --to 2026-10-10
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
TX-000005 | 2026-10-05 | expense | transport  |     62,000원 | 교통카드 충전
TX-000004 | 2026-10-02 | expense | rent       |    450,000원 | 월세 #fixed #house
TX-000003 | 2026-10-01 | income  | salary     |  3,000,000원 | 10월 월급
(최신순 4건)
$ echo $?
0

$ python3.12 -m budget_app search --category food
TX-000001 | 2026-10-15 | expense | food       |     15,000원 | 점심 #meal
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
TX-000007 | 2026-09-25 | expense | food       |     12,000원 | 9월 점심 #meal
(최신순 3건)
$ echo $?
0

$ python3.12 -m budget_app search --type income
TX-000003 | 2026-10-01 | income  | salary     |  3,000,000원 | 10월 월급
(최신순 1건)
$ echo $?
0

$ python3.12 -m budget_app search --q 점심
TX-000001 | 2026-10-15 | expense | food       |     15,000원 | 점심 #meal
TX-000007 | 2026-09-25 | expense | food       |     12,000원 | 9월 점심 #meal
(최신순 2건)
$ echo $?
0

$ python3.12 -m budget_app search --tag meal
TX-000001 | 2026-10-15 | expense | food       |     15,000원 | 점심 #meal
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
TX-000007 | 2026-09-25 | expense | food       |     12,000원 | 9월 점심 #meal
(최신순 3건)
$ echo $?
0

$ python3.12 -m budget_app search --type expense --from 2026-10-01 --tag friend
TX-000002 | 2026-10-16 | expense | hobby      |     25,000원 | 보드게임 #friend #weekend
TX-000006 | 2026-10-08 | expense | food       |     18,000원 | 친구랑 저녁 #meal #friend
(최신순 2건)
$ echo $?
0

$ python3.12 -m budget_app search --category rent --type income
[안내] 검색 결과가 없습니다.
$ echo $?
0
```

#### summary (데이터 있는 달 / 데이터 없는 달)

```text
$ python3.12 -m budget_app summary --month 2026-09
──── 2026-09 월별 요약 ────
총 수입: 0원
총 지출: 12,000원
잔액:   -12,000원
예산:   100,000원 (사용률 12.0%)

지출 TOP 5
1) food 12,000원
$ echo $?
0

$ python3.12 -m budget_app summary --month 2026-08
──── 2026-08 월별 요약 ────
데이터 없음
$ echo $?
0
```

> 예산과 함께 출력되는 summary는 [8-4](#8-4-budget-set--summary-예산-사용률초과)에 있습니다.

#### update (옵션 방식) — 성공 / 없는 id / 수정 항목 없음 / 미등록 카테고리 / 잘못된 값

```text
$ python3.12 -m budget_app update --id TX-000001 --amount 17000 --memo "점심 김밥" --tags "meal,lunch"
[수정 완료] TX-000001 | 2026-10-15 | expense | food       |     17,000원 | 점심 김밥 #meal #lunch
$ echo $?
0

$ python3.12 -m budget_app update --id TX-000006 --date 2026-10-09 --category hobby
[수정 완료] TX-000006 | 2026-10-09 | expense | hobby      |     18,000원 | 친구랑 저녁 #meal #friend
$ echo $?
0

$ python3.12 -m budget_app update --id TX-999999 --amount 1000
[오류] id 'TX-999999'에 해당하는 거래가 없습니다.
[힌트] list 또는 search 명령으로 id를 확인하세요.
$ echo $?
1

$ python3.12 -m budget_app update --id TX-000001
[오류] 수정할 항목이 없습니다.
[힌트] 예: update --id TX-000001 --amount 20000 --memo 저녁
$ echo $?
1

$ python3.12 -m budget_app update --id TX-000001 --category coffee
[오류] 등록되지 않은 카테고리입니다: 'coffee'
[힌트] 사용 가능: food, transport, rent, salary, etc, hobby / 새로 만들려면: category add coffee
$ echo $?
1

$ python3.12 -m budget_app update --id TX-000001 --amount -100
usage: python -m budget_app update [-h] --id ID [--date DATE]
                                   [--type {income,expense}]
                                   [--category CATEGORY] [--amount AMOUNT]
                                   [--memo MEMO] [--tags TAGS]
python -m budget_app update: error: argument --amount: 금액은 0보다 큰 양수여야 합니다. 지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다.
$ echo $?
2
```

#### delete — 성공 / 없는 id

```text
$ python3.12 -m budget_app delete --id TX-000007
[삭제 완료] id=TX-000007
$ echo $?
0

$ python3.12 -m budget_app delete --id TX-000007
[오류] id 'TX-000007'에 해당하는 거래가 없습니다.
[힌트] list 또는 search 명령으로 id를 확인하세요.
$ echo $?
1

$ python3.12 -m budget_app list
TX-000002 | 2026-10-16 | expense | hobby      |     25,000원 | 보드게임 #friend #weekend
TX-000001 | 2026-10-15 | expense | food       |     17,000원 | 점심 김밥 #meal #lunch
TX-000006 | 2026-10-09 | expense | hobby      |     18,000원 | 친구랑 저녁 #meal #friend
TX-000005 | 2026-10-05 | expense | transport  |     62,000원 | 교통카드 충전
TX-000004 | 2026-10-02 | expense | rent       |    450,000원 | 월세 #fixed #house
TX-000003 | 2026-10-01 | income  | salary     |  3,000,000원 | 10월 월급
(최신순 6건)
$ echo $?
0
```

#### export

[8-5](#8-5-importexport-csv-스키마)에 있습니다.

---

### 8-2. 재실행 후 데이터 유지 (저장 파일 3개)

명령을 실행할 때마다 프로세스가 새로 시작되므로, 위의 모든 결과가 이어지는 것 자체가 영구 저장의 증거입니다.
아래는 첫 실행 전후의 `data/` 폴더와, 모든 작업이 끝난 뒤의 저장 파일 내용입니다.

```text
$ ls data
ls: data: No such file or directory

$ python3.12 -m budget_app category list
- food
- transport
- rent
- salary
- etc
$ echo $?
0

$ ls data
app.log			categories.jsonl
budgets.jsonl		transactions.jsonl
```

모든 작업이 끝난 뒤:

```text
$ ls -l data
total 48
-rw-r--r--  1 c4321qwaszx9029  c4321qwaszx9029  8479 10 20 15:15 app.log
-rw-------  1 c4321qwaszx9029  c4321qwaszx9029    78 10 20 15:15 budgets.jsonl
-rw-------  1 c4321qwaszx9029  c4321qwaszx9029    91 10 20 15:15 categories.jsonl
-rw-------  1 c4321qwaszx9029  c4321qwaszx9029   883 10 20 15:15 transactions.jsonl

$ cat data/transactions.jsonl
{"id": "TX-000001", "type": "expense", "date": "2026-10-15", "amount": 17000, "category": "food", "memo": "점심 김밥", "tags": ["meal", "lunch"]}
{"id": "TX-000002", "type": "expense", "date": "2026-10-16", "amount": 25000, "category": "etc", "memo": "보드게임", "tags": ["friend", "weekend"]}
{"id": "TX-000003", "type": "income", "date": "2026-10-01", "amount": 3000000, "category": "salary", "memo": "10월 월급", "tags": []}
{"id": "TX-000004", "type": "expense", "date": "2026-10-02", "amount": 450000, "category": "rent", "memo": "월세", "tags": ["fixed", "house"]}
{"id": "TX-000005", "type": "expense", "date": "2026-10-05", "amount": 62000, "category": "transport", "memo": "교통카드 충전", "tags": []}
{"id": "TX-000006", "type": "expense", "date": "2026-10-09", "amount": 18000, "category": "etc", "memo": "친구랑 저녁", "tags": ["meal", "friend"]}

$ cat data/categories.jsonl
{"name": "food"}
{"name": "transport"}
{"name": "rent"}
{"name": "salary"}
{"name": "etc"}

$ cat data/budgets.jsonl
{"month": "2026-10", "amount": 600000}
{"month": "2026-09", "amount": 100000}

$ python3.12 -m budget_app list --limit 3
TX-000002 | 2026-10-16 | expense | etc        |     25,000원 | 보드게임 #friend #weekend
TX-000001 | 2026-10-15 | expense | food       |     17,000원 | 점심 김밥 #meal #lunch
TX-000006 | 2026-10-09 | expense | etc        |     18,000원 | 친구랑 저녁 #meal #friend
(최신순 3건)
$ echo $?
0

$ python3.12 -m budget_app summary --month 2026-10 --top 3
──── 2026-10 월별 요약 ────
총 수입: 3,000,000원
총 지출: 572,000원
잔액:   2,428,000원
예산:   600,000원 (사용률 95.3%)
[주의] 예산의 80% 이상을 사용했습니다.

지출 TOP 3
1) rent 450,000원
2) transport 62,000원
3) etc 43,000원
$ echo $?
0
```

- 거래(update/delete 반영), 카테고리(`hobby` 추가 후 삭제 반영), 예산(600,000원으로 덮어쓰기 반영)이 모두 파일에 남아 있습니다.
- `transactions.jsonl` / `categories.jsonl` / `budgets.jsonl` 3개 파일로 나눠 저장합니다.

---

### 8-3. category add/list/remove

#### add (대화형 / 위치 인자) + 중복 / list

```text
$ python3.12 -m budget_app category add
카테고리명: hobby
[저장 완료] category=hobby
$ echo $?
0

$ python3.12 -m budget_app category add Hobby
[오류] 'hobby' 카테고리는 이미 존재합니다.
[힌트] category list로 목록을 확인하세요.
$ echo $?
1

$ python3.12 -m budget_app category list
- food
- transport
- rent
- salary
- etc
- hobby
$ echo $?
0
```

#### remove — 사용 중이면 차단 → `--replace`로 옮기며 삭제 / 미사용 삭제 / 없는 카테고리

```text
$ python3.12 -m budget_app category remove hobby
[오류] 'hobby' 카테고리를 사용하는 거래가 2건 있어 삭제할 수 없습니다.
[힌트] 다른 카테고리로 옮기며 삭제하려면: category remove hobby --replace etc
$ echo $?
1

$ python3.12 -m budget_app category remove hobby --replace etc
[안내] 거래 2건의 카테고리를 'etc'(으)로 변경했습니다.
[삭제 완료] category=hobby
$ echo $?
0

$ python3.12 -m budget_app category add temp
[저장 완료] category=temp
$ echo $?
0

$ python3.12 -m budget_app category remove
삭제할 카테고리명: temp
[삭제 완료] category=temp
$ echo $?
0

$ python3.12 -m budget_app category remove travel
[오류] 'travel' 카테고리가 존재하지 않습니다.
[힌트] category list 로 목록을 확인하세요.
$ echo $?
1

$ python3.12 -m budget_app category list
- food
- transport
- rent
- salary
- etc
$ echo $?
0

$ python3.12 -m budget_app search --category etc
TX-000002 | 2026-10-16 | expense | etc        |     25,000원 | 보드게임 #friend #weekend
TX-000006 | 2026-10-09 | expense | etc        |     18,000원 | 친구랑 저녁 #meal #friend
(최신순 2건)
$ echo $?
0
```

---

### 8-4. budget set + summary (예산 사용률/초과)

```text
$ python3.12 -m budget_app budget get --month 2026-10
[안내] 2026-10 예산이 설정되어 있지 않습니다.
$ echo $?
0

$ python3.12 -m budget_app budget set --month 2026-10 --amount 500000
[저장 완료] 2026-10 예산 500,000원
$ echo $?
0

$ python3.12 -m budget_app budget get --month 2026-10
2026-10 예산: 500,000원
$ echo $?
0

$ python3.12 -m budget_app summary --month 2026-10 --top 3
──── 2026-10 월별 요약 ────
총 수입: 3,000,000원
총 지출: 570,000원
잔액:   2,430,000원
예산:   500,000원 (사용률 114.0%)
[경고] 예산을 70,000원 초과했습니다!

지출 TOP 3
1) rent 450,000원
2) transport 62,000원
3) food 33,000원
$ echo $?
0

$ python3.12 -m budget_app budget set --month 2026-10 --amount 600000
[저장 완료] 2026-10 예산 600,000원
$ echo $?
0

$ python3.12 -m budget_app summary --month 2026-10
──── 2026-10 월별 요약 ────
총 수입: 3,000,000원
총 지출: 570,000원
잔액:   2,430,000원
예산:   600,000원 (사용률 95.0%)
[주의] 예산의 80% 이상을 사용했습니다.

지출 TOP 5
1) rent 450,000원
2) transport 62,000원
3) food 33,000원
4) hobby 25,000원
$ echo $?
0
```

- 예산을 넘으면 `[경고]`와 초과 금액을, 80% 이상이면 `[주의]`를 출력합니다.
- 같은 월에 다시 `budget set`을 하면 덮어씁니다. 재실행 후에도 유지되는 것은 [8-2](#8-2-재실행-후-데이터-유지-저장-파일-3개)에서 확인할 수 있습니다.

---

### 8-5. import/export (CSV 스키마)

#### export — `--month` / `--from --to` / 조건 없음(오류)

```text
$ python3.12 -m budget_app export --out export.csv --month 2026-10
[완료] export.csv (6 records)
$ echo $?
0

$ cat export.csv
date,type,category,amount,memo,tags
2026-10-15,expense,food,17000,점심 김밥,"meal,lunch"
2026-10-16,expense,etc,25000,보드게임,"friend,weekend"
2026-10-01,income,salary,3000000,10월 월급,
2026-10-02,expense,rent,450000,월세,"fixed,house"
2026-10-05,expense,transport,62000,교통카드 충전,
2026-10-09,expense,etc,18000,친구랑 저녁,"meal,friend"

$ python3.12 -m budget_app export --out early.csv --from 2026-10-01 --to 2026-10-05
[완료] early.csv (3 records)
$ echo $?
0

$ cat early.csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,3000000,10월 월급,
2026-10-02,expense,rent,450000,월세,"fixed,house"
2026-10-05,expense,transport,62000,교통카드 충전,

$ python3.12 -m budget_app export --out none.csv
[오류] 내보낼 기간 조건이 없습니다.
[힌트] --month 2026-10 또는 --from 2026-10-01 --to 2026-10-31 을 지정하세요.
$ echo $?
1
```

#### 왕복 확인 — export한 파일을 새 저장 폴더(`./data2`)로 import

```text
$ python3.12 -m budget_app --data-dir ./data2 import --from export.csv
[완료] imported=6, skipped=0
$ echo $?
0

$ python3.12 -m budget_app --data-dir ./data2 list
TX-000002 | 2026-10-16 | expense | etc        |     25,000원 | 보드게임 #friend #weekend
TX-000001 | 2026-10-15 | expense | food       |     17,000원 | 점심 김밥 #meal #lunch
TX-000006 | 2026-10-09 | expense | etc        |     18,000원 | 친구랑 저녁 #meal #friend
TX-000005 | 2026-10-05 | expense | transport  |     62,000원 | 교통카드 충전
TX-000004 | 2026-10-02 | expense | rent       |    450,000원 | 월세 #fixed #house
TX-000003 | 2026-10-01 | income  | salary     |  3,000,000원 | 10월 월급
(최신순 6건)
$ echo $?
0
```

- export 파일은 UTF-8이고 헤더 `date,type,category,amount,memo,tags`가 들어갑니다. 한글 메모와 쉼표가 들어간 태그도 그대로 import됩니다.
- 잘못된 행을 건너뛰는 import 예시는 [8-1 import](#import-csv에서-한꺼번에-등록)에, 헤더 오류는 [8-6](#8-6-잘못된-입력파일-오류--스택트레이스-없음)에 있습니다.

---

### 8-6. 잘못된 입력/파일 오류 — 스택트레이스 없음

```text
$ python3.12 -m budget_app search --from 2026-10-10 --to 2026-10-01
[오류] 시작일(2026-10-10)이 종료일(2026-10-01)보다 늦습니다.
[힌트] --from 은 --to 보다 같거나 이른 날짜여야 합니다.
$ echo $?
1

$ python3.12 -m budget_app import --from nofile.csv
[오류] 가져올 CSV 파일을 찾을 수 없습니다: nofile.csv
[힌트] 파일 경로를 확인하세요. 예: import --from ./import.csv
$ echo $?
1

$ cat bad_header.csv
날짜,종류,금액
2026-10-01,income,1000

$ python3.12 -m budget_app import --from bad_header.csv
[오류] CSV 헤더에 필수 컬럼이 없습니다. date, type, category, amount
[힌트] 첫 줄(헤더)은 다음과 같아야 합니다: date,type,category,amount,memo,tags
$ echo $?
1

$ touch not_a_dir

$ python3.12 -m budget_app --data-dir ./not_a_dir list
[오류] 파일을 처리하는 중 문제가 발생했습니다: File exists (not_a_dir)
[힌트] 경로와 권한을 확인하세요. --data-dir 옵션으로 저장 위치를 바꿀 수 있습니다.
$ echo $?
1

$ python3.12 -m budget_app add
새 거래를 입력합니다. (취소: Ctrl + C)
날짜(YYYY-MM-DD, 엔터=2026-10-20): 2026-10-20
타입(income/expense): ^C
[중단] 사용자가 작업을 취소했습니다. 저장되지 않은 입력은 버려집니다.
$ echo $?
130

$ python3.12 -m budget_app add
새 거래를 입력합니다. (취소: Ctrl + C)
날짜(YYYY-MM-DD, 엔터=2026-10-20): 2026-10-20
타입(income/expense): [오류] 입력이 끝나서 작업을 계속할 수 없습니다.
[힌트] 대화형 명령(add 등)은 터미널에서 직접 실행하세요.
$ echo $?
1
```

> 마지막 예시는 타입 입력 중에 Ctrl+D(EOF)를 누른 경우입니다. 터미널이 `^D` 표시를 지운 뒤 오류 메시지를 출력합니다.

옵션 형식 오류는 argparse가 사용법과 원인을 함께 출력합니다. (스택트레이스 없음)

```text
$ python3.12 -m budget_app summary --month 2026-13
usage: python -m budget_app summary [-h] --month MONTH [--top TOP]
python -m budget_app summary: error: argument --month: 월 형식이 올바르지 않습니다 (YYYY-MM). 예: 2026-10
$ echo $?
2

$ python3.12 -m budget_app list --limit 0
usage: python -m budget_app list [-h] [--limit LIMIT]
python -m budget_app list: error: argument --limit: 1이상의 정수여야 합니다. 예: 10
$ echo $?
2

$ python3.12 -m budget_app budget set --month 2026-10 --amount 0
usage: python -m budget_app budget set [-h] --month MONTH --amount AMOUNT
python -m budget_app budget set: error: argument --amount: 금액은 0보다 큰 양수여야 합니다. 지출도 양수로 입력하고, 수입/지출 구분은 타입(income/expense)으로 합니다.
$ echo $?
2

$ python3.12 -m budget_app delete
usage: python -m budget_app delete [-h] --id ID
python -m budget_app delete: error: the following arguments are required: --id
$ echo $?
2

$ python3.12 -m budget_app
usage: python -m budget_app [-h] [--data-dir DATA_DIR] [--verbose] <명령> ...
python -m budget_app: error: the following arguments are required: <명령>
$ echo $?
2
```

전체 검증을 마친 뒤 로그 파일에도 `Traceback`이 한 번도 기록되지 않았습니다.
`--verbose`를 주면 데코레이터(`@log_execution`, `@timed`)가 남기는 로그를 화면에서도 볼 수 있습니다.

```text
$ grep -c Traceback data/app.log
0

$ python3.12 -m budget_app --verbose list --limit 1
[로그] 실행 시작: cmd_list
TX-000002 | 2026-10-16 | expense | etc        |     25,000원 | 보드게임 #friend #weekend
(최신순 1건)
[로그] 소요 시간: cmd_list 0.003초
[로그] 실행 종료: cmd_list
$ echo $?
0
```

---

### 8-7. 오류 시 종료 코드

위 로그의 `echo $?` 결과를 정리한 표입니다. 성공한 경우는 모두 `0`, 오류가 난 경우는 모두 `0`이 아닌 값입니다.

| 상황 | 명령 | 종료 코드 |
| --- | --- | --- |
| 중복 카테고리 추가 | `category add Hobby` | `1` |
| 없는 id 수정 | `update --id TX-999999 --amount 1000` | `1` |
| 수정 항목 없음 | `update --id TX-000001` | `1` |
| 미등록 카테고리로 수정 | `update --id TX-000001 --category coffee` | `1` |
| 없는 id 삭제 | `delete --id TX-000007` (두 번째) | `1` |
| 사용 중 카테고리 삭제 | `category remove hobby` | `1` |
| 없는 카테고리 삭제 | `category remove travel` | `1` |
| export 조건 없음 | `export --out none.csv` | `1` |
| 검색 기간 역전 | `search --from 2026-10-10 --to 2026-10-01` | `1` |
| CSV 파일 없음 | `import --from nofile.csv` | `1` |
| CSV 헤더 오류 | `import --from bad_header.csv` | `1` |
| 저장 경로 오류 | `--data-dir ./not_a_dir list` | `1` |
| 입력 중 EOF(Ctrl+D) | `add` | `1` |
| 잘못된 옵션 값 | `summary --month 2026-13`, `list --limit 0`, `budget set ... --amount 0`, `update ... --amount -100` | `2` |
| 필수 인자 누락 | `delete`, 명령 없이 실행 | `2` |
| 사용자 중단(Ctrl+C) | `add` | `130` |
