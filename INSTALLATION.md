# Installation

This project expects a local Python virtual environment and a few third-party
assets that are not committed to the repository.

## Python Environment

1. Create a virtual environment.
2. Install dependencies with the venv executables.

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
```

## OpenCV DNN Face Model Files

The OpenCV DNN SSD face detector model files are intentionally ignored by git.
Download them from the official OpenCV sources and place them here:

- `faces/models/opencv_dnn_ssd/deploy.prototxt`
- `faces/models/opencv_dnn_ssd/res10_300x300_ssd_iter_140000.caffemodel`

If you store them elsewhere, update the paths in `config.py`:

- `FACE_DNN_PROTO_PATH`
- `FACE_DNN_MODEL_PATH`

## Face Backend Options

Face detection uses a configurable primary backend plus an optional fallback
backend for low face counts. Configure these in `config.py`:

- `FACE_BACKEND`: Primary detector backend (default: `opencv_dnn_ssd`).
- `FACE_FALLBACK_BACKEND`: Optional fallback backend (default: `opencv_haar`).
  Set to an empty string to disable fallback entirely for a run.
- `FACE_FALLBACK_MIN_FACE_COUNT`: Minimum faces required before triggering
  fallback.
- `FACE_FALLBACK_MAX`: Max additional faces to accept from fallback.
- `FACE_FALLBACK_IOU_THRESHOLD`: IoU threshold for de-duplicating fallback
  boxes against primary detections.

Benchmark metadata records the face backend configuration so you can compare
runs and see whether fallback passes were enabled.

Fallback runs only when the primary backend returns fewer than the minimum
face count, so it can recover missed faces without impacting cases that are
already strong.

## Standards

Project-wide conventions live in `STANDARDS.md`.
