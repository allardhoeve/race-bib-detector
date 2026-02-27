"""Benchmark JSON API endpoints."""

from fastapi import APIRouter, Body, HTTPException

from benchmarking.photo_index import load_photo_index

api_benchmark_router = APIRouter()


@api_benchmark_router.post('/api/freeze')
async def api_freeze(body: dict = Body(default={})):
    from benchmarking.sets import freeze
    name = body.get("name", "").strip()
    description = body.get("description", "")
    hashes = body.get("hashes", [])

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
            description=description,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return snapshot.metadata.to_dict()
