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

## Standards

Project-wide conventions live in `STANDARDS.md`.
