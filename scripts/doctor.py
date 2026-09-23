from importlib.util import find_spec
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medical_learning_system.config import Settings
from medical_learning_system.retrieval import RAGAnythingAdapter, RAGConfig


def mark(ok: bool) -> str:
    return "OK" if ok else "MISSING"


def main() -> None:
    settings = Settings()
    checks = {
        "package_import": find_spec("medical_learning_system") is not None,
        "data_dir": settings.data_dir.exists(),
        "raganything": RAGAnythingAdapter(RAGConfig()).dependency_available(),
    }
    for name, ok in checks.items():
        print(f"[{mark(ok):7}] {name}")
    if not checks["raganything"]:
        print("\nRAG integration is scaffolded but the optional dependency is not installed.")
        print("Install with: pip install -e '.[rag]'")


if __name__ == "__main__":
    main()
