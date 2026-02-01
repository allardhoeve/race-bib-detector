# TODO

## Completed

1. ~~Create preprocessing module skeleton~~ DONE
   [x] Create a preprocessing/ module with pure, deterministic functions (no global state).
   [x] Document your philosophy and guidance (below) in STRUCTURE.md and PREPROCESSING.md.
   [x] Define a single PreprocessConfig object (or dict) that parameterizes all steps.
   [x] Define a run_pipeline(img, config) function that applies steps in order.

2. ~~Implement image-level normalization~~ DONE
   [x] Implement to_grayscale(img).
   [x] Implement resize_to_width(img, width) (preserve aspect ratio).
   [x] Add unit tests for grayscale + resize (shape, dtype, aspect ratio).
   [x] PreprocessResult includes scale_factor for coordinate mapping back to original.
   [x] Documentation in STRUCTURE.md and PREPROCESSING.md.

3. ~~Integrate preprocessing into scan_album.py~~ DONE
   [x] Call run_pipeline() before OCR detection
   [x] Save preprocessed images (grayscale, resized) with linked filenames
   [x] Use coordinate mapping to convert detections back to original coordinates
   [x] Display grayscale with bounding boxes in web interface (new "Grayscale" tab)

## In Progress

[ ] There are a lot of hard-coded values, like the minimum median brightness and such. Move all functional values into a central global variable file so they are easily tweaked. Use all caps for globals and use descriptive names.



### Improve bib detection filtering
# - [ ] Take a new approach to the bib detection. 1. Take all the squares that look like bibs. These are white squares. 
#      There can be multiple. Make these into snippets. Disregard all boxes that contain text that do not look like 
#      bibs. This prevents things like numbers on helmets, like in photo 7286de68 (make this a test). Detect a single (!)
#      number in each bib snippet. This is the largest number we can find. 
# - [ ] Clean up any unused code that was used in the previous way of detecting bibs.
# - [ ] Try to make methods shorter. Some methods have a large number of branches. Things will get more maintainable and
#      more readable if the methods are shorter.
# - [ ] Use tricks like increasing the contrast on each bib snippet to get to better results. Ideas are in "IDEAS.md".

## Backlog

### Explore facial recognition for photo grouping
See IDEAS.md for exploration notes.
