# Labeling Guide

This guide is for human operators labeling photos in the benchmark UI. The labels build ground truth for a race photo retrieval system — they define what the detection pipeline *should* do. Wrong labels produce wrong benchmarks, so label what you see, not what you expect.

The labeling UI opens with `bnr benchmark ui`. Three independent labeling steps exist for each photo: bib labeling, face labeling, and link labeling.

---

## Face Labeling

**Core rule: label every face a human would recognise as a face — participants and bystanders alike.**

The face detector has no knowledge of who is a runner. It finds faces. If you skip a real face, the benchmark will not penalise the detector for missing it, which trains the system to miss faces. Bystanders are harmless: they are detected, never linked to a bib, and never returned in retrieval results.

### Ghost suggestions

When you open a photo, faint boxes appear automatically — these are pre-computed detection suggestions (ghosts). Your job is to:

- Accept correct ghosts by confirming them
- Adjust misplaced ghosts by dragging the box
- Reject false ghosts (not a face) by setting scope to `exclude`
- Draw new boxes for real faces the detector missed

### Scope

| Situation | Scope |
|-----------|-------|
| Realistic face, clearly visible — participant or bystander | `keep` |
| Face significantly clipped at the frame edge, or degraded enough that you are unsure whether the detector should find it | `uncertain` |
| Ghost suggestion that is not actually a face | `exclude` |

`keep` faces are scored in the benchmark. `uncertain` and `exclude` faces are not.

### Identity (for `keep` faces only)

| Situation | Identity |
|-----------|----------|
| You recognise the person | Enter their name |
| You do not recognise them but expect to see them again in other photos | Assign the next available `anonymous_N` |
| Genuinely one-off unknown — will not appear again | Leave as `null` |

`keep` + `null` contributes to face detection scoring but not to clustering or linking evaluation. That is intentional: `null` means the face is real but not worth tracking across photos.

`keep` + `anonymous_N` contributes to clustering evaluation — the system can be tested on whether it correctly groups all appearances of the same person.

### Identity on `uncertain` faces

You may sometimes be able to infer who a clipped or degraded face belongs to from context — a visible bib number, clothing, or race position. It is fine to set an identity on an `uncertain` face, but be aware of the effect:

- The `uncertain` scope excludes the face from detection scoring regardless of identity.
- The identity is only useful for clustering evaluation if the face was actually detected by the pipeline. If the detector missed it, the label is inert.
- If the detector did find the face, its embedding may be poor quality (the face is clipped or degraded). That embedding may not cluster reliably with the same person's good embeddings, which could create misleading clustering signal.

In short: identity on `uncertain` faces is harmless to keep, but do not expect it to contribute meaningful signal. The identity was inferred from context the embedder cannot see.

### Per-box tags (optional)

These do not affect scoring. Use them to annotate difficulty.

| Tag | When to use |
|-----|-------------|
| `tiny` | Face is very small in the frame |
| `blurry` | Motion blur or out of focus |
| `occluded` | Partially hidden by another person or object |
| `profile` | Significant side angle |
| `looking_down` | Face angled downward |

### Per-photo tags

| Tag | When to use |
|-----|-------------|
| `no_faces` | Photo has no faces at all |
| `light_faces` | Faces present but low contrast or faded |

---

## Bib Labeling

**Core rule: label bibs as a human reader would. Ask yourself: can I read the full number?**

### Decision guide

| Situation | Scope | Enter number? |
|-----------|-------|---------------|
| Complete, fully readable bib | `bib` | Yes |
| Top or bottom edge clipped, but the full number is still legible | `bib_clipped` | Yes |
| Side-clipped — part of the number is missing (e.g. `234` shows as `34`) | `bib_obscured` | No |
| Blurry, obscured, side-angle, or otherwise unreadable | `bib_obscured` | Optional — enter if you can read it, but it is not scored |
| Ghost suggestion that is not a real bib | `not_bib` | No |

`bib` and `bib_clipped` are scored. `bib_obscured` and `not_bib` are excluded from scoring.

### Clipping vs obscured

`bib_clipped` means the *image frame* cuts off part of the bib. Top or bottom clipping usually leaves the number legible — use `bib_clipped`. Side clipping cuts off digits: `234` becomes `34` and the system cannot know the leading digit is missing — use `bib_obscured`.

`bib_obscured` covers everything else that makes the number unreadable: a hand or arm in front of the bib, the runner shot from the side so the bib face is angled away, motion blur, or any other reason the digits cannot be read. Do not enter a number for `bib_obscured`.

### Partial numbers

If you can make out most of a number but not all of it, you may enter it with a `?` suffix (e.g. `62?`). Partial numbers are excluded from scoring but preserved as context.

---

## Link Labeling

Links connect a face box to the bib box of the same runner in the same photo. The link step is only available for photos that have both bib and face labels.

**When to link:**

- Both the face and the bib are clearly visible
- The pairing is unambiguous — you can see it is the same person

**When not to link:**

- The bib scope is `bib_obscured` — even if you can guess the number
- The face scope is `uncertain`
- You are not sure which bib belongs to which face

**Saving an empty link list (`[]`) is a valid outcome.** It means: reviewed — no valid links in this photo. This is different from not having visited the photo at all.

---

## Common Edge Cases

| Situation | Decision |
|-----------|----------|
| Bystander with a visible face | `keep` + `anonymous_N` or `null` — detect it, do not link it |
| Runner whose face is substantially clipped at the top of the frame | `uncertain` — skip if more than roughly half the face is outside the frame |
| Runner whose bib is behind another person | `bib_obscured` — no link |
| Auto-detected box on a race banner or finish-line sign | `not_bib` |
| Auto-detected box on a shadow or noise artefact | `exclude` |
| Two runners side by side, both bibs partially occluded | Label each separately; use `bib_obscured` only if digits are actually cut off |
| Same person appears in multiple photos | Use the same name or `anonymous_N` consistently across photos |

---

## Completeness

A photo is complete when all three dimensions are done:

- **Bib labeled** — you have saved bib labels (even if the result is zero boxes)
- **Face labeled** — you have saved face labels (even if the result is zero boxes, or you set a `no_faces` tag)
- **Links labeled** — you have saved a link list, or the photo has no bib boxes or no face boxes (link step is skipped automatically in that case)

The staging page (`/staging/`) shows completeness status for every photo. Only complete photos are included in a freeze by default.
