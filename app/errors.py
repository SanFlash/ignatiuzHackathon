class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status
        super().__init__(message)


class Conflict(AppError):
    def __init__(self, message='This question was already answered or the attempt changed. Reload to continue.'):
        super().__init__(message, 409)
