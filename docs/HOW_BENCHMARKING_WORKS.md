# How Benchmarking Works

## Stage 1: Detection

The bib detector processes each photo through a preprocessing pipeline (resize, grayscale, optionally CLAHE contrast enhancement). It then looks for white rectangular regions as bib candidates. Each candidate region is fed to the OCR engine (EasyOCR), which tries to read a number. The output is a list of predicted bib boxes, each with coordinates and a recognized number string.

Face detection works similarly but with different backends (OpenCV DNN, Haar cascades). Each backend proposes face candidate rectangles with a confidence score. Candidates below a threshold are rejected. The survivors become predicted face boxes.

## Stage 2: Scoring against ground truth labels

This is where IoU (Intersection over Union) comes in. It's a simple measure: take the overlapping area between a predicted box and a ground truth box, divide by the total area covered by both boxes combined. The result is a number between 0 (no overlap) and 1 (perfect overlap). A threshold of 0.5 means "at least half the area overlaps."

The matching algorithm pairs up predicted boxes with ground truth boxes:

1. Compute the IoU between every predicted box and every ground truth box — this gives a grid of overlap scores.
2. Greedily match pairs: take the highest IoU pair, assign it, remove both boxes from consideration, repeat. Only pairs above the 0.5 threshold qualify.
3. After matching: matched pairs are "detection true positives" (the detector found the region). Unmatched predicted boxes are "detection false positives." Unmatched ground truth boxes are "detection false negatives" (the detector missed the region entirely).

For bibs specifically, there's a second check on matched pairs: did the OCR read the correct number? A matched pair where the predicted number equals the ground truth number is an "OCR correct." A matched pair with the wrong number means the detector found the bib but OCR failed.

## What exists today vs. what's missing

The **number-matching** on PhotoResult today skips all of this geometry. It just asks: "is 415 in the expected set AND in the detected set?" This usually gives the same answer, but it can't tell you *why* a bib was missed.

The **IoU scoring** (`score_bibs`, `score_faces`) does the full geometric matching described above — but only keeps the aggregate totals across all photos. The per-photo breakdown (which would tell you "on this specific photo, the detector found 2 of 3 bib regions, and OCR got both numbers right") is computed and then thrown away. Task-061 fixes this by persisting per-photo scorecards on PhotoResult.
