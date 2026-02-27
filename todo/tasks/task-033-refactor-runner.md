# Task NNN: <short title>

This is a standalone task.

## Goal

Runner.py is 1000 lines, most of which is dataclasses. This is too long.

## Background

Runner.py is getting unreadable.

## Context

Runner.py is a collection of dataclasses. They repeat so much boilerplate. I feel like this is not always
necessary:

```python
    @classmethod
    def from_dict(cls, data: dict) -> "FacePipelineConfig":
        return cls(
            face_backend=data.get("face_backend", "unknown"),
            dnn_confidence_min=data.get("dnn_confidence_min", 0.0),
            dnn_fallback_confidence_min=data.get("dnn_fallback_confidence_min", 0.0),
            dnn_fallback_max=data.get("dnn_fallback_max", 0),
            fallback_backend=data.get("fallback_backend"),
            fallback_min_face_count=data.get("fallback_min_face_count", 0),
            fallback_max=data.get("fallback_max", 0),
            fallback_iou_threshold=data.get("fallback_iou_threshold", 0.0),
        )
```

Most platforms give a way of doing this in other ways. Also the `to_dict` function seem boilerplate.


RunMetaData is obscure. THe config generation is too many branches deep and opaque. 

```python
    @classmethod
    def from_dict(cls, data: dict) -> RunMetadata:
        pipeline_config = None
        if "pipeline_config" in data:
            pipeline_config = PipelineConfig.from_dict(data["pipeline_config"])
        face_pipeline_config = None
        if "face_pipeline_config" in data:
            face_pipeline_config = FacePipelineConfig.from_dict(data["face_pipeline_config"])
        return cls(
            run_id=data.get("run_id", "unknown"),
            timestamp=data["timestamp"],
```


The function `run_detection_loop` is too long with too many branches. The code is obscure and has no in-line 
documentation on what the code does. This combined with terse variable names make it hard to understand as a human.


```python
        if face_backend is not None and face_gt is not None:
            photo_face_label = face_gt.get_photo(label.content_hash)
            gt_face_boxes = photo_face_label.boxes if photo_face_label else []
            img_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            if img_array is not None:
                image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                face_h, face_w = image_rgb.shape[:2]
                face_candidates = face_backend.detect_face_candidates(image_rgb)
                pred_face_boxes: list[FaceBox] = []
                for cand in face_candidates:
                    if not cand.passed:
                        continue
                    x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
                    pred_face_boxes.append(FaceBox(
                        x=x1 / face_w, y=y1 / face_h,
                        w=(x2 - x1) / face_w, h=(y2 - y1) / face_h,
                    ))
                photo_face_sc = score_faces(pred_face_boxes, gt_face_boxes)
                face_det_tp += photo_face_sc.detection_tp
                face_det_fp += photo_face_sc.detection_fp
                face_det_fn += photo_face_sc.detection_fn
```


## Tasks

* Split functions into well-named parts
* Add selected in-line comments on what certain complicated things do
* Add docstrings to functions that are more involved that explain the control flow, the intent and the constraints
* Check if all tests are accounted for.
* This wasn't written with TDD, that is clear. If you split out functions, build them with red/green TDD.