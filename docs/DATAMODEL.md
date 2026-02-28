# Data Model

Entity-relationship diagram showing the target state after task-044 (Photo entity) and task-046 (frozen enforcement).

## ERD

```
┌─────────────────────────────────────────────────────────────────┐
│                        photo_metadata.json                      │
│                                                                 │
│  ┌─────────────────────────────────────┐                        │
│  │         PhotoMetadata               │                        │
│  │─────────────────────────────────────│                        │
│  │  content_hash  PK   (64-char SHA)   │                        │
│  │  paths         list[str]            │                        │
│  │  split         str (iteration|full) │                        │
│  │  bib_tags      list[str]            │                        │
│  │  face_tags     list[str]            │                        │
│  │  frozen        str | None  (046)    │                        │
│  └──────────┬──────────────────────────┘                        │
└─────────────┼───────────────────────────────────────────────────┘
              │
              │ 1:1 by content_hash
              │
     ┌────────┼────────┬──────────────────┐
     │        │        │                  │
     ▼        ▼        ▼                  ▼
┌─────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────────┐
│ bib GT  │ │ face GT  │ │ link GT    │ │ face_identities.json │
└────┬────┘ └────┬─────┘ └─────┬──────┘ └──────────┬───────────┘
     │           │             │                    │
     ▼           ▼             ▼                    ▼
┌──────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────────┐
│BibPhoto  │ │FacePhoto  │ │BibFace    │ │Identity            │
│Label     │ │Label      │ │Link       │ │────────────────────│
│──────────│ │───────────│ │───────────│ │ name    str        │
│hash   PK │ │hash    PK │ │hash    FK │ │ (e.g. "Lasse",    │
│boxes  1:N│ │boxes   1:N│ │bib_idx FK │ │  "anon-3")        │
│labeled   │ │labeled    │ │face_idx FK│ └────────────────────┘
└────┬─────┘ └────┬─────┘ └───────────┘          ▲
     │            │          │     │               │
     ▼            ▼          │     │               │
┌──────────┐ ┌───────────┐  │     │               │
│BibBox    │ │FaceBox    │  │     │               │
│──────────│ │───────────│  │     │               │
│x,y,w,h  │ │x,y,w,h   │  │     │    references │
│number str│ │scope      │◄─┘     │               │
│scope     │ │identity   │────────────────────────┘
│          │ │tags[]     │◄───────┘
└──────────┘ └───────────┘
  ▲               ▲
  │    indexes    │
  └───────┬───────┘
          │
┌─────────┴──────────────────────────────────────────────────────┐
│                      frozen/<name>/                             │
│                                                                 │
│  ┌─────────────────────────────────────┐                        │
│  │      BenchmarkSnapshot              │                        │
│  │─────────────────────────────────────│                        │
│  │  name          str                  │                        │
│  │  created_at    ISO 8601             │                        │
│  │  photo_count   int                  │                        │
│  │  description   str                  │                        │
│  │  hashes        list[content_hash]   │  (listing/discovery)   │
│  └─────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

## Relationships

| From | To | Cardinality | Via |
|------|-----|------------|-----|
| PhotoMetadata | BibPhotoLabel | 1 : 0..1 | content_hash |
| PhotoMetadata | FacePhotoLabel | 1 : 0..1 | content_hash |
| PhotoMetadata | BibFaceLink | 1 : 0..N | content_hash |
| BibPhotoLabel | BibBox | 1 : N | boxes[] index |
| FacePhotoLabel | FaceBox | 1 : N | boxes[] index |
| BibFaceLink | BibBox | N : 1 | bib_index → boxes[] |
| BibFaceLink | FaceBox | N : 1 | face_index → boxes[] |
| FaceBox | Identity | N : 1 | identity (name string) |
| BenchmarkSnapshot | PhotoMetadata | N : N | hashes[] (but `frozen` field makes it effectively N:1) |

## Files on disk

| File | Contains |
|------|----------|
| `photo_metadata.json` | PhotoMetadata per hash (paths, split, tags, frozen) |
| `bib_ground_truth.json` | BibPhotoLabel per hash (boxes, labeled) |
| `face_ground_truth.json` | FacePhotoLabel per hash (boxes, labeled) |
| `bib_face_links.json` | BibFaceLink lists per hash |
| `face_identities.json` | Identity name list |
| `frozen/<name>/metadata.json` | Snapshot metadata (for listing) |
