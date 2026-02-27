"""Backward-compatibility shims: 301/308 redirects and 410 gone endpoints."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

shims_router = APIRouter()


# ---- BIB / ASSOCIATIONS --------------------------------------------------

@shims_router.get('/labels/')
async def labels_index_redirect(request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('bibs_index'))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@shims_router.get('/labels/{content_hash}')
async def labels_photo_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('bib_photo', content_hash=content_hash))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@shims_router.post('/api/labels')
async def save_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/bibs/<hash>."""
    raise HTTPException(status_code=410, detail='Use PUT /api/bibs/<hash>')


@shims_router.get('/links/')
async def links_index_redirect(request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(url=str(request.url_for('associations_index')), status_code=301)


@shims_router.get('/links/{content_hash}')
async def links_photo_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('association_photo', content_hash=content_hash)),
        status_code=301,
    )


@shims_router.get('/api/bib_boxes/{content_hash}')
async def get_bib_boxes_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_bib_boxes', content_hash=content_hash)),
        status_code=308,
    )


@shims_router.get('/api/bib_face_links/{content_hash}')
async def get_bib_face_links_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_associations', content_hash=content_hash)),
        status_code=308,
    )


@shims_router.put('/api/bib_face_links/{content_hash}')
async def save_bib_face_links_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('save_associations', content_hash=content_hash)),
        status_code=308,
    )


# ---- FACE ----------------------------------------------------------------

@shims_router.get('/faces/labels/')
async def face_labels_redirect(request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('faces_index'))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@shims_router.get('/faces/labels/{content_hash}')
async def face_label_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('face_photo', content_hash=content_hash))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@shims_router.post('/api/face_labels')
async def save_face_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/faces/<hash>."""
    raise HTTPException(status_code=410, detail='Use PUT /api/faces/<hash>')


@shims_router.get('/api/face_boxes/{content_hash}')
async def get_face_boxes_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_face_boxes', content_hash=content_hash)),
        status_code=308,
    )


@shims_router.get('/api/face_identity_suggestions/{content_hash}')
async def face_identity_suggestions_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    qs = ('?' + str(request.url.query)) if request.url.query else ''
    return RedirectResponse(
        url=str(request.url_for('face_identity_suggestions', content_hash=content_hash)) + qs,
        status_code=308,
    )


@shims_router.get('/api/face_crop/{content_hash}/{box_index}')
async def face_crop_redirect(content_hash: str, box_index: int, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('face_crop', content_hash=content_hash, box_index=box_index)),
        status_code=308,
    )


# ---- IDENTITIES ----------------------------------------------------------

@shims_router.post('/api/rename_identity')
async def rename_identity_legacy():
    """Legacy rename endpoint — gone. Use PATCH /api/identities/<name>."""
    raise HTTPException(status_code=410, detail='Use PATCH /api/identities/<name>')


# ---- BENCHMARK -----------------------------------------------------------

@shims_router.get('/staging/')
async def staging_redirect(request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(url=str(request.url_for('staging')), status_code=301)


@shims_router.get('/artifact/{run_id}/{hash_prefix}/{image_type}')
async def serve_artifact_redirect(run_id: str, hash_prefix: str, image_type: str, request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('serve_artifact', run_id=run_id,
                                hash_prefix=hash_prefix, image_type=image_type)),
        status_code=301,
    )
