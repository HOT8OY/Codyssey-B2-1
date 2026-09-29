# 📓 학습 노트: 미션 핵심 개념 쉽게 이해하기

> 이 문서는 미션에서 요구하는 세 가지 핵심 개념을  
> **비유 → 기초 코드 → 미션 실전 적용** 순으로 차근차근 설명합니다.

---

## 목차

1. [JSON vs JSONL — 두 형식의 차이](#1-json-vs-jsonl--두-형식의-차이)
2. [yield 제너레이터 — 스트리밍 처리](#2-yield-제너레이터--스트리밍-처리)
3. [데코레이터(Decorator) — 공통 기능 분리](#3-데코레이터decorator--공통-기능-분리)

---

## 1. JSON vs JSONL — 두 형식의 차이

### 📌 먼저, JSON이란?

JSON(JavaScript Object Notation)은 데이터를 **사람이 읽기 쉬운 텍스트** 형태로 저장하는 표준 형식입니다.  
Python의 `dict`나 `list`와 거의 똑같이 생겼습니다.

```json
{
  "id": "TX-000001",
  "date": "2024-01-15",
  "type": "expense",
  "amount": 15000,
  "category": "food",
  "memo": "점심"
}
```

Python에서는 `json` 표준 라이브러리로 쉽게 읽고 쓸 수 있습니다.

```python
import json

# dict → JSON 문자열로 변환
data = {"id": "TX-000001", "amount": 15000}
json_str = json.dumps(data, ensure_ascii=False)
print(json_str)  # '{"id": "TX-000001", "amount": 15000}'

# JSON 문자열 → dict로 변환
loaded = json.loads(json_str)
print(loaded["amount"])  # 15000

# 파일로 쓰기
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 파일 읽기
with open("data.json", "r", encoding="utf-8") as f:
    loaded_from_file = json.load(f)
```

---

### 📌 그러면 JSONL이란?

JSONL(JSON Lines)은 **한 줄에 하나의 JSON 객체**를 넣는 형식입니다.  
확장자는 `.jsonl` 또는 `.json`을 쓰기도 합니다.

```
{"id": "TX-000001", "date": "2024-01-15", "type": "expense", "amount": 15000}
{"id": "TX-000002", "date": "2024-01-16", "type": "income", "amount": 3000000}
{"id": "TX-000003", "date": "2024-01-17", "type": "expense", "amount": 20000}
```

각 줄이 독립적인 완전한 JSON 객체입니다.

---

### 🆚 JSON vs JSONL 비교

| 비교 항목 | JSON | JSONL |
| :--- | :--- | :--- |
| **파일 구조** | 파일 전체가 하나의 구조(`[]` 또는 `{}`) | 줄마다 독립된 JSON 객체 |
| **한 줄 추가** | ❌ 파일 전체를 다시 써야 함 | ✅ 맨 끝에 줄 하나 추가만 하면 됨 |
| **한 줄씩 처리(스트리밍)** | ❌ 파일 전체를 읽어야 파싱 가능 | ✅ 줄 단위로 읽으며 처리 가능 |
| **가독성** | 들여쓰기/구조 파악 쉬움 | 단순하지만 컬럼 파악이 어려울 수 있음 |
| **주요 용도** | 설정 파일, API 응답 | 로그, 대용량 데이터, 가계부 내역 |

---

### 💡 비유로 이해하기

> **JSON** = 책 📚  
> 목차, 장, 절이 전부 연결된 하나의 문서. 책 전체를 펼쳐야 원하는 내용을 찾을 수 있습니다.
>
> **JSONL** = 영수증 묶음 🧾🧾🧾  
> 영수증 하나하나가 독립적입니다. 맨 위에 새 영수증을 끼워 넣거나, 한 장씩 꺼내 보기 쉽습니다.

---

### 🎯 미션에서의 JSONL 활용

미션에서 거래 내역을 JSONL로 저장하면 아래처럼 사용할 수 있습니다.

```python
import json
from dataclasses import dataclass, asdict
from typing import Iterator

@dataclass
class Transaction:
    id: str
    date: str
    type: str
    amount: int
    category: str
    memo: str = ""

# 거래 저장: 파일 끝에 한 줄 추가만 하면 됨 (효율적!)
def save_transaction(tx: Transaction, filepath: str = "data/transactions.jsonl") -> None:
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(tx), ensure_ascii=False) + "\n")

# 거래 읽기: 줄 하나 = 거래 하나
def load_transactions(filepath: str = "data/transactions.jsonl") -> list[Transaction]:
    transactions = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:  # 빈 줄 건너뜀
                data = json.loads(line)
                transactions.append(Transaction(**data))
    return transactions
```

---

## 2. yield 제너레이터 — 스트리밍 처리

### 📌 문제 상황: 메모리가 터진다?

거래 내역이 100만 건이라고 상상해 보세요.  
아래처럼 **한꺼번에 다 읽으면** 무슨 일이 생길까요?

```python
# ❌ 위험한 방법: 파일 전체를 메모리에 올림
def load_all_transactions(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()   # 100만 줄을 한 번에 RAM에 올림!

    result = []
    for line in lines:
        result.append(json.loads(line.strip()))
    return result  # 100만 개의 dict가 메모리에 가득!
```

데이터가 크면 프로그램이 멈추거나, 컴퓨터 전체가 느려질 수 있습니다.

---

### 📌 yield가 뭐야? — `return`과의 차이

`return`은 값을 반환하고 **함수를 끝내버립니다**.  
`yield`는 값을 반환하고 **함수를 잠깐 멈춥니다** (다음 호출 때 이어서 실행).

```python
# return 방식: 한꺼번에 모든 값을 리스트로 만들어 반환
def get_numbers_return():
    result = []
    for i in range(5):
        result.append(i * 2)
    return result  # [0, 2, 4, 6, 8] 전부 만들어서 반환

# yield 방식: 값을 하나씩 그때그때 반환
def get_numbers_yield():
    for i in range(5):
        yield i * 2  # 0 반환 → 잠깐 멈춤 → 2 반환 → 잠깐 멈춤 → ...
```

```python
# 사용 방법은 거의 똑같습니다
for n in get_numbers_return():
    print(n)

for n in get_numbers_yield():
    print(n)
```

두 코드의 **출력은 동일**합니다. 차이는 **메모리 사용 방식**입니다.

---

### 💡 비유로 이해하기

> **return (일반 함수)** = 편의점 도시락 🍱  
> 공장에서 모든 재료를 미리 다 담아 포장해 옵니다.  
> 한 번에 모든 게 준비되지만, 재료가 많으면 포장 상자도 엄청 커집니다.
>
> **yield (제너레이터)** = 스시 컨베이어 벨트 🍣  
> 접시를 한 번에 100개 쌓아두지 않습니다.  
> 먹을 때 하나씩 올려줍니다. 접시는 언제나 딱 1~2개만 앞에 있습니다.

---

### 📌 제너레이터 함수 기초

`yield`를 사용하는 함수를 **제너레이터 함수**라고 합니다.  
호출하면 값 자체가 아니라 **제너레이터 객체**를 반환합니다.

```python
def countdown(n: int):
    """n부터 1까지 카운트다운하는 제너레이터"""
    print("카운트다운 시작!")
    while n > 0:
        yield n          # 값을 하나 내보내고 "일시 정지"
        n -= 1
    print("카운트다운 끝!")

# 제너레이터 객체 생성 (아직 아무것도 실행되지 않음!)
gen = countdown(3)
print(type(gen))  # <class 'generator'>

# next()로 하나씩 꺼내기
print(next(gen))  # 출력: 카운트다운 시작! \n 3
print(next(gen))  # 출력: 2
print(next(gen))  # 출력: 1
# print(next(gen))  # StopIteration 에러 (더 이상 없음)

# 보통은 for문으로 쓰면 자동으로 처리됨
for n in countdown(3):
    print(n)  # 3, 2, 1
```

---

### 📌 `yield from` — 다른 이터러블을 이어서 내보내기

```python
def chain_numbers():
    yield from range(1, 4)     # 1, 2, 3
    yield from range(10, 13)   # 10, 11, 12

for n in chain_numbers():
    print(n)  # 1, 2, 3, 10, 11, 12
```

---

### 🎯 미션에서의 제너레이터 활용

파일을 **줄 단위로 읽는 스트리밍 함수**를 만들면 됩니다.

```python
import json
from typing import Generator

# ✅ 좋은 방법: 제너레이터로 한 줄씩 읽기
def stream_transactions(filepath: str) -> Generator[dict, None, None]:
    """JSONL 파일을 한 줄씩 읽어 dict를 yield하는 제너레이터"""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:              # 파일을 한 줄씩 읽음 (메모리 절약!)
            line = line.strip()
            if not line:
                continue            # 빈 줄 건너뜀
            yield json.loads(line)  # 한 줄 파싱 후 반환, 다음 줄로 이동

# 사용 예시: 최신 N건만 보기 (100만 건이어도 메모리 걱정 없음!)
def get_latest_n(filepath: str, limit: int = 20) -> list[dict]:
    all_txs = list(stream_transactions(filepath))
    # 날짜 기준 내림차순 정렬 후 limit 개 반환
    sorted_txs = sorted(all_txs, key=lambda tx: tx["date"], reverse=True)
    return sorted_txs[:limit]

# 검색도 제너레이터로 처리할 수 있음
def search_by_category(filepath: str, category: str) -> Generator[dict, None, None]:
    for tx in stream_transactions(filepath):        # 스트리밍으로 읽으면서
        if tx.get("category") == category:          # 조건에 맞는 것만
            yield tx                                # 하나씩 내보냄
```

```python
# 실제 사용 예시
for tx in search_by_category("data/transactions.jsonl", "food"):
    print(f"{tx['date']} | {tx['amount']}원 | {tx['memo']}")
    # 파일 전체를 메모리에 올리지 않고 필터링 가능!
```

---

### 📊 메모리 사용량 비교

| 방식 | 데이터 100건 | 데이터 100만 건 |
| :--- | :--- | :--- |
| `readlines()` + 리스트 | 몇 KB | 수백 MB ~ GB |
| `yield` 제너레이터 | 몇 KB | 몇 KB (동일!) |

제너레이터는 **한 번에 한 줄**만 메모리에 올리기 때문에, 데이터가 아무리 많아도 메모리 사용량이 거의 일정합니다.

---

## 3. 데코레이터(Decorator) — 공통 기능 분리

### 📌 문제 상황: 반복되는 코드

모든 함수에 예외 처리와 로그를 넣어야 한다고 해봅시다.

```python
# ❌ 나쁜 방법: 함수마다 똑같은 코드 반복
def add_transaction(tx):
    print(f"[로그] add_transaction 시작")
    try:
        # 실제 로직
        save_transaction(tx)
        print(f"[로그] add_transaction 완료")
    except Exception as e:
        print(f"[오류] {e}")

def delete_transaction(tx_id):
    print(f"[로그] delete_transaction 시작")
    try:
        # 실제 로직
        remove_from_file(tx_id)
        print(f"[로그] delete_transaction 완료")
    except Exception as e:
        print(f"[오류] {e}")
```

함수가 10개면 같은 코드를 10번 써야 합니다. 유지보수도 지옥입니다. 🔥

---

### 📌 데코레이터란?

데코레이터는 **함수를 감싸는 함수**입니다.  
기존 함수를 건드리지 않고, **앞뒤에 공통 기능을 끼워 넣을 수 있습니다**.

Python에서는 `@데코레이터명`을 함수 위에 붙이는 간편한 문법을 제공합니다.

---

### 💡 비유로 이해하기

> **데코레이터** = 선물 포장지 🎁  
> 선물(함수) 자체는 그대로인데, 포장지(데코레이터)를 씌우면  
> 겉모습(기능)이 달라집니다. 포장지를 바꾸거나 추가하기도 쉽습니다.

---

### 📌 데코레이터 기초: 함수를 감싸는 함수

데코레이터를 이해하려면 먼저 **함수가 값처럼 전달될 수 있다**는 것을 알아야 합니다.

```python
# 파이썬에서 함수는 변수처럼 다룰 수 있습니다
def greet():
    print("안녕하세요!")

say_hello = greet       # 함수를 변수에 대입
say_hello()             # 안녕하세요! (정상 동작)

# 함수를 인자로 받는 함수
def call_twice(func):
    func()
    func()

call_twice(greet)       # 안녕하세요! \n 안녕하세요!
```

---

### 📌 데코레이터 만들기 — 단계별로

**Step 1**: 가장 기본 구조

```python
def my_decorator(func):         # 함수를 인자로 받음
    def wrapper(*args, **kwargs):   # 원래 함수를 감싸는 함수
        print("실행 전")
        result = func(*args, **kwargs)  # 원래 함수 호출
        print("실행 후")
        return result
    return wrapper              # 감싼 함수를 반환
```

**Step 2**: 적용하기 — `@` 없이 직접 적용

```python
def add(a, b):
    return a + b

add = my_decorator(add)  # 직접 감싸기
add(1, 2)
# 출력:
# 실행 전
# 실행 후
```

**Step 3**: `@` 문법으로 깔끔하게 (Step 2와 완전히 동일)

```python
@my_decorator       # add = my_decorator(add) 와 100% 같은 의미!
def add(a, b):
    return a + b

add(1, 2)
# 출력:
# 실행 전
# 실행 후
```

---

### 📌 `functools.wraps` — 함수 정보 보존

데코레이터를 쓰면 함수 이름과 docstring이 `wrapper`로 바뀌는 부작용이 있습니다.  
`functools.wraps`를 써서 원래 함수 정보를 유지하세요.

```python
import functools

def my_decorator(func):
    @functools.wraps(func)      # ← 원래 함수의 이름/docstring 유지
    def wrapper(*args, **kwargs):
        print("실행 전")
        result = func(*args, **kwargs)
        print("실행 후")
        return result
    return wrapper

@my_decorator
def add(a, b):
    """두 수를 더합니다."""
    return a + b

print(add.__name__)   # add (wraps 없으면 wrapper가 출력됨)
print(add.__doc__)    # 두 수를 더합니다.
```

---

### 🎯 미션에서의 데코레이터 활용

미션에서 구현해야 하는 3가지 대표 데코레이터 예시입니다.

#### ① 예외 처리 데코레이터

```python
import functools
import sys

def handle_errors(func):
    """스택트레이스 대신 친절한 에러 메시지를 출력하는 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            print(f"[오류] 파일을 찾을 수 없습니다: {e.filename}")
            print(f"[힌트] 'python -m budget_app init' 으로 초기화하세요.")
            sys.exit(1)
        except ValueError as e:
            print(f"[오류] 입력값이 올바르지 않습니다: {e}")
            print(f"[힌트] --help 옵션으로 올바른 입력 형식을 확인하세요.")
            sys.exit(1)
        except Exception as e:
            print(f"[오류] 예상치 못한 오류가 발생했습니다: {e}")
            sys.exit(1)
    return wrapper

# 적용 예시
@handle_errors
def cmd_add():
    """add 명령 처리 함수"""
    # 에러가 나도 스택트레이스 없이 친절한 메시지 출력!
    date = input("날짜(YYYY-MM-DD): ")
    ...
```

#### ② 실행 로그 데코레이터

```python
import functools
import datetime

def log_command(func):
    """함수 실행 시작/완료를 로그로 남기는 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {func.__name__} 명령 실행 시작")
        result = func(*args, **kwargs)
        print(f"[{timestamp}] {func.__name__} 명령 완료")
        return result
    return wrapper

@log_command
def cmd_export(out_path: str, month: str):
    """export 명령 처리"""
    ...
```

#### ③ 실행 시간 측정 데코레이터

```python
import functools
import time

def measure_time(func):
    """함수 실행 시간을 측정하는 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"[시간] {func.__name__} 실행 완료 ({elapsed:.3f}초)")
        return result
    return wrapper

@measure_time
def cmd_summary(month: str):
    """월별 요약 처리 (대용량일 때 얼마나 걸리는지 측정)"""
    ...
```

#### 데코레이터 여러 개 동시 적용

```python
# 아래처럼 여러 데코레이터를 쌓아서 쓸 수 있습니다.
# 적용 순서: 가장 가까운 것부터 (handle_errors → log_command → measure_time 순으로 감쌈)
@measure_time
@log_command
@handle_errors
def cmd_list(limit: int = 20):
    """list 명령 처리"""
    for tx in get_latest_n("data/transactions.jsonl", limit):
        print(f"{tx['id']} | {tx['date']} | {tx['type']} | {tx['amount']}원")
```

---

## 📋 전체 요약

| 개념 | 한 줄 요약 | 미션에서의 역할 |
| :--- | :--- | :--- |
| **JSON** | 파일 전체가 하나의 구조 | 설정 파일 등에 적합 |
| **JSONL** | 한 줄 = 한 레코드 | 거래 내역처럼 계속 추가되는 데이터에 최적 |
| **yield 제너레이터** | 값을 하나씩 그때그때 반환 | 대용량 파일도 메모리 걱정 없이 처리 |
| **데코레이터** | 함수를 감싸 공통 기능 추가 | 예외 처리, 로그, 시간 측정을 중복 없이 분리 |

---

## 💬 자주 하는 질문 (FAQ)

**Q. 제너레이터를 쓰면 항상 빠른가요?**  
A. 꼭 그렇지는 않습니다. 데이터를 **전부 봐야 하는 작업**(예: 정렬)은 결국 모든 항목을 한 번은 읽어야 합니다. 제너레이터의 진짜 이점은 **메모리 절약**과 **필요한 만큼만 처리**하는 데 있습니다.

**Q. 데코레이터를 반드시 만들어야 하나요?**  
A. 미션 요구사항에 "1개 이상 구현 및 실제 적용"이 필수입니다. `handle_errors` 하나만 만들어 모든 커맨드 함수에 적용해도 요건을 충족합니다.

**Q. JSONL 파일의 확장자는 뭘 써야 하나요?**  
A. 미션 문서에서는 `transactions.jsonl` 형태를 권장하지만, `.json`을 써도 내부 포맷이 JSONL이면 동일합니다. 가독성을 위해 `.jsonl`을 권장합니다.

**Q. `*args, **kwargs`가 뭔가요?**  
A. 데코레이터 `wrapper` 함수 안에서 원래 함수의 **모든 인자를 그대로 전달**하기 위한 표현입니다.  
`*args`는 위치 인자 모음, `**kwargs`는 키워드 인자 모음입니다.  
데코레이터는 어떤 함수에든 범용적으로 쓰여야 하므로, 인자 모양을 미리 정하지 않고 이렇게 씁니다.

---

*📝 이 노트는 미션 [mission.md](./mission.md)의 핵심 개념 이해를 돕기 위해 작성되었습니다.*
