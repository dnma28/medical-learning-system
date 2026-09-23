import json
from pathlib import Path

from pydantic import BaseModel


class JsonlStore:
    """Append-only JSONL store for early candidate/canonical exports."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item: BaseModel) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n"
            )
