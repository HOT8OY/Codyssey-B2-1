class AppError(Exception):
    exit_code: int = 1

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

class ValidationError(AppError):
    pass

class NotFoundError(AppError):
    pass