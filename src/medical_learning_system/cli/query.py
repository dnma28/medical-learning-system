from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from medical_learning_system.retrieval.openai_provider import build_openai_rag_ready
from medical_learning_system.retrieval.rag_anything_adapter import RAGConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query the existing Medical Learning System RAG index."
    )
    parser.add_argument("question")
    parser.add_argument("--working-dir", type=Path, default=Path("./rag_storage"))
    parser.add_argument(
        "--mode",
        choices=["local", "global", "hybrid", "naive", "mix"],
        default="hybrid",
    )
    parser.add_argument(
        "--parser",
        choices=["mineru", "docling", "paddleocr"],
        default="mineru",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    load_dotenv()
    rag = await build_openai_rag_ready(
        RAGConfig(
            working_dir=args.working_dir,
            parser=args.parser,
            parse_method="auto",
        )
    )
    result = await rag.aquery(args.question, mode=args.mode)
    print(result)


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
