"""Read-only smoke check for the optional MarkItDown and LangGraph extras."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from medical_learning_system.markitdown_adapter import convert_with_markitdown


class CheckState(TypedDict):
    headings: list[str]
    heading_found: bool


def check_heading(state: CheckState) -> dict[str, bool]:
    return {"heading_found": "Optional tools smoke" in state["headings"]}


def main() -> None:
    with TemporaryDirectory() as directory:
        fixture = Path(directory) / "fixture.html"
        fixture.write_text(
            "<html><body><h1>Optional tools smoke</h1><p>Local fixture.</p></body></html>",
            encoding="utf-8",
        )
        parsed = convert_with_markitdown(fixture)

    assert parsed.parser == "markitdown"
    graph = StateGraph(CheckState)
    graph.add_node("check_heading", check_heading)
    graph.add_edge(START, "check_heading")
    graph.add_edge("check_heading", END)
    result = graph.compile().invoke(
        {
            "headings": [block.text for block in parsed.blocks if block.heading_level],
            "heading_found": False,
        }
    )
    assert result["heading_found"], "HTML conversion or graph execution failed"


if __name__ == "__main__":
    main()
