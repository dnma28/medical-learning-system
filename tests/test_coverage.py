import pytest

from medical_learning_system.coverage import (
    CoverageState,
    CoverageStore,
    StructureKind,
    StructureNode,
    validate_structure,
)


SOURCE = "costanzo-physiology-6e"


def tree() -> list[StructureNode]:
    return [
        StructureNode(
            source_id=SOURCE,
            node_id="book",
            kind=StructureKind.BOOK,
            title="Costanzo Physiology",
            depth=0,
            order_index=0,
        ),
        StructureNode(
            source_id=SOURCE,
            node_id="ch1",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Cellular Physiology",
            depth=1,
            order_index=1,
            page_start=1,
        ),
        StructureNode(
            source_id=SOURCE,
            node_id="ch1-membrane",
            parent_id="ch1",
            kind=StructureKind.SECTION,
            title="Cell Membranes",
            depth=2,
            order_index=2,
            page_start=2,
            page_end=8,
        ),
        StructureNode(
            source_id=SOURCE,
            node_id="ch1-transport",
            parent_id="ch1",
            kind=StructureKind.SECTION,
            title="Transport",
            depth=2,
            order_index=3,
            page_start=8,
            page_end=16,
        ),
    ]


def test_structure_round_trip_preserves_source_order(tmp_path):
    store = CoverageStore(tmp_path / "coverage.sqlite3")
    store.replace_structure(SOURCE, tree())

    loaded = store.get_structure(SOURCE)
    assert [node.node_id for node in loaded] == [
        "book",
        "ch1",
        "ch1-membrane",
        "ch1-transport",
    ]


def test_missing_parent_is_rejected():
    nodes = tree()
    nodes[-1] = nodes[-1].model_copy(update={"parent_id": "missing"})
    with pytest.raises(ValueError, match="missing parent"):
        validate_structure(SOURCE, nodes)


def test_duplicate_node_id_is_rejected():
    nodes = tree()
    nodes[-1] = nodes[-1].model_copy(update={"node_id": "ch1-membrane"})
    with pytest.raises(ValueError, match="duplicate node_id"):
        validate_structure(SOURCE, nodes)


def test_coverage_summary_tracks_learning_states(tmp_path):
    store = CoverageStore(tmp_path / "coverage.sqlite3")
    store.replace_structure(SOURCE, tree())
    store.set_coverage(SOURCE, "ch1", CoverageState.LEARNING)
    store.set_coverage(SOURCE, "ch1-membrane", CoverageState.MASTERED)
    store.set_coverage(SOURCE, "ch1-transport", CoverageState.REVIEW)

    summary = store.summarize(SOURCE)
    assert summary.total == 3
    assert summary.not_learned == 0
    assert summary.learning == 1
    assert summary.review == 1
    assert summary.mastered == 1


def test_structure_refresh_preserves_retained_coverage(tmp_path):
    store = CoverageStore(tmp_path / "coverage.sqlite3")
    store.replace_structure(SOURCE, tree())
    store.set_coverage(SOURCE, "ch1-membrane", CoverageState.MASTERED)

    refreshed = tree()[:-1]
    store.replace_structure(SOURCE, refreshed)

    summary = store.summarize(SOURCE)
    assert summary.total == 2
    assert summary.mastered == 1
    assert summary.not_learned == 1


def test_book_root_cannot_be_marked_as_learned(tmp_path):
    store = CoverageStore(tmp_path / "coverage.sqlite3")
    store.replace_structure(SOURCE, tree())

    with pytest.raises(ValueError, match="book root"):
        store.set_coverage(SOURCE, "book", CoverageState.MASTERED)
