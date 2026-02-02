#!/usr/bin/env python3
"""Benchmark the image processing pipeline to identify bottlenecks.

Usage:
    venv/bin/python benchmark.py /path/to/images [--limit N]
"""

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import easyocr
import numpy as np
from PIL import Image

from detection import detect_bib_numbers, find_bib_candidates
from preprocessing import run_pipeline, PreprocessConfig
from sources import scan_local_images


@dataclass
class TimingStats:
    """Accumulated timing statistics."""
    image_load: list[float] = field(default_factory=list)
    preprocessing: list[float] = field(default_factory=list)
    region_detection: list[float] = field(default_factory=list)
    ocr: list[float] = field(default_factory=list)
    total: list[float] = field(default_factory=list)

    def add(self, stage: str, duration: float):
        getattr(self, stage).append(duration)

    def summary(self) -> dict:
        """Calculate summary statistics."""
        result = {}
        for stage in ['image_load', 'preprocessing', 'region_detection', 'ocr', 'total']:
            times = getattr(self, stage)
            if times:
                result[stage] = {
                    'mean': sum(times) / len(times),
                    'min': min(times),
                    'max': max(times),
                    'total': sum(times),
                    'count': len(times),
                }
        return result


def benchmark_image(image_path: Path, reader: easyocr.Reader, config: PreprocessConfig) -> dict:
    """Benchmark processing of a single image, returning timing for each stage."""
    timings = {}

    # Stage 1: Image load
    t0 = time.perf_counter()
    image_data = image_path.read_bytes()
    image = Image.open(image_path)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image_array = np.array(image)
    timings['image_load'] = time.perf_counter() - t0

    # Stage 2: Preprocessing
    t0 = time.perf_counter()
    preprocess_result = run_pipeline(image_array, config)
    if preprocess_result.resized is not None:
        ocr_image = preprocess_result.resized
    else:
        ocr_image = image_array
    timings['preprocessing'] = time.perf_counter() - t0

    # Stage 3: Region detection
    t0 = time.perf_counter()
    bib_candidates = find_bib_candidates(ocr_image)
    timings['region_detection'] = time.perf_counter() - t0

    # Stage 4: OCR (the main suspect)
    t0 = time.perf_counter()

    # OCR on candidate regions
    for candidate in bib_candidates:
        region = candidate.extract_region(ocr_image)
        reader.readtext(region)

    # OCR on full image (fallback)
    reader.readtext(ocr_image)

    timings['ocr'] = time.perf_counter() - t0

    # Total
    timings['total'] = sum(timings.values())

    return timings


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 0.001:
        return f"{seconds * 1000000:.0f}µs"
    elif seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    else:
        return f"{seconds:.2f}s"


def print_summary(stats: TimingStats, num_images: int):
    """Print a formatted summary of timing statistics."""
    summary = stats.summary()

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Images processed: {num_images}")
    print()

    # Table header
    print(f"{'Stage':<20} {'Mean':>10} {'Min':>10} {'Max':>10} {'Total':>10} {'%':>6}")
    print("-" * 60)

    total_time = summary.get('total', {}).get('total', 1)

    for stage in ['image_load', 'preprocessing', 'region_detection', 'ocr']:
        if stage in summary:
            s = summary[stage]
            pct = (s['total'] / total_time) * 100
            print(f"{stage:<20} {format_duration(s['mean']):>10} {format_duration(s['min']):>10} {format_duration(s['max']):>10} {format_duration(s['total']):>10} {pct:>5.1f}%")

    print("-" * 60)
    if 'total' in summary:
        s = summary['total']
        print(f"{'TOTAL':<20} {format_duration(s['mean']):>10} {format_duration(s['min']):>10} {format_duration(s['max']):>10} {format_duration(s['total']):>10} {'100.0':>5}%")

    print()
    print("Throughput: {:.2f} images/sec".format(num_images / summary['total']['total']))

    # Analysis
    print()
    print("ANALYSIS")
    print("-" * 60)

    # Find bottleneck
    stages = ['image_load', 'preprocessing', 'region_detection', 'ocr']
    bottleneck = max(stages, key=lambda s: summary.get(s, {}).get('total', 0))
    bottleneck_pct = (summary[bottleneck]['total'] / total_time) * 100

    print(f"Bottleneck: {bottleneck} ({bottleneck_pct:.1f}% of time)")

    if bottleneck == 'ocr':
        print()
        print("Recommendations:")
        print("  - Parallelization with --workers would help (OCR is CPU-bound)")
        print("  - With 4 workers, expect ~3-4x speedup")
        print("  - GPU acceleration (if available) could give 5-10x speedup")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark the image processing pipeline"
    )
    parser.add_argument(
        "directory",
        help="Path to directory containing images"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=10,
        help="Number of images to benchmark (default: 10)"
    )

    args = parser.parse_args()

    # Find images
    try:
        image_files = scan_local_images(args.directory)
    except ValueError as e:
        print(f"Error: {e}")
        return

    if not image_files:
        print("No images found.")
        return

    # Apply limit
    image_files = image_files[:args.limit]
    print(f"Benchmarking {len(image_files)} images from {args.directory}")

    # Initialize
    print("Initializing EasyOCR (this takes a few seconds)...")
    t0 = time.perf_counter()
    reader = easyocr.Reader(["en"], gpu=False)
    init_time = time.perf_counter() - t0
    print(f"EasyOCR initialized in {format_duration(init_time)}")

    config = PreprocessConfig(target_width=1280)
    stats = TimingStats()

    # Benchmark each image
    print()
    print("Processing images...")
    for i, image_path in enumerate(image_files):
        print(f"  [{i+1}/{len(image_files)}] {image_path.name}", end="", flush=True)

        try:
            timings = benchmark_image(image_path, reader, config)
            for stage, duration in timings.items():
                stats.add(stage, duration)
            print(f" - {format_duration(timings['total'])}")
        except Exception as e:
            print(f" - ERROR: {e}")

    # Print summary
    print_summary(stats, len(image_files))

    # Parallel testing hint
    if len(image_files) >= 4:
        print()
        print("To test parallel speedup, use scan_album.py with --workers:")
        print(f"  time venv/bin/python scan_album.py {args.directory} --limit {len(image_files)} --rescan -w 1")
        print(f"  time venv/bin/python scan_album.py {args.directory} --limit {len(image_files)} --rescan -w 4")


if __name__ == "__main__":
    main()
