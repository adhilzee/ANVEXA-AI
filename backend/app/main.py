from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging
from backend.app.services.document_service import DuplicateDocumentError


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description="Evidence-traceable academic document verification API.",
    )

    @application.exception_handler(DuplicateDocumentError)
    def duplicate_document_handler(request, exc: DuplicateDocumentError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "existing_document_id": exc.existing_document_id,
                "status": exc.status,
            },
            headers=dict(exc.headers or {}),
        )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix=app_settings.api_v1_prefix)

    # Static assets and sample demo papers
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    sample_dir = Path(__file__).resolve().parents[2] / "sample_papers"
    if sample_dir.is_dir():
        application.mount("/sample-papers", StaticFiles(directory=str(sample_dir)), name="sample_papers")

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon():
        favicon_path = static_dir / "favicon.ico"
        if favicon_path.is_file():
            return FileResponse(favicon_path, media_type="image/x-icon")
        return Response(status_code=204)

    @application.get("/manifest.json", include_in_schema=False)
    @application.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        manifest_path = static_dir / "manifest.json"
        if manifest_path.is_file():
            return FileResponse(
                manifest_path,
                media_type="application/manifest+json",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        return Response(status_code=404)

    @application.get("/sw.js", include_in_schema=False)
    def service_worker():
        sw_path = static_dir / "sw.js"
        if sw_path.is_file():
            return FileResponse(
                sw_path,
                media_type="application/javascript",
                headers={
                    "Service-Worker-Allowed": "/",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
        return Response(status_code=404)

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
    @application.get("/dashboard", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
    def serve_dashboard() -> HTMLResponse:
        html_path = Path(__file__).parent / "static" / "dashboard.html"
        if html_path.is_file():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>ANVEXA AI Platform Active</h1><p>Visit <a href='/docs'>/docs</a></p>")

    return application


app = create_app()
