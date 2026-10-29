from starlette.exceptions import HTTPException

from app.core.config import settings


class ResumeBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not (
            path.startswith("/api/v1/resumes") or path.startswith("/api/v1/extractions")
        ):
            return await self.app(scope, receive, send)
        upload = scope.get("method") == "POST" and (
            path == "/api/v1/resumes" or path.endswith("/versions")
        )
        limit = settings.resume_max_bytes if upload else 256 * 1024
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length < 0 or length > limit:
            from starlette.responses import JSONResponse

            return await JSONResponse(
                {
                    "error": {
                        "code": "body_too_large",
                        "message": "Resume request exceeds the configured size limit",
                    }
                },
                status_code=413,
            )(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "Resume request exceeds the configured size limit")
            return message

        await self.app(scope, bounded_receive, send)
