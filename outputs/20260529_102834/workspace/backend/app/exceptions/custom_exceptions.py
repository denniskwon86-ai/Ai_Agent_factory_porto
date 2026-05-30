from fastapi import HTTPException, status

class NotFoundException(HTTPException):
    """
    리소스를 찾을 수 없을 때 발생하는 사용자 정의 예외입니다 (HTTP 404).
    """
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ConflictException(HTTPException):
    """
    리소스 충돌이 발생했을 때 발생하는 사용자 정의 예외입니다 (HTTP 409).
    예: 고유해야 하는 이름이 이미 존재할 때.
    """
    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)

class BadRequestException(HTTPException):
    """
    잘못된 요청이 발생했을 때 발생하는 사용자 정의 예외입니다 (HTTP 400).
    """
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

# 필요에 따라 다른 사용자 정의 예외를 추가할 수 있습니다.