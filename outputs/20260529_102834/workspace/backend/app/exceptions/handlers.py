from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.exceptions.custom_exceptions import NotFoundException, ConflictException, BadRequestException
from app.schemas.common import ErrorResponse

def add_exception_handlers(app: FastAPI):
    """
    FastAPI 애플리케이션에 전역 예외 핸들러를 등록합니다.
    """

    @app.exception_handler(NotFoundException)
    async def not_found_exception_handler(request: Request, exc: NotFoundException):
        """NotFoundException (HTTP 404) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(ConflictException)
    async def conflict_exception_handler(request: Request, exc: ConflictException):
        """ConflictException (HTTP 409) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(BadRequestException)
    async def bad_request_exception_handler(request: Request, exc: BadRequestException):
        """BadRequestException (HTTP 400) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        FastAPI의 요청 유효성 검사 오류 (HTTP 422) 처리 핸들러.
        Pydantic 모델 유효성 검사 실패 시 발생합니다.
        """
        errors = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            errors.append(f"{loc}: {error['msg']}")
        detail_message = "Validation Error: " + "; ".join(errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(detail=detail_message).model_dump()
        )

    @app.exception_handler(ValidationError) # Pydantic v2의 일반 ValidationError 처리
    async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
        """
        Pydantic 모델의 일반 유효성 검사 오류 (HTTP 422) 처리 핸들러.
        RequestValidationError 외의 Pydantic 유효성 검사 오류를 처리합니다.
        """
        errors = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            errors.append(f"{loc}: {error['msg']}")
        detail_message = "Pydantic Validation Error: " + "; ".join(errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(detail=detail_message).model_dump()
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """
        처리되지 않은 모든 예외를 처리하는 제네릭 핸들러 (HTTP 500).
        """
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(detail=f"An unexpected error occurred: {str(exc)}").model_dump()
        )