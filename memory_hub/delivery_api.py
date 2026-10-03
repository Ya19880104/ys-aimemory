"""Authenticated relay REST routes; intentionally absent from MCP discovery."""
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from .session_service import SessionActor


def install_delivery_api(app, hub, principal_context):
    def actor():
        return SessionActor.from_principal(principal_context.get())

    def response(result):
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @app.get('/v1/chat/status')
    def status(project_id: str, session_id: str):
        try:
            return response(hub.delivery.call('status', {'project_id': project_id, 'session_id': session_id}, actor()))
        except ValidationError:
            return JSONResponse({'error': 'invalid_arguments'}, status_code=422)

    @app.post('/v1/chat/{operation}')
    async def operation(operation: str, request: Request):
        if operation not in {'join', 'heartbeat', 'claim', 'dispatched', 'pause', 'control', 'disconnect'}:
            return JSONResponse({'error': 'unknown_delivery_operation'}, status_code=404)
        try:
            payload = await request.json()
            result = await run_in_threadpool(hub.delivery.call, operation, payload, actor())
            return response(result)
        except (ValueError, ValidationError):
            # Never echo arguments, native identifiers, or bearer values on error.
            return JSONResponse({'error': 'invalid_arguments'}, status_code=422)
