/**
 * Node.js unit tests for LabelingCore (pure logic, no DOM).
 *
 * Run with: node --test tests/test_labeling.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const { LabelingCore: C } = require('../benchmarking/static/labeling.js');

// A sample "image rect" representing an image rendered at 100x100 px
// offset by (50, 25) within a canvas.
const IMG_RECT = { x: 50, y: 25, w: 100, h: 100 };

// --- Coordinate conversion ---

describe('normalToCanvas', () => {
    it('maps (0, 0) to image origin', () => {
        const p = C.normalToCanvas(0, 0, IMG_RECT);
        assert.equal(p.x, 50);
        assert.equal(p.y, 25);
    });

    it('maps (1, 1) to image bottom-right', () => {
        const p = C.normalToCanvas(1, 1, IMG_RECT);
        assert.equal(p.x, 150);
        assert.equal(p.y, 125);
    });

    it('maps (0.5, 0.5) to image centre', () => {
        const p = C.normalToCanvas(0.5, 0.5, IMG_RECT);
        assert.equal(p.x, 100);
        assert.equal(p.y, 75);
    });
});

describe('canvasToNormal', () => {
    it('maps image origin to (0, 0)', () => {
        const n = C.canvasToNormal(50, 25, IMG_RECT);
        assert.equal(n.x, 0);
        assert.equal(n.y, 0);
    });

    it('maps image bottom-right to (1, 1)', () => {
        const n = C.canvasToNormal(150, 125, IMG_RECT);
        assert.equal(n.x, 1);
        assert.equal(n.y, 1);
    });

    it('round-trips correctly', () => {
        const nx = 0.3, ny = 0.7;
        const c = C.normalToCanvas(nx, ny, IMG_RECT);
        const n = C.canvasToNormal(c.x, c.y, IMG_RECT);
        assert.ok(Math.abs(n.x - nx) < 1e-10);
        assert.ok(Math.abs(n.y - ny) < 1e-10);
    });
});

// --- Hit testing ---

describe('hitTestBox', () => {
    const box = { x: 0.2, y: 0.3, w: 0.4, h: 0.3 };

    it('returns true for point inside box', () => {
        // Centre of box in canvas coords
        const cx = 50 + 0.4 * 100; // 90
        const cy = 25 + 0.45 * 100; // 70
        assert.ok(C.hitTestBox(cx, cy, box, IMG_RECT));
    });

    it('returns false for point outside box', () => {
        assert.ok(!C.hitTestBox(0, 0, box, IMG_RECT));
    });

    it('returns true on box edge', () => {
        const cx = 50 + 0.2 * 100; // left edge
        const cy = 25 + 0.3 * 100; // top edge
        assert.ok(C.hitTestBox(cx, cy, box, IMG_RECT));
    });
});

describe('hitTestHandle', () => {
    const box = { x: 0.2, y: 0.2, w: 0.6, h: 0.6 };

    it('returns handle index for TL corner', () => {
        // TL handle is at normalToCanvas(0.2, 0.2)
        const p = C.normalToCanvas(0.2, 0.2, IMG_RECT);
        assert.equal(C.hitTestHandle(p.x, p.y, box, IMG_RECT), 0);
    });

    it('returns -1 for miss', () => {
        assert.equal(C.hitTestHandle(0, 0, box, IMG_RECT), -1);
    });

    it('returns BR handle (index 2)', () => {
        const p = C.normalToCanvas(0.8, 0.8, IMG_RECT);
        assert.equal(C.hitTestHandle(p.x, p.y, box, IMG_RECT), 2);
    });
});

// --- Box model operations ---

describe('meetsMinSize', () => {
    it('accepts box larger than minimum', () => {
        const box = { x: 0, y: 0, w: 0.2, h: 0.2 };
        assert.ok(C.meetsMinSize(box, IMG_RECT)); // 20px > 10px
    });

    it('rejects box smaller than minimum', () => {
        const box = { x: 0, y: 0, w: 0.05, h: 0.05 };
        assert.ok(!C.meetsMinSize(box, IMG_RECT)); // 5px < 10px
    });
});

describe('computeIoU', () => {
    it('returns 1 for identical boxes', () => {
        const box = { x: 0.1, y: 0.1, w: 0.3, h: 0.3 };
        assert.ok(Math.abs(C.computeIoU(box, box) - 1) < 1e-10);
    });

    it('returns 0 for non-overlapping boxes', () => {
        const a = { x: 0.0, y: 0.0, w: 0.1, h: 0.1 };
        const b = { x: 0.5, y: 0.5, w: 0.1, h: 0.1 };
        assert.equal(C.computeIoU(a, b), 0);
    });

    it('returns correct IoU for partial overlap', () => {
        const a = { x: 0, y: 0, w: 0.2, h: 0.2 };
        const b = { x: 0.1, y: 0.1, w: 0.2, h: 0.2 };
        // Intersection: 0.1*0.1 = 0.01; Union: 0.04 + 0.04 - 0.01 = 0.07
        const iou = C.computeIoU(a, b);
        assert.ok(Math.abs(iou - 0.01 / 0.07) < 1e-10);
    });
});

describe('suggestionOverlaps', () => {
    it('returns false for no existing boxes', () => {
        const sugg = { x: 0.1, y: 0.1, w: 0.2, h: 0.2 };
        assert.ok(!C.suggestionOverlaps(sugg, []));
    });

    it('returns true when suggestion overlaps existing box', () => {
        const sugg = { x: 0.1, y: 0.1, w: 0.3, h: 0.3 };
        const boxes = [{ x: 0.1, y: 0.1, w: 0.3, h: 0.3 }];
        assert.ok(C.suggestionOverlaps(sugg, boxes));
    });
});

describe('applyHandleDrag', () => {
    const box = { x: 0.2, y: 0.2, w: 0.4, h: 0.4 };

    it('moves TL corner', () => {
        const result = C.applyHandleDrag(box, 0, 0.1, 0.1);
        assert.ok(Math.abs(result.x - 0.1) < 1e-10);
        assert.ok(Math.abs(result.y - 0.1) < 1e-10);
        assert.ok(Math.abs(result.w - 0.5) < 1e-10);
        assert.ok(Math.abs(result.h - 0.5) < 1e-10);
    });

    it('swaps when dragged past opposite edge', () => {
        const result = C.applyHandleDrag(box, 0, 0.8, 0.8);
        // TL dragged to (0.8, 0.8), past BR at (0.6, 0.6) → swap
        assert.ok(result.w > 0);
        assert.ok(result.h > 0);
    });
});

describe('moveBox', () => {
    it('moves box by delta', () => {
        const box = { x: 0.2, y: 0.3, w: 0.1, h: 0.1 };
        const result = C.moveBox(box, 0.1, 0.05);
        assert.ok(Math.abs(result.x - 0.3) < 1e-10);
        assert.ok(Math.abs(result.y - 0.35) < 1e-10);
    });

    it('clamps to image bounds', () => {
        const box = { x: 0.8, y: 0.8, w: 0.2, h: 0.2 };
        const result = C.moveBox(box, 0.5, 0.5);
        assert.ok(result.x + result.w <= 1.0 + 1e-10);
        assert.ok(result.y + result.h <= 1.0 + 1e-10);
    });
});

describe('clampNormal', () => {
    it('clamps below 0', () => {
        assert.equal(C.clampNormal(-0.5), 0);
    });

    it('clamps above 1', () => {
        assert.equal(C.clampNormal(1.5), 1);
    });

    it('passes through valid values', () => {
        assert.equal(C.clampNormal(0.5), 0.5);
    });
});
