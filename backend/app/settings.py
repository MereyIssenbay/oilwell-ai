"""Local settings. Secret database URLs never participate in repr/log output."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_url: str = field(default="", repr=False)
    model_artifact_dir: Path | None = None
    max_request_bytes: int = 262_144
    max_concurrent_predictions: int = 4
    database_connect_timeout: int = 3
    database_statement_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if not 1024 <= self.max_request_bytes <= 1_048_576:
            raise ValueError("Request byte limit outside local service bounds")
        if not 1 <= self.max_concurrent_predictions <= 16:
            raise ValueError("Invalid prediction concurrency")
        if not 1 <= self.database_connect_timeout <= 30:
            raise ValueError("Invalid database timeout")
        if not 100 <= self.database_statement_timeout_ms <= 30_000:
            raise ValueError("Invalid database statement timeout")

    @property
    def bundle_path(self) -> Path:
        return self.model_artifact_dir or self.root / "ml/artifacts/phase5/c4e1835a82620306778a"

    @classmethod
    def from_environment(cls) -> Settings:
        root = Path(os.environ.get("OILWELL_ROOT", Path(__file__).resolve().parents[2])).resolve()
        artifact = os.environ.get("MODEL_ARTIFACT_DIR")
        return cls(root=root, database_url=os.environ.get("DATABASE_URL", ""),
                   model_artifact_dir=Path(artifact).resolve() if artifact else None,
                   max_request_bytes=int(os.environ.get("MAX_REQUEST_BYTES", "262144")),
                   max_concurrent_predictions=int(os.environ.get("MAX_CONCURRENT_PREDICTIONS", "4")))
