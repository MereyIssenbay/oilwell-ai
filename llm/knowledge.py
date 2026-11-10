"""Small reviewed local retrieval corpus; no runtime web crawling or embeddings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from llm.schemas import Source

CATALOG_SHA256 = "a82b1d4b841a9008cfe8d2264e6355b167654069c8ed1fc1c2a065f331c2f711"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class KnowledgeBase:
    def __init__(self, path: Path | None = None):
        path = path or Path(__file__).parent / "knowledge" / "sources.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.sources = tuple(Source.model_validate(x) for x in payload["sources"])
        if digest([x.model_dump() for x in self.sources]) != CATALOG_SHA256:
            raise ValueError("Unreviewed knowledge catalog")
        if not self.sources or len({x.source_id for x in self.sources}) != len(self.sources):
            raise ValueError("Invalid knowledge source identity")
        for source in self.sources:
            if hashlib.sha256(source.content.encode()).hexdigest() != source.content_sha256:
                raise ValueError("Knowledge content checksum mismatch")
        self.version = "curated-1.0.0:" + digest([x.model_dump() for x in self.sources])

    def list_sources(self) -> list[Source]:
        return list(self.sources)

    def get_source(self, source_id: str) -> Source:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def retrieve(self, query: str, limit: int = 3) -> list[Source]:
        """Bounded deterministic lexical overlap, stable source-ID tie breaking."""
        words = set(re.findall(r"[a-z]{3,}", query.lower()))
        scored = [(len(words & set(re.findall(r"[a-z]{3,}", (s.title + " " + s.content).lower()))), s)
                  for s in self.sources]
        return [s for score, s in sorted(scored, key=lambda x: (-x[0], x[1].source_id))[:max(0, min(limit, 3))]]
