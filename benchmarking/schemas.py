"""Pydantic schemas for API request bodies and response models.

Domain model classes (BibBox, FaceBox, etc.) live in ground_truth.py.
These schemas define the exact wire format accepted / returned by each endpoint.
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Bib boxes
# ---------------------------------------------------------------------------

class BibBoxIn(BaseModel):
    """Input shape for a single bib box (from the labeling UI)."""
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"


class SaveBibBoxesRequest(BaseModel):
    """Body for PUT /api/bibs/{hash}."""
    boxes: list[BibBoxIn] | None = None  # None = absent (fall through to bibs legacy path)
    bibs: list[int] | None = None  # legacy int-list format
    tags: list[str] = Field(default_factory=list)
    split: str = "full"


class BibBoxOut(BaseModel):
    """Output shape for a single bib box."""
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"


class BibSuggestionOut(BaseModel):
    """Output shape for a single bib ghost suggestion."""
    x: float
    y: float
    w: float
    h: float
    number: str
    confidence: float


class GetBibBoxesResponse(BaseModel):
    """Response for GET /api/bibs/{hash}."""
    boxes: list[BibBoxOut]
    suggestions: list[BibSuggestionOut] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    split: str
    labeled: bool


# ---------------------------------------------------------------------------
# Face boxes
# ---------------------------------------------------------------------------

class FaceBoxIn(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str = "keep"
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)


class SaveFaceBoxesRequest(BaseModel):
    """Body for PUT /api/faces/{hash}."""
    boxes: list[FaceBoxIn] = Field(default_factory=list)
    face_tags: list[str] = Field(default_factory=list)  # photo-level tags


class FaceBoxOut(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)


class FaceSuggestionOut(BaseModel):
    """Output shape for a single face ghost suggestion."""
    x: float
    y: float
    w: float
    h: float
    confidence: float


class GetFaceBoxesResponse(BaseModel):
    """Response for GET /api/faces/{hash}."""
    boxes: list[FaceBoxOut]
    suggestions: list[FaceSuggestionOut] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------


class IdentityMatchOut(BaseModel):
    """Output shape for a single identity suggestion."""
    identity: str
    similarity: float
    content_hash: str
    box_index: int
    samples: list[dict] = Field(default_factory=list)


class IdentitySuggestionsResponse(BaseModel):
    """Response for GET /api/faces/{hash}/suggestions."""
    suggestions: list[IdentityMatchOut]


class IdentitiesResponse(BaseModel):
    identities: list[str]


class CreateIdentityRequest(BaseModel):
    name: str


class PatchIdentityRequest(BaseModel):
    """Body for PATCH /api/identities/{name}."""
    new_name: str


class PatchIdentityResponse(BaseModel):
    updated_count: int
    identities: list[str]


# ---------------------------------------------------------------------------
# Associations (bib-face links)
# ---------------------------------------------------------------------------

class SaveAssociationsRequest(BaseModel):
    """Body for PUT /api/associations/{hash}."""
    links: list[list[int]] = Field(default_factory=list)


class AssociationsResponse(BaseModel):
    links: list[list[int]]


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------

class FreezeRequest(BaseModel):
    """Body for POST /api/freeze."""
    name: str
    hashes: list[str]
    description: str = ""


class FreezeResponse(BaseModel):
    name: str
    created_at: str
    photo_count: int
    description: str = ""
