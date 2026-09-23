from medical_learning_system.compilation_planner import (
    CompilationTier,
    QueueStatus,
)
from medical_learning_system.supabase_queue import (
    SupabaseCompilationQueueStore,
)


class Response:
    def __init__(self, data):
        self.data = data


class Rpc:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.calls.append((self.name, self.params))
        return Response(self.client.results.get(self.name, []))


class Client:
    def __init__(self):
        self.calls = []
        self.results = {}

    def rpc(self, name, params):
        return Rpc(self, name, params)


def row(status="running"):
    return {
        "job_id": "job-1",
        "source_id": "source-1",
        "tier": "core",
        "status": status,
        "priority": 320,
        "attempts": 1,
        "max_attempts": 3,
        "requested_at": "2026-09-23T10:00:00+00:00",
        "updated_at": "2026-09-23T10:01:00+00:00",
    }


def test_claim_next_uses_atomic_rpc():
    client = Client()
    client.results["mls_claim_compilation_job"] = [row()]
    store = SupabaseCompilationQueueStore(client)

    job = store.claim_next()

    assert job.job_id == "job-1"
    assert job.tier == CompilationTier.CORE
    assert job.status == QueueStatus.RUNNING
    assert client.calls == [("mls_claim_compilation_job", {})]


def test_claim_next_returns_none_when_queue_is_empty():
    store = SupabaseCompilationQueueStore(Client())

    assert store.claim_next() is None


def test_finish_requires_rpc_to_return_running_job_transition():
    client = Client()
    client.results["mls_finish_compilation_job"] = [row("succeeded")]
    store = SupabaseCompilationQueueStore(client)

    job = store.finish("job-1", success=True)

    assert job.status == QueueStatus.SUCCEEDED
    assert client.calls[-1] == (
        "mls_finish_compilation_job",
        {"target_job_id": "job-1", "was_successful": True},
    )


def test_finish_rejects_missing_or_nonrunning_job():
    store = SupabaseCompilationQueueStore(Client())

    try:
        store.finish("job-missing", success=False)
    except ValueError as exc:
        assert "missing or is not running" in str(exc)
    else:
        raise AssertionError("expected ValueError")
