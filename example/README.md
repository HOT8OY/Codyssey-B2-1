# 나만의 용돈 기입장 — budget_app

파일 기반 가계부 CLI 프로그램입니다.  
Python 표준 라이브러리만 사용하며, JSONL 형식으로 데이터를 영구 저장합니다.

---

## 실행 방법

```bash
# example 폴더 안에서 실행
cd example
python3 cli.py <명령어> [옵션]
```

모든 명령은 `--help` 옵션으로 사용법을 확인할 수 있습니다.

```bash
python3 cli.py --help
python3 cli.py list --help
python3 cli.py summary --help
```

---

## 저장 파일 위치 및 형식

기본 저장 위치: `./data/` (변경하려면 `--data-dir <경로>` 옵션 사용)

| 파일 | 형식 | 내용 |
| :--- | :--- | :--- |
| `data/transactions.jsonl` | JSONL | 거래 내역 (한 줄 = 거래 1건) |
| `data/categories.jsonl` | JSONL | 카테고리 목록 |
| `data/budgets.jsonl` | JSONL | 월별 예산 |

### JSONL 파일 예시

**transactions.jsonl**
```jsonl
{"id": "TX-000001", "type": "expense", "date": "2024-01-15", "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}
{"id": "TX-000002", "type": "income", "date": "2024-01-16", "amount": 3000000, "category": "salary", "memo": "월급", "tags": []}
```

**categories.jsonl**
```jsonl
{"name": "food"}
{"name": "transport"}
{"name": "salary"}
```

**budgets.jsonl**
```jsonl
{"month": "2024-01", "amount": 500000}
```

---

## 주요 명령 예시

### 거래 추가
```bash
python3 cli.py add
# 날짜(YYYY-MM-DD): 2024-01-15
# 타입(income/expense): expense
# 카테고리: food
# 금액(양수 정수): 15000
# 메모(선택, 없으면 엔터): 점심
# 태그(쉼표로 구분, 없으면 엔터): meal
# [저장 완료] id=TX-000001
```

### 거래 목록 조회
```bash
python3 cli.py list
python3 cli.py list --limit 5
```

### 거래 검색
```bash
python3 cli.py search --category food
python3 cli.py search --from 2024-01-01 --to 2024-01-31
python3 cli.py search --type expense --q 점심
python3 cli.py search --tag meal
```

### 월별 요약
```bash
python3 cli.py summary --month 2024-01
python3 cli.py summary --month 2024-01 --top 3
```

### 예산 설정
```bash
python3 cli.py budget set --month 2024-01 --amount 500000
```

### 카테고리 관리
```bash
python3 cli.py category list
python3 cli.py category add
python3 cli.py category remove
```

### 거래 수정 (옵션 기반)
```bash
python3 cli.py update --id TX-000001 --amount 20000
python3 cli.py update --id TX-000001 --memo "수정된 메모" --category transport
python3 cli.py update --id TX-000001 --tags "meal,lunch"
```

### 거래 삭제
```bash
python3 cli.py delete --id TX-000001
```

### CSV 내보내기
```bash
python3 cli.py export --out export.csv --month 2024-01
python3 cli.py export --out export.csv --from 2024-01-01 --to 2024-01-31
```

### CSV 가져오기
```bash
python3 cli.py import --from import.csv
```

---

## Import/Export CSV 스키마

| 컬럼 | 필수 | 설명 |
| :--- | :---: | :--- |
| `date` | ✅ | YYYY-MM-DD 형식 |
| `type` | ✅ | `income` 또는 `expense` |
| `category` | ✅ | 등록된 카테고리 이름 |
| `amount` | ✅ | 양수 정수 |
| `memo` | ❌ | 문자열 (없으면 빈 칸) |
| `tags` | ❌ | 쉼표(,) 구분 문자열 |

- 인코딩: UTF-8
- 헤더 행 포함 필수

CSV 예시:
```csv
date,type,category,amount,memo,tags
2024-01-15,expense,food,15000,점심,meal
2024-01-16,income,salary,3000000,월급,
```

---

## 파일 구조

```
example/
├── __main__.py      # python -m 실행 진입점
├── cli.py           # CLI 계층: 명령어 파싱 및 사용자 입력 처리
├── services.py      # 서비스 계층: 비즈니스 로직 및 입력 검증
├── repository.py    # 저장소 계층: 파일 입출력 (JSONL 읽기/쓰기)
├── models.py        # 모델 계층: 데이터 구조 정의 (dataclass)
├── decorators.py    # 공통 데코레이터: 예외 처리, 시간 측정
└── data/            # 데이터 저장 폴더 (자동 생성)
    ├── transactions.jsonl
    ├── categories.jsonl
    └── budgets.jsonl
```

---

## 개발 환경

- Python 3.10 이상
- 외부 라이브러리 없음 (표준 라이브러리만 사용)
