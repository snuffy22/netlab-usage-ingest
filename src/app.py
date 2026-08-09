from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from models import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    SubmissionResponse,
    UsageSubmission,
)
from normalize import normalize_submission
from settings import DEFAULT_MAX_BODY_BYTES, integer_setting
from storage import ingest_submission

SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
}

app = FastAPI(
    title='Netlab anonymous usage ingestion',
    version='1.0.0',
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def request_environment(request: Request) -> Any | None:
    env = request.scope.get('env')
    if env is not None:
        return env
    return getattr(request.app.state, 'env', None)


def json_response(status: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status, content=body, headers=SECURITY_HEADERS)


def error_response(status: int, message: str) -> JSONResponse:
    body = ErrorResponse(error=message).model_dump(mode='json', exclude_none=True)
    return json_response(status, body)


def validation_details(errors: list[dict[str, Any]]) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for error in errors:
        location = '.'.join(str(part) for part in error.get('loc', ()) if part != 'body')
        details.append(ErrorDetail(
            location=location or 'body',
            message=str(error.get('msg', 'invalid value')),
            type=str(error.get('type', 'value_error')),
        ))
    return details


def rate_limit_argument() -> Any:
    # Cloudflare's FFI needs a JavaScript object. Ordinary Python dictionaries
    # are used in unit tests outside the Worker runtime.
    try:
        from js import Object
        from pyodide.ffi import to_js
    except ImportError:
        return {'key': 'v1-submissions'}
    return to_js({'key': 'v1-submissions'}, dict_converter=Object.fromEntries)


async def rate_limit_allows(env: Any | None) -> bool:
    if env is None or not hasattr(env, 'SUBMISSION_LIMITER'):
        return True
    result = await env.SUBMISSION_LIMITER.limit(rate_limit_argument())
    return bool(result.success)


@app.middleware('http')
async def submission_controls(request: Request, call_next):
    if request.method == 'POST' and request.url.path == '/v1/submissions':
        content_type = request.headers.get('content-type', '')
        if content_type.split(';', 1)[0].strip().lower() != 'application/json':
            return error_response(415, 'content-type must be application/json')

        env = request_environment(request)
        limit = integer_setting(
            env, 'MAX_BODY_BYTES', DEFAULT_MAX_BODY_BYTES, 1_024, 262_144)

        content_length = request.headers.get('content-length')
        if content_length:
            try:
                if int(content_length) > limit:
                    return error_response(413, f'request body exceeds {limit} bytes')
            except ValueError:
                return error_response(400, 'content-length is invalid')

        body = await request.body()
        if len(body) > limit:
            return error_response(413, f'request body exceeds {limit} bytes')

        if not await rate_limit_allows(env):
            return error_response(429, 'submission rate limit exceeded')

    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    details = validation_details(exception.errors())
    body = ErrorResponse(
        error='invalid submission',
        details=details,
    ).model_dump(mode='json', exclude_none=True)
    return json_response(400, body)


@app.exception_handler(PydanticValidationError)
async def pydantic_validation_error(
    _request: Request,
    exception: PydanticValidationError,
) -> JSONResponse:
    details = validation_details(exception.errors())
    body = ErrorResponse(
        error='invalid submission',
        details=details,
    ).model_dump(mode='json', exclude_none=True)
    return json_response(400, body)


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exception: StarletteHTTPException) -> JSONResponse:
    if exception.status_code == 404:
        return error_response(404, 'not found')
    return error_response(exception.status_code, str(exception.detail))


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, _exception: Exception) -> JSONResponse:
    return error_response(503, 'usage service temporarily unavailable')


@app.get('/v1/health')
async def health(request: Request) -> JSONResponse:
    env = request_environment(request)
    try:
        if env is None:
            raise RuntimeError('database binding is unavailable')
        await env.DB.prepare('SELECT 1 AS healthy').first('healthy')
        body = HealthResponse(status='ok').model_dump(mode='json')
        return json_response(200, body)
    except Exception:
        body = HealthResponse(status='unavailable').model_dump(mode='json')
        return json_response(503, body)


@app.post('/v1/submissions')
async def submit(submission: UsageSubmission, request: Request) -> JSONResponse:
    env = request_environment(request)
    if env is None:
        return error_response(503, 'usage service temporarily unavailable')

    normalized = normalize_submission(submission)
    result = await ingest_submission(env.DB, normalized)
    body = SubmissionResponse(
        status=result,
        batch_id=normalized.batch_id,
    ).model_dump(mode='json')
    return json_response(202 if result == 'accepted' else 200, body)
