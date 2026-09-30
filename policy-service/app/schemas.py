from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class InternalAnswerRequest(BaseModel):
    tenant: str
    role: str
    as_of: date
    question: str = Field(min_length=1)


class CitationOut(BaseModel):
    chunk_id: str
    quote: str


class InternalAnswerResponse(BaseModel):
    status: str
    answer: Optional[str]
    citations: List[CitationOut]


class ManifestEntryIn(BaseModel):
    document_id: str
    filename: str


class BatchMetadataIn(BaseModel):
    batch_id: str
    tenant: str
    role: str
    as_of: date
    documents: List[ManifestEntryIn]
