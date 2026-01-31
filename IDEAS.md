# Ideas

## Facial Recognition for Photo Grouping

**Status:** To explore

**Problem it solves:**
Instead of relying solely on OCR to detect bib numbers (which can misread), we could use facial recognition to group photos of the same person together. If we correctly identify one bib for a person, all their photos get tagged with that bib.

**Potential approach:**
1. Extract faces from all photos using a face detection model
2. Generate face embeddings (vector representations)
3. Cluster similar faces together
4. For each cluster, if any photo has a confident bib detection, apply that bib to all photos in the cluster
5. This provides redundancy - even if OCR fails on some photos, the face grouping carries the bib forward

**Libraries to explore:**
- `face_recognition` (dlib-based, easy to use)
- `deepface` (multiple backends: VGG-Face, Facenet, OpenFace, etc.)
- `insightface` (state-of-the-art accuracy)

**Considerations:**
- Privacy implications of storing face embeddings
- Performance on race photos (motion blur, sunglasses, helmets, varied angles)
- Multiple people in same photo
- Same person may have different bibs in different races (if album spans multiple events)

**Next steps:**
- [ ] Test face detection accuracy on sample race photos
- [ ] Evaluate clustering quality
- [ ] Design data model for face embeddings and clusters
