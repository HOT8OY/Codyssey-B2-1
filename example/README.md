# 용돈 기입장 — 참고 구현 (example)

[`etc/plan.md`](../etc/plan.md)의 Step 0~9를 그대로 구현한 **참고용 코드**입니다.
모든 파일에 초보자용 주석을 달아 두었습니다. 직접 만들 `budget_app/`을 짜다가 막힐 때 참고하세요.

> [!IMPORTANT]
> 이 Mac의 기본 `python3`는 **3.9**라서 실행되지 않습니다. (`ParamSpec`, `X | Y` 문법은 3.10 이상)
> `python3.12`를 사용하거나 가상환경을 3.10 이상으로 만드세요.

## 실행 방법

저장소 루트(`Codyssey-B2-1/`)에서 실행합니다.

```bash
python3.12 -m example --help              # 전체 명령 목록
python3.12 -m example <명령> --help       # 명령별 사용법
python3.12 -m example --data-dir ./mydata list   # 전역 옵션은 명령보다 앞에
```

> 직접 만드는 `budget_app/`에서는 `python -m budget_app ...`이 됩니다.
> 이 코드는 상대 import(`from .models import ...`)만 쓰므로 폴더째 복사해도 그대로 동작합니다.

## 파일 구성 (읽는 순서 추천)

| 순서 | 파일 | 계층 | 핵심 개념 |
| --- | --- | --- | --- |
| 1 | [errors.py](errors.py) | 공통 | 예외 상속, message + hint |
| 2 | [models.py](models.py) | 모델 | `dataclass`, `__post_init__` 검증, `Literal`, `@property`, `@classmethod` |
| 3 | [repository.py](repository.py) | 저장소 | `yield` 스트리밍, 임시 파일 + `os.replace` 원자적 교체 |
| 4 | [decorators.py](decorators.py) | 공통 | 데코레이터, `functools.wraps`, `ParamSpec` |
| 5 | [services.py](services.py) | 서비스 | 제너레이터 체인, `heapq.nlargest`, CSV |
| 6 | [cli.py](cli.py) | CLI | `argparse` 서브커맨드, 대화형 재입력, 로깅 설정 |
| 7 | [\_\_main\_\_.py](__main__.py) | 진입점 | `python -m`, 상대 import, `sys.exit(code)` |

## 저장 파일

기본 위치는 `./data/`(실행한 위치 기준)이고, `--data-dir`로 바꿀 수 있습니다. 형식은 JSONL(한 줄에 JSON 하나)입니다.

| 파일 | 한 줄 예시 |
| --- | --- |
| `transactions.jsonl` | `{"id": "TX-000001", "type": "expense", "date": "2024-01-15", "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}` |
| `categories.jsonl` | `{"name": "food"}` |
| `budgets.jsonl` | `{"month": "2024-01", "amount": 500000}` |
| `app.log` | 실행 로그 (데코레이터가 기록. `--verbose`를 주면 화면에도 출력) |

## 주요 명령

```bash
python3.12 -m example add                                   # 대화형 입력
python3.12 -m example list --limit 10
python3.12 -m example search --from 2024-01-01 --to 2024-01-31 --type expense
python3.12 -m example search --category food --q 점심 --tag meal
python3.12 -m example budget set --month 2024-01 --amount 500000
python3.12 -m example budget get --month 2024-01
python3.12 -m example summary --month 2024-01 --top 3
python3.12 -m example category list
python3.12 -m example category add hobby                    # 이름을 생략하면 대화형으로 입력
python3.12 -m example category remove food --replace etc
python3.12 -m example update --id TX-000001 --amount 20000 --memo ""
python3.12 -m example delete --id TX-000001
python3.12 -m example export --out export.csv --month 2024-01
python3.12 -m example import --from import.csv
```

## import/export CSV 스키마

UTF-8이고 헤더 행이 필요합니다. import는 엑셀에서 저장한 BOM 붙은 UTF-8도 읽습니다.

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표 구분 문자열. 예: `"meal,회식"` (쉼표가 있으면 따옴표로 감쌈) |

## 설계 결정

| 항목 | 결정 |
| --- | --- |
| update | 옵션 방식으로 고정. 지정한 옵션만 수정하며, `--memo ""`처럼 빈 값을 주면 지워짐 |
| 빈 카테고리 파일 | 기본 카테고리를 자동 생성: food, transport, rent, salary, etc |
| 카테고리 삭제 | 사용 중이면 삭제를 막음. `--replace <대체>`를 주면 거래를 옮긴 뒤 삭제 |
| 최신순 기준 | `(date, id)` 내림차순. 날짜가 같으면 나중에 추가된 거래가 위로 |
| list | `heapq.nlargest`로 메모리에 N건만 유지 |
| search | `--limit`을 생략하면 일치하는 건을 모두 정렬해 출력 |
| import 오류 행 | 그 줄만 건너뛰고 줄 번호와 사유를 출력 |
| export 순서 | 파일에 저장된 순서대로 스트리밍 기록 |
| 잘못된 저장 데이터 | 깨진 줄은 경고 로그만 남기고 건너뜀 |
| 종료 코드 | 정상 0, 앱 오류 1, argparse 옵션 오류 2, Ctrl+C 130 |
