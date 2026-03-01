/**
 * Canvas overlay for benchmark inspect page (task-053).
 *
 * Draws predicted and ground-truth bounding boxes over the photo image,
 * colour-coded by type (bib/face) and match status (TP/FP/FN).
 * Also draws link lines connecting linked bib↔face GT pairs.
 */

class InspectOverlay {
  constructor(imgEl, canvasEl) {
    this.img = imgEl;
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext('2d');
    this.photoData = null;
    this.options = {
      showBibBoxes: true,
      showFaceBoxes: true,
      showGT: true,
      showPred: true,
      showLinks: true,
    };
    this._setupResize();
  }

  _setupResize() {
    const ro = new ResizeObserver(() => this.draw());
    ro.observe(this.img);
    this.img.addEventListener('load', () => this.draw());
  }

  setPhotoData(data) {
    this.photoData = data;
    this.draw();
  }

  draw() {
    const w = this.img.clientWidth;
    const h = this.img.clientHeight;
    if (w === 0 || h === 0) return;

    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx.clearRect(0, 0, w, h);

    const data = this.photoData;
    if (!data) return;

    // Draw GT boxes (dashed)
    if (this.options.showGT) {
      if (this.options.showBibBoxes && data.gt_bib_boxes) {
        for (const box of data.gt_bib_boxes) {
          this._drawBox(box, w, h, '#3b82f6', true, box.number || '', box.scope);
        }
      }
      if (this.options.showFaceBoxes && data.gt_face_boxes) {
        for (const box of data.gt_face_boxes) {
          const label = box.identity || '';
          this._drawBox(box, w, h, '#8b5cf6', true, label, box.scope);
        }
      }
    }

    // Draw prediction boxes (solid)
    if (this.options.showPred) {
      if (this.options.showBibBoxes && data.pred_bib_boxes) {
        for (const box of data.pred_bib_boxes) {
          const num = parseInt(box.number);
          const isTP = !isNaN(num) && data.expected_bibs.includes(num);
          const color = isTP ? '#22c55e' : '#ef4444';
          this._drawBox(box, w, h, color, false, box.number || '');
        }
      }
      if (this.options.showFaceBoxes && data.pred_face_boxes) {
        for (const box of data.pred_face_boxes) {
          const label = box.cluster_id != null ? `c${box.cluster_id}` : '';
          this._drawBox(box, w, h, '#14b8a6', false, label);
        }
      }
    }

    // Draw link lines
    if (this.options.showLinks && data.gt_links && data.gt_bib_boxes && data.gt_face_boxes) {
      this._drawLinks(data.gt_links, data.gt_bib_boxes, data.gt_face_boxes, w, h);
    }
  }

  _drawBox(box, imgW, imgH, color, dashed, label, scope) {
    if (box.x == null || box.y == null || box.w == null || box.h == null) return;

    const ctx = this.ctx;
    const x = box.x * imgW;
    const y = box.y * imgH;
    const bw = box.w * imgW;
    const bh = box.h * imgH;

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash(dashed ? [6, 3] : []);
    ctx.strokeRect(x, y, bw, bh);

    // Draw label background + text above box
    const parts = [];
    if (label) parts.push(label);
    if (scope && scope !== 'bib' && scope !== 'keep') parts.push(scope);
    const text = parts.join(' ');

    if (text) {
      ctx.font = '11px monospace';
      const textW = ctx.measureText(text).width + 6;
      const textH = 15;
      const labelY = y - textH;
      const drawY = labelY < 0 ? y : labelY;

      ctx.fillStyle = color;
      ctx.globalAlpha = 0.85;
      ctx.fillRect(x, drawY, textW, textH);
      ctx.globalAlpha = 1.0;

      ctx.fillStyle = '#fff';
      ctx.fillText(text, x + 3, drawY + 11);
    }
    ctx.setLineDash([]);
  }

  _drawLinks(links, bibBoxes, faceBoxes, imgW, imgH) {
    const ctx = this.ctx;
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.globalAlpha = 0.7;

    for (const link of links) {
      const bib = bibBoxes[link.bib_index];
      const face = faceBoxes[link.face_index];
      if (!bib || !face) continue;
      if (bib.x == null || face.x == null) continue;

      // Center of each box
      const bx = (bib.x + bib.w / 2) * imgW;
      const by = (bib.y + bib.h / 2) * imgH;
      const fx = (face.x + face.w / 2) * imgW;
      const fy = (face.y + face.h / 2) * imgH;

      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.lineTo(fx, fy);
      ctx.stroke();
    }
    ctx.globalAlpha = 1.0;
    ctx.setLineDash([]);
  }
}
