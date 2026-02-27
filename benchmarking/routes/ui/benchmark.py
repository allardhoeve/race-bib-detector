"""Benchmark inspection HTML views and artifact serving."""

import json

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import FileResponse

from benchmarking.label_utils import filter_results
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import RESULTS_DIR, get_run, list_runs
from benchmarking.templates_env import TEMPLATES

ui_benchmark_router = APIRouter()


@ui_benchmark_router.get('/benchmark/')
async def benchmark_list(request: Request):
    """List all benchmark runs."""
    runs = list_runs()
    return TEMPLATES.TemplateResponse(request, 'benchmark_list.html', {'runs': runs})


@ui_benchmark_router.get('/benchmark/staging/')
async def staging(request: Request):
    from benchmarking.completeness import get_all_completeness
    rows = get_all_completeness()
    index = load_photo_index()
    return TEMPLATES.TemplateResponse(request, 'staging.html', {'rows': rows, 'index': index})


@ui_benchmark_router.get('/benchmark/{run_id}/')
async def benchmark_inspect(
    run_id: str,
    request: Request,
    filter_type: str = Query(default='all', alias='filter'),
    idx: int = Query(default=0),
    hash_query: str = Query(default='', alias='hash'),
):
    """Inspect a specific benchmark run."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail='Run not found')

    filtered = filter_results(run.photo_results, filter_type)

    if not filtered:
        raise HTTPException(status_code=404, detail='No photos match the filter.')

    if hash_query:
        for i, r in enumerate(filtered):
            if r.content_hash.startswith(hash_query):
                idx = i
                break

    idx = max(0, min(idx, len(filtered) - 1))

    photo_results_json = json.dumps([{
        'content_hash': r.content_hash,
        'expected_bibs': r.expected_bibs,
        'detected_bibs': r.detected_bibs,
        'tp': r.tp,
        'fp': r.fp,
        'fn': r.fn,
        'status': r.status,
        'detection_time_ms': r.detection_time_ms,
        'tags': r.tags,
        'artifact_paths': r.artifact_paths,
        'preprocess_metadata': r.preprocess_metadata,
    } for r in filtered])

    all_runs = list_runs()

    pipeline_summary = "unknown"
    passes_summary = "unknown"
    if run.metadata.pipeline_config:
        pipeline_summary = run.metadata.pipeline_config.summary()
    if run.metadata.face_pipeline_config:
        passes_summary = run.metadata.face_pipeline_config.summary_passes()

    return TEMPLATES.TemplateResponse(request, 'benchmark_inspect.html', {
        'run': run,
        'filtered_results': filtered,
        'current_idx': idx,
        'filter': filter_type,
        'photo_results_json': photo_results_json,
        'all_runs': all_runs,
        'pipeline_summary': pipeline_summary,
        'passes_summary': passes_summary,
    })


@ui_benchmark_router.get('/media/artifacts/{run_id}/{hash_prefix}/{image_type}')
async def serve_artifact(run_id: str, hash_prefix: str, image_type: str):
    """Serve artifact image from run directory."""
    artifact_dir = RESULTS_DIR / run_id / "images" / hash_prefix

    filename_map = {
        'original': 'original.jpg',
        'grayscale': 'grayscale.jpg',
        'clahe': 'clahe.jpg',
        'resize': 'resize.jpg',
        'candidates': 'candidates.jpg',
        'detections': 'detections.jpg',
    }

    filename = filename_map.get(image_type)
    if not filename:
        raise HTTPException(status_code=404)

    artifact_path = artifact_dir / filename
    if not artifact_path.exists():
        raise HTTPException(status_code=404)

    return FileResponse(artifact_path)
