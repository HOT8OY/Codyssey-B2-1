"""
errors.py — 프로그램 전용 예외(Exception) 모음
================================================

[이 파일이 왜 필요한가요?]
미션 요구사항에 "오류는 스택트레이스 대신 '원인 + 해결 힌트'로 출력한다"가 있습니다.

파이썬에서 처리되지 않은 예외가 발생하면 아래처럼 무시무시한 화면이 나옵니다.

    Traceback (most recent call last):
      File "...", line 12, in <module>
    ValueError: invalid literal for int() with base 10: 'abc'

이건 개발자에게는 유용하지만, 일반 사용자에게는 "프로그램이 고장났다"로 보입니다.
그래서 우리는 "사용자에게 보여줄 메시지(message)"와 "해결 방법(hint)"을
함께 담는 예외 클래스를 직접 만들고, 맨 바깥(decorators.handle_errors)에서
이 예외를 잡아 예쁘게 출력합니다.

    [오류] 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
    [힌트] 예: 2024-01-15

[클래스 상속 구조]
    Exception            ← 파이썬 기본 예외
     └─ AppError         ← 우리 프로그램의 모든 예외의 "부모"
         ├─ ValidationError  ← 입력값이 잘못됨 (날짜 형식, 음수 금액 등)
         └─ NotFoundError    ← 찾는 데이터가 없음 (없는 id, 없는 파일 등)

부모를 하나로 묶어두면 `except AppError:` 한 줄로
모든 자식 예외를 한꺼번에 잡을 수 있습니다. (다형성)
"""


class AppError(Exception):
    """프로그램에서 '예상 가능한' 모든 오류의 부모 클래스.

    Attributes:
        message: 무엇이 잘못되었는지 (원인)
        hint:    어떻게 고치면 되는지 (해결 힌트). 없으면 빈 문자열.
        exit_code: 이 오류로 프로그램이 끝날 때 돌려줄 종료 코드.
                   0은 '정상 종료'라는 약속이므로, 오류는 0이 아닌 값이어야 합니다.
    """

    # 클래스 변수: 모든 AppError 객체가 공유하는 기본값.
    # 자식 클래스에서 다른 값으로 덮어쓸 수도 있습니다.
    exit_code: int = 1

    def __init__(self, message: str, hint: str = "") -> None:
        # super().__init__(message)를 호출해 두면
        # str(error) 했을 때 message가 나오는 등 기본 예외 동작이 유지됩니다.
        super().__init__(message)
        self.message = message
        self.hint = hint


class ValidationError(AppError):
    """사용자가 입력한 값(또는 파일에서 읽은 값)이 규칙에 맞지 않을 때.

    예) 날짜가 2024-13-40, 금액이 -500, 타입이 'spend', 등록되지 않은 카테고리 등
    """


class NotFoundError(AppError):
    """찾으려는 대상이 존재하지 않을 때.

    예) delete --id TX-999999 처럼 없는 id를 지정했을 때,
        import --from 에 존재하지 않는 파일을 지정했을 때
    """
