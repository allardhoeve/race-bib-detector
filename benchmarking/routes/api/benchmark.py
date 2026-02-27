"""Benchmark JSON API endpoints."""

from fastapi import APIRouter, HTTPException

from benchmarking.photo_index import load_photo_index
from benchmarking.schemas import FreezeRequest, FreezeResponse

api_benchmark_router = APIRouter()


@api_benchmark_router.post('/api/freeze', response_model=FreezeResponse)
async def api_freeze(request: FreezeRequest) -> FreezeResponse:
    from benchmarking.sets import freeze
    name = request.name.strip()
    hashes = request.hashes

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not hashes:
        raise HTTPException(status_code=400, detail="hashes list is empty")

    index = load_photo_index()
    flat_index = {h: (paths[0] if isinstance(paths, list) else paths)
                  for h, paths in index.items() if h in hashes}

    try:
        snapshot = freeze(
            name=name,
            hashes=sorted(flat_index.keys()),
            index=flat_index,
            description=request.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return FreezeResponse(**snapshot.metadata.to_dict())
