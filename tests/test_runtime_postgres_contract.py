"""Actual store/bridge/CLI -> PostgreSQL regression, never a production connection.

Opt in with MLS_RUNTIME_POSTGRES_CONTRACT=1 and disposable local PG* settings.
Each test owns a new database; teardown drops it rather than deleting evidence.
CI runs this on PostgreSQL 17 alongside the rollback-only SQL contracts.
"""
import asyncio
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_hoc90_deeptutor_bridge import _decision, _session

from medical_learning_system.cli.hoc90_deeptutor import _submit
from medical_learning_system.deeptutor_runtime import (
    DeepTutorReadingInput,
    DeepTutorRuntimeExecutor,
)
from medical_learning_system.hoc90.deeptutor_bridge import DeepTutorSubmission, Hoc90DeepTutorBridge
from medical_learning_system.hoc90.session import LearningEvent, LearningEventType
from medical_learning_system.student.models import ConceptMastery, MasteryLevel
from medical_learning_system.student.skills import SkillNode, SkillState
from medical_learning_system.supabase_learning_state import SupabaseLearningStateStore

pytestmark = pytest.mark.skipif(
    os.getenv("MLS_RUNTIME_POSTGRES_CONTRACT") != "1", reason="isolated PostgreSQL opt-in"
)
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    "0001_core_storage.sql", "0009_adaptive_learning_runtime.sql",
    "0011_source_aware_hoc90_events.sql", "20260927024500_fsrs_spaced_retrieval.sql",
    "20260928172534_learning_events_append_only.sql",
    "20260928200000_learner_runtime_projection_atomicity.sql",
]


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    assert re.fullmatch(r"[a-z_]+", value), value
    return '"' + value + '"'


class PgClient:
    """Small test transport: real SQL/roles/RPC, no emulated database behavior."""
    def __init__(self, database):
        self.database = database

    def sql(self, sql, *, backend=True):
        prefix = "begin; set local role service_role; " if backend else ""
        suffix = "; commit;" if backend else ""
        result = subprocess.run(
            [os.getenv("MLS_TEST_PSQL", "psql"), "-XqAt", "-v", "ON_ERROR_STOP=1",
             "-d", self.database], input=prefix + sql + suffix,
            text=True, capture_output=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        output = result.stdout.strip()
        return json.loads(output) if output else None

    def table(self, name):
        return PgQuery(self, name)

    def rpc(self, name, params):
        args = ",".join(
            f"{identifier(key)} => {literal(json.dumps(value))}::jsonb"
            if isinstance(value, (dict, list)) else
            f"{identifier(key)} => {literal(value)}" if value is not None else
            f"{identifier(key)} => null"
            for key, value in params.items()
        )
        return SimpleNamespace(execute=lambda: SimpleNamespace(
            data=self.sql(f"select public.{identifier(name)}({args})")
        ))


class PgQuery:
    def __init__(self, client, table):
        self.client, self.table = client, identifier(table)
        self.filters = []
        self.limit_count = 1000
        self.payload = None
        self.conflict = None

    def select(self, fields):
        assert fields == "*"
        return self

    def eq(self, field, value):
        expression = ("metadata->>'deeptutor_interaction_id'" if
                      field == "metadata->>deeptutor_interaction_id" else identifier(field))
        self.filters.append(f"{expression}={literal(value)}")
        return self

    def limit(self, count):
        self.limit_count = int(count)
        return self

    def insert(self, row):
        self.payload = row
        return self

    def upsert(self, row, on_conflict):
        self.payload, self.conflict = row, on_conflict
        return self

    def execute(self):
        table = f"public.{self.table}"
        if self.payload is None:
            where = " and ".join(self.filters) or "true"
            sql = f"select * from {table} where {where} limit {self.limit_count}"
            sql = f"select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) from ({sql}) t"
        else:
            row = literal(json.dumps(self.payload))
            # Only supplied columns; defaults stay real PostgreSQL defaults.
            columns = ",".join(identifier(key) for key in self.payload)
            sql = (f"insert into {table} ({columns}) select {columns} from "
                   f"jsonb_populate_record(null::{table},{row}::jsonb)")
            if self.conflict:
                updates = ",".join(f"{identifier(k)}=excluded.{identifier(k)}"
                                   for k in self.payload if k != self.conflict)
                sql += f" on conflict ({identifier(self.conflict)}) do update set {updates}"
            sql = f"with saved as ({sql} returning *) select jsonb_agg(to_jsonb(saved)) from saved"
        return SimpleNamespace(data=self.client.sql(sql))


@pytest.fixture
def store():
    database = "mls_contract_" + uuid4().hex
    admin = PgClient(os.getenv("PGDATABASE", "postgres"))
    admin.sql(f'create database "{database}" template template0', backend=False)
    client = PgClient(database)
    try:
        for name in MIGRATIONS:
            client.sql((ROOT / "supabase/migrations" / name).read_text(), backend=False)
        result = SupabaseLearningStateStore(client)
        result.save_session(_session())
        result.upsert_skill_node(SkillNode(skill_node_id="skill-a", vi_name="Fixture", domain="test"))
        yield result
    finally:
        admin.sql(f'drop database "{database}" with (force)', backend=False)


def event(store, *, event_type=LearningEventType.EXPLANATION, outcome="correct", **kwargs):
    item = LearningEvent(session_id="session-1", concept_id="concept-a",
                         event_type=event_type, outcome=outcome, **kwargs)
    store.append_event(item)
    return item


def seed_mastery(store):
    evidence = event(store)
    return store.upsert_mastery(ConceptMastery(
        concept_id="concept-a", mastery_level=MasteryLevel.M2,
        historical_peak_mastery=MasteryLevel.M2, evidence_for_mastery=[evidence.event_id],
    ), evidence_event_id=evidence.event_id)


@pytest.mark.parametrize("reduction_outcome", ["partial", "incorrect", "correct"])
def test_mastery_real_store_timing_fsrs_again_reduction_and_retained_peak(store, reduction_outcome):
    current = seed_mastery(store)
    exposure = event(store, event_type=LearningEventType.CHECKPOINT, outcome=None)
    # The actual store path must UPDATE rather than firing a speculative INSERT.
    current = store.upsert_mastery(current.model_copy(update={"next_review": exposure.created_at}),
                                  evidence_event_id=exposure.event_id)
    failed = event(store, event_type=LearningEventType.RETRIEVAL, outcome="incorrect",
                   metadata={"retrieval_independent": True, "retrieval_rating": "again"})
    current = store.apply_spaced_retrieval_event(failed)
    assert current.retrieval_failures == 1 and current.next_review is not None
    assert current.mastery_level == current.historical_peak_mastery == MasteryLevel.M2
    for outcome in (reduction_outcome, "correct"):
        assessment = event(store, outcome=outcome, metadata={"evidence_ceiling": "M1"})
        current = store.upsert_mastery(current.model_copy(update={
            "mastery_level": MasteryLevel.M1,
            "evidence_for_mastery": current.evidence_for_mastery + [assessment.event_id],
        }), evidence_event_id=assessment.event_id)
        assert current.mastery_level == MasteryLevel.M1
        assert current.historical_peak_mastery == MasteryLevel.M2
    assert store.get_mastery("concept-a") == current


@pytest.mark.parametrize("reduction_outcome", ["partial", "incorrect"])
def test_skill_real_store_retained_high_level_and_assessed_reduction(store, reduction_outcome):
    evidence = event(store, metadata={"skill_node_id": "skill-a"})
    current = store.upsert_skill_state(SkillState(
        skill_node_id="skill-a", mastery_level=MasteryLevel.M2,
        evidence_summary={"event_ids": [evidence.event_id]},
    ), evidence_event_id=evidence.event_id)
    exposure = event(store, event_type=LearningEventType.CHECKPOINT, outcome=None,
                     metadata={"skill_node_id": "skill-a"})
    current = store.upsert_skill_state(current.model_copy(update={"next_review": exposure.created_at}),
                                      evidence_event_id=exposure.event_id)
    assert current.mastery_level == MasteryLevel.M2
    failed = event(store, outcome=reduction_outcome, metadata={"skill_node_id": "skill-a"})
    current = store.upsert_skill_state(current.model_copy(update={
        "mastery_level": MasteryLevel.M1, "evidence_summary": {"event_ids": [failed.event_id]},
    }), evidence_event_id=failed.event_id)
    assert current.mastery_level == MasteryLevel.M1
    assert store.get_skill_state("skill-a") == current


@pytest.mark.parametrize("table", ["mastery", "skill"])
def test_real_store_true_insert_grants_remain_guarded(store, table):
    bad = event(store, outcome="incorrect", metadata={"skill_node_id": "skill-a"})
    with pytest.raises(RuntimeError, match="assessed correct"):
        if table == "mastery":
            store.upsert_mastery(ConceptMastery(
                concept_id="concept-a", mastery_level=MasteryLevel.M1,
                historical_peak_mastery=MasteryLevel.M2, evidence_for_mastery=[bad.event_id],
            ), evidence_event_id=bad.event_id)
        else:
            store.upsert_skill_state(SkillState(
                skill_node_id="skill-a", mastery_level=MasteryLevel.M2,
                evidence_summary={"event_ids": [bad.event_id]},
            ), evidence_event_id=bad.event_id)
    assert store.get_mastery("concept-a") is None
    assert store.get_skill_state("skill-a") is None


@pytest.mark.parametrize("table", ["mastery", "skill"])
def test_concurrent_projection_writers_choose_real_insert_then_update(store, table):
    evidence = event(store, metadata={"skill_node_id": "skill-a"})
    barrier = Barrier(2)

    def save(_):
        barrier.wait(timeout=10)
        if table == "mastery":
            return store.upsert_mastery(ConceptMastery(
                concept_id="concept-a", mastery_level=MasteryLevel.M2,
                historical_peak_mastery=MasteryLevel.M2, evidence_for_mastery=[evidence.event_id],
            ), evidence_event_id=evidence.event_id)
        return store.upsert_skill_state(SkillState(
            skill_node_id="skill-a", mastery_level=MasteryLevel.M2,
            evidence_summary={"event_ids": [evidence.event_id]},
        ), evidence_event_id=evidence.event_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert all(item.mastery_level == MasteryLevel.M2 for item in results)
    name = store.MASTERY if table == "mastery" else store.SKILL_STATE
    assert len(store.client.table(name).select("*").execute().data) == 1


def test_projection_rpc_is_backend_only_and_table_allowlisted(store):
    grants = store.client.sql("""select jsonb_build_object(
        'anon',has_function_privilege('anon','public.mls_save_learner_projection(text,jsonb)','execute'),
        'authenticated',has_function_privilege('authenticated','public.mls_save_learner_projection(text,jsonb)','execute'),
        'service_role',has_function_privilege('service_role','public.mls_save_learner_projection(text,jsonb)','execute'))""")
    assert grants == {"anon": False, "authenticated": False, "service_role": True}
    with pytest.raises(RuntimeError, match="unsupported learner projection table"):
        store.client.rpc("mls_save_learner_projection", {
            "p_table": store.EVENTS, "p_row": {},
        }).execute()


def prepare(store, *, quiz=False):
    async def runner(*args):
        return ({"type": "quiz", "title": "Test", "message": "Synthetic fixture",
                 "payload": {"questions": [{"id": "q1", "prompt": "Choose",
                 "choices": ["A", "B", "C", "D"], "correct_choice_index": 1}]}} if quiz else
                {"type": "card", "title": "Test", "message": "Synthetic fixture",
                 "payload": {"steps": ["one"]}})
    bridge = Hoc90DeepTutorBridge(store=store, executor=DeepTutorRuntimeExecutor(runner=runner))
    prepared = asyncio.run(bridge.prepare(
        session_id="session-1", decision=_decision(), source_context=["synthetic verified fixture"],
        reading=DeepTutorReadingInput(material_id="test"), quiz=quiz,
    ))
    return bridge, prepared.interaction.interaction_id


def test_bridge_and_cli_retry_after_commit_and_with_newer_pending(store):
    bridge, interaction = prepare(store)
    submission = DeepTutorSubmission(interaction_id=interaction, learner_response="answer")
    original = bridge.submit(session_id="session-1", submission=submission)
    assert bridge.submit(session_id="session-1", submission=submission) == original
    args = SimpleNamespace(session_id="session-1", interaction_id=interaction,
                           response="answer", question_id=None, choice_index=None)
    assert _submit(args, store.client) == original.model_dump(mode="json")
    _, next_interaction = prepare(store)
    checkpoint = store.get_session("session-1")
    assert _submit(args, store.client) == original.model_dump(mode="json")
    assert store.get_session("session-1") == checkpoint
    assert checkpoint.checkpoint.pending_deeptutor_interaction["interaction_id"] == next_interaction
    with pytest.raises(ValueError, match="Conflicting"):
        bridge.submit(session_id="session-1", submission=submission.model_copy(
            update={"learner_response": "different answer"}))
    assert store.get_session("session-1") == checkpoint
    assert len(store.client.table(store.EVENTS).select("*").execute().data) == 1


def test_lost_response_retry_returns_persisted_event(store, monkeypatch):
    bridge, interaction = prepare(store)
    original_commit = store.commit_deeptutor_submission
    committed = []

    def lose_response(**kwargs):
        committed.append(original_commit(**kwargs))
        raise ConnectionError("response lost after database commit")

    monkeypatch.setattr(store, "commit_deeptutor_submission", lose_response)
    submission = DeepTutorSubmission(interaction_id=interaction, learner_response="answer")
    with pytest.raises(ConnectionError, match="lost"):
        bridge.submit(session_id="session-1", submission=submission)
    assert bridge.submit(session_id="session-1", submission=submission) == committed[0]
    assert len(committed) == 1


def test_commit_between_event_lookup_and_checkpoint_read_is_recovered(store, monkeypatch):
    bridge, interaction = prepare(store)
    submission = DeepTutorSubmission(interaction_id=interaction, learner_response="answer")
    other = Hoc90DeepTutorBridge(store=SupabaseLearningStateStore(store.client))
    original_lookup = store.get_deeptutor_submission
    committed = []

    def stale_lookup(**kwargs):
        result = original_lookup(**kwargs)
        if not committed:
            committed.append(other.submit(session_id="session-1", submission=submission))
        return result

    monkeypatch.setattr(store, "get_deeptutor_submission", stale_lookup)
    assert bridge.submit(session_id="session-1", submission=submission) == committed[0]
    assert len(store.client.table(store.EVENTS).select("*").execute().data) == 1


@pytest.mark.parametrize("quiz", [False, True])
def test_racing_real_bridge_candidates_reject_conflict_return_only_committed(store, quiz):
    bridge, interaction = prepare(store, quiz=quiz)
    original_commit = store.commit_deeptutor_submission
    barrier = Barrier(2)
    candidates = []

    def synchronized_commit(**kwargs):
        candidates.append(kwargs)
        barrier.wait(timeout=10)  # Both built before either database commit.
        return original_commit(**kwargs)

    store.commit_deeptutor_submission = synchronized_commit
    submissions = ([DeepTutorSubmission(interaction_id=interaction, question_id="q1",
                                       selected_choice_index=i) for i in (0, 1)] if quiz else
                   [DeepTutorSubmission(interaction_id=interaction, learner_response=answer)
                    for answer in ("first answer", "different answer")])

    def submit(item):
        try:
            return bridge.submit(session_id="session-1", submission=item)
        except RuntimeError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, submissions))
    successes = [result for result in results if isinstance(result, LearningEvent)]
    failures = [result for result in results if isinstance(result, RuntimeError)]
    assert len(successes) == len(failures) == 1
    assert "conflicting DeepTutor" in str(failures[0])
    canonical = store.get_deeptutor_submission(session_id="session-1", interaction_id=interaction)
    assert successes[0] == canonical
    assert len(store.client.table(store.EVENTS).select("*").execute().data) == 1
    assert store.get_session("session-1").checkpoint.pending_deeptutor_interaction is None
    # Rebuild the winning candidate with a fresh timestamp. Readback must remain original.
    winning = next(item for item in candidates if item["event"].answer_summary == canonical.answer_summary
                   and item["event"].outcome == canonical.outcome)
    fresh = dict(winning, event=winning["event"].model_copy(update={
        "created_at": canonical.created_at + timedelta(seconds=30),
    }))
    assert original_commit(**fresh) == canonical
