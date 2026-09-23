from medical_learning_system.evidence_store import (
    EvidenceContentType,
    EvidenceStore,
    make_evidence_block,
)


def block(index, page_index):
    return make_evidence_block(
        source_id="source-1",
        block_index=index,
        page_index=page_index,
        content_type=EvidenceContentType.TEXT,
        parser="native-test",
        text=f"block-{index}",
    )


def test_page_range_uses_one_based_physical_pages(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.replace_source(
        "source-1",
        [
            block(0, 0),
            block(1, 1),
            block(2, 2),
            block(3, 3),
        ],
    )

    found = store.list_page_range("source-1", 2, 3)
    assert [item.block_index for item in found] == [1, 2]
