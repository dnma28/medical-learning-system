from medical_learning_system.source_map_checkpoint import (
    SourceMapCheckpoint,
    latest_checkpoint,
    parse_checkpoint_block,
    render_checkpoint_block,
)


def _checkpoint(status="IN_PROGRESS"):
    return SourceMapCheckpoint(
        work_key="source-map:neumann-kinesiology",
        book_id="neumann-kinesiology",
        batch_id="BATCH-CH12-PART3-001",
        status=status,
        cursor={
            "last_processed_node_id": "n23",
            "next_pending_node_id": "n24",
            "processed_count": 23,
        },
        artifacts={"ledger_sha256": "a" * 64},
    )


def test_checkpoint_round_trip_is_machine_readable_inside_prose():
    block = render_checkpoint_block(_checkpoint())
    parsed = parse_checkpoint_block("human summary\n" + block + "\nmore prose")
    assert parsed == _checkpoint()


def test_latest_checkpoint_skips_non_checkpoint_comments():
    older = render_checkpoint_block(_checkpoint("PREFLIGHT_LOCKED"))
    newer = render_checkpoint_block(_checkpoint("VALIDATED"))
    parsed = latest_checkpoint([older, "ordinary comment", newer])
    assert parsed is not None
    assert parsed.status == "VALIDATED"
