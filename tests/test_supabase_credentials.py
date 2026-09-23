from types import SimpleNamespace
import sys

from medical_learning_system.supabase_storage import build_supabase_client


def _fake_supabase(monkeypatch):
    calls = []

    def create_client(url, key):
        calls.append((url, key))
        return (url, key)

    monkeypatch.setitem(
        sys.modules,
        "supabase",
        SimpleNamespace(create_client=create_client),
    )
    return calls


def test_build_client_prefers_current_secret_key(monkeypatch):
    calls = _fake_supabase(monkeypatch)
    monkeypatch.setenv("MLS_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("MLS_SUPABASE_SECRET_KEY", "sb_secret_current")
    monkeypatch.setenv("MLS_SUPABASE_SERVICE_ROLE_KEY", "legacy")

    result = build_supabase_client()

    assert result == ("https://project.supabase.co", "sb_secret_current")
    assert calls == [
        ("https://project.supabase.co", "sb_secret_current")
    ]


def test_build_client_keeps_legacy_service_role_fallback(monkeypatch):
    _fake_supabase(monkeypatch)
    monkeypatch.setenv("MLS_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.delenv("MLS_SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("MLS_SUPABASE_SERVICE_ROLE_KEY", "legacy")

    assert build_supabase_client() == (
        "https://project.supabase.co",
        "legacy",
    )


def test_explicit_secret_key_wins_over_environment(monkeypatch):
    _fake_supabase(monkeypatch)
    monkeypatch.setenv("MLS_SUPABASE_URL", "https://env.supabase.co")
    monkeypatch.setenv("MLS_SUPABASE_SECRET_KEY", "env-secret")

    assert build_supabase_client(
        url="https://explicit.supabase.co",
        secret_key="explicit-secret",
        service_role_key="legacy-explicit",
    ) == (
        "https://explicit.supabase.co",
        "explicit-secret",
    )
