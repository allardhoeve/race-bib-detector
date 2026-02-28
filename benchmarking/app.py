"""FastAPI application factory for benchmark labeling and inspection."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse, RedirectResponse

from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.routes.api.benchmark import api_benchmark_router
from benchmarking.routes.api.bibs import api_bibs_router
from benchmarking.routes.api.faces import api_faces_router
from benchmarking.routes.api.identities import api_identities_router
from benchmarking.routes.shims import shims_router
from benchmarking.routes.ui.benchmark import ui_benchmark_router
from benchmarking.routes.ui.frozen import ui_frozen_router
from benchmarking.routes.ui.labeling import ui_labeling_router
from benchmarking.templates_env import TEMPLATES

_STATIC_DIR = Path(__file__).parent / "static"
PHOTOS_DIR = Path(__file__).parent.parent / "photos"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="BNR Benchmark", version="0.1.0", docs_url="/docs", redoc_url="/redoc")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(api_bibs_router)
    app.include_router(api_faces_router)
    app.include_router(api_identities_router)
    app.include_router(api_benchmark_router)
    app.include_router(ui_labeling_router, include_in_schema=False)
    app.include_router(ui_benchmark_router, include_in_schema=False)
    app.include_router(ui_frozen_router, include_in_schema=False)
    app.include_router(shims_router, include_in_schema=False)

    # Return 400 for request validation errors (missing/invalid params or body)
    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    # -------------------------------------------------------------------------
    # Index / Root
    # -------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        """Landing page — numbered labeling workflow with per-step progress."""
        from benchmarking.ground_truth import load_bib_ground_truth, load_face_ground_truth
        from benchmarking.label_utils import is_face_labeled

        photo_index = load_photo_index()
        total = len(photo_index)

        bib_gt = load_bib_ground_truth()
        face_gt = load_face_ground_truth()

        bib_labeled = sum(1 for lbl in bib_gt.photos.values() if lbl.labeled)
        face_labeled = sum(1 for lbl in face_gt.photos.values() if is_face_labeled(lbl))

        try:
            from benchmarking.ground_truth import load_link_ground_truth
            link_gt = load_link_ground_truth()
            links_labeled = len(link_gt.photos)
        except (ImportError, AttributeError):
            links_labeled = None

        return TEMPLATES.TemplateResponse(request, 'labels_home.html', {
            'total': total,
            'bib_labeled': bib_labeled,
            'face_labeled': face_labeled,
            'links_labeled': links_labeled,
        })

    # -------------------------------------------------------------------------
    # Shared Routes
    # -------------------------------------------------------------------------
    @app.get("/photo/{content_hash}", include_in_schema=False)
    async def serve_photo_redirect(content_hash: str, request: Request):
        """301 shim for backward compatibility."""
        return RedirectResponse(
            url=str(request.url_for("serve_photo", content_hash=content_hash)),
            status_code=301,
        )

    @app.get("/media/photos/{content_hash}", include_in_schema=False)
    async def serve_photo(content_hash: str):
        """Serve photo by content hash."""
        from benchmarking.label_utils import find_hash_by_prefix
        index = load_photo_index()

        full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
        if not full_hash:
            raise HTTPException(status_code=404, detail="Not found")

        path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(path)

    # -------------------------------------------------------------------------
    # Test route
    # -------------------------------------------------------------------------
    @app.get("/test/labeling", include_in_schema=False)
    async def test_labeling(request: Request):
        """Redirect to the browser integration test page."""
        return RedirectResponse(url=str(request.url_for("static", path="test_labeling.html")))

    return app


app = create_app()
