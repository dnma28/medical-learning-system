from medical_learning_system.source_map_checkpoint import (
    SourceMapCheckpoint,
    latest_checkpoint,
    parse_checkpoint_block,
    render_checkpoint_block,
    validate_checkpoint_transition,
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



def test_latest_checkpoint_filters_exact_work_key_and_batch():
    other = SourceMapCheckpoint(
        work_key="source-map:other-book",
        book_id="other-book",
        batch_id="BATCH-OTHER",
        status="VALIDATED",
    )
    target = _checkpoint("ARTIFACT_VERIFIED")
    comments = [
        render_checkpoint_block(target),
        render_checkpoint_block(other),
    ]
    assert latest_checkpoint(
        comments,
        work_key=target.work_key,
        batch_id=target.batch_id,
    ) == target
    assert latest_checkpoint(comments, work_key="missing") is None



def test_checkpoint_transition_rejects_cross_work_and_regression():
    first = _checkpoint("INPUT_FROZEN")
    ready = _checkpoint("SOURCE_READY")
    validated = _checkpoint("VALIDATED")
    regressed = _checkpoint("SOURCE_READY")
    other = SourceMapCheckpoint(
        work_key="source-map:other",
        book_id=first.book_id,
        batch_id=first.batch_id,
        status="VALIDATED",
    )
    assert validate_checkpoint_transition(None, first) == []
    assert validate_checkpoint_transition(first, ready) == []
    assert validate_checkpoint_transition(ready, validated) == []
    assert any(
        "regressed" in error
        for error in validate_checkpoint_transition(validated, regressed)
    )
    assert any(
        "work_key changed" in error
        for error in validate_checkpoint_transition(validated, other)
    )
