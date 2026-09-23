from importlib.util import find_spec
import os
from pathlib import Path
import shutil
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
        "mineru_command": shutil.which("mineru") is not None,
        "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
    }

    for name, ok in checks.items():
        print(f"[{mark(ok):7}] {name}")

    if not checks["raganything"]:
        print("\nInstall RAG support with: pip install -e '.[rag]'")
    if not checks["openai_api_key"]:
        print("Create .env from .env.example and set OPENAI_API_KEY.")
    if not checks["mineru_command"]:
        print("MinerU command is not available yet; verify the RAG-Anything install.")


if __name__ == "__main__":
    main()
