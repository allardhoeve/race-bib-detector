# CLAHE TODOs

- Validate CLAHE against benchmark `d19c3ebe` and record precision/recall deltas
- Check whether CLAHE introduces new false positives in high-contrast scenes
- Tune `clahe_dynamic_range_threshold` and `clahe_clip_limit` for best trade-off
- Explore a bib aspect-ratio/geometry filter to suppress partial-digit matches
- Re-evaluate placement (before vs after resize) if accuracy or speed is poor
- Decide when to flip `clahe_enabled` to default on
