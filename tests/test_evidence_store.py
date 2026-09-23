from medical_learning_system.evidence_store import (
    EvidenceContentType,
    EvidenceStore,
    make_evidence_block,
)


SOURCE = "costanzo-physiology-6e"
OTHER = "guyton-hall-physiology"


def block(
    block_index: int,
    *,
    source_id: str = SOURCE,
    page_index: int = 0,
    content_type: EvidenceContentType = EvidenceContentType.TEXT,
    text: str | None = "example",
    asset_ref: str | None = None,
):
    return make_evidence_block(
        source_id=source_id,
        block_index=block_index,
        page_index=page_index,
        content_type=content_type,
        parser="mineru",
        text=text,
        asset_ref=asset_ref,
    )


def test_evidence_round_trip_preserves_block_order(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.replace_source(
        SOURCE,
        [
            block(2, page_index=3, text="third"),
            block(0, page_index=0, text="first"),
            block(1, page_index=1, text="second"),
        ],
    )

    loaded = store.list_source(SOURCE)
    assert [item.block_index for item in loaded] == [0, 1, 2]
    assert [item.text for item in loaded] == ["first", "second", "third"]


def test_pdf_page_is_one_based():
    item = block(0, page_index=7)
    assert item.page_index == 7
    assert item.pdf_page == 8


def test_same_locator_and_content_produces_same_evidence_id():
    first = block(0, page_index=2, text="membrane potential")
    second = block(0, page_index=2, text="membrane   potential")
    assert first.evidence_id == second.evidence_id
    assert first.content_sha256 == second.content_sha256


def test_content_change_produces_new_evidence_id():
    first = block(0, text="old evidence")
    changed = block(0, text="new evidence")
    assert first.evidence_id != changed.evidence_id


def test_replace_source_removes_obsolete_blocks_only_for_that_source(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.replace_source(SOURCE, [block(0), block(1)])
    store.replace_source(OTHER, [block(0, source_id=OTHER, text="Guyton")])

    store.replace_source(SOURCE, [block(0, text="refreshed")])

    assert len(store.list_source(SOURCE)) == 1
    assert len(store.list_source(OTHER)) == 1


def test_summary_keeps_modalities_distinct(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.replace_source(
        SOURCE,
        [
            block(0, content_type=EvidenceContentType.TEXT, text="paragraph"),
            block(
                1,
                content_type=EvidenceContentType.IMAGE,
                text=None,
                asset_ref="images/figure-1.png",
            ),
            block(2, content_type=EvidenceContentType.TABLE, text="<table />"),
            block(3, content_type=EvidenceContentType.EQUATION, text="V=IR"),
        ],
    )

    summary = store.summarize(SOURCE)
    assert summary.total == 4
    assert summary.text == 1
    assert summary.image == 1
    assert summary.table == 1
    assert summary.equation == 1


def test_evidence_can_be_linked_to_structure_node(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    linked = make_evidence_block(
        source_id=SOURCE,
        structure_node_id="section-membrane-potential",
        block_index=0,
        page_index=10,
        content_type=EvidenceContentType.TEXT,
        parser="mineru",
        text="Resting membrane potential...",
        bbox=(10.0, 20.0, 300.0, 400.0),
    )
    store.replace_source(SOURCE, [linked])

    found = store.list_structure_node(SOURCE, "section-membrane-potential")
    assert len(found) == 1
    assert found[0].bbox == (10.0, 20.0, 300.0, 400.0)
