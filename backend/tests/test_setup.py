"""Zero-config first run: the app boots without a SEC User-Agent and the setup endpoint provides one."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from gufu.config import Settings
from gufu.fetch.fixtures import LiveFetchers, SetupRequiredFetchers
from gufu.main import create_app
from gufu.setup import build_user_agent, write_env_value


def test_build_user_agent():
    assert build_user_agent("  Jane   Doe ", "jane@example.com") == "GuFu/0.1 (Jane Doe; jane@example.com)"
    with pytest.raises(ValueError):
        build_user_agent("J", "jane@example.com")
    with pytest.raises(ValueError):
        build_user_agent("Jane", "not-an-email")
    with pytest.raises(ValueError):
        build_user_agent('Jane "Q"', "jane@example.com")


def test_write_env_value_replaces_existing_and_commented(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# comment\n# GUFU_SEC_USER_AGENT="old"\nGUFU_FIXTURE_MODE=0\n', encoding="utf-8")
    write_env_value(p, "GUFU_SEC_USER_AGENT", "GuFu/0.1 (A; a@b.co)")
    text = p.read_text(encoding="utf-8")
    assert text.count("GUFU_SEC_USER_AGENT") == 1
    assert 'GUFU_SEC_USER_AGENT="GuFu/0.1 (A; a@b.co)"' in text
    assert "GUFU_FIXTURE_MODE=0" in text
    write_env_value(p, "GUFU_SEC_USER_AGENT", "GuFu/0.1 (B; b@b.co)")
    assert p.read_text(encoding="utf-8").count("GUFU_SEC_USER_AGENT") == 1
    write_env_value(tmp_path / "new" / ".env", "X", "1")
    assert (tmp_path / "new" / ".env").read_text() == 'X="1"\n'


@pytest.fixture
async def live_client(tmp_path):
    settings = Settings(fixture_mode=False, sec_user_agent="", db_path=tmp_path / "t.sqlite", auto_build_on_start=False,
                        env_path=tmp_path / ".env")
    app = create_app(settings, run_scheduler=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, app.state.gufu, settings


async def test_setup_flow(live_client):
    client, state, settings = live_client
    assert isinstance(state.fetchers, SetupRequiredFetchers)
    assert not state.setup_done.is_set()
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json()["setup_required"] is True and r.json()["fixture_mode"] is False
    # company pages fail gracefully (no network call, no crash)
    r = await client.get("/api/company/AAPL")
    assert r.status_code == 503 and "name and email" in r.json()["detail"]
    # validation
    r = await client.post("/api/admin/setup", json={"name": "Jane Doe", "email": "nope"})
    assert r.status_code == 422
    # success
    r = await client.post("/api/admin/setup", json={"name": "Jane Doe", "email": "jane@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_agent"] == "GuFu/0.1 (Jane Doe; jane@example.com)" and body["persisted"] == "env"
    assert 'GUFU_SEC_USER_AGENT="GuFu/0.1 (Jane Doe; jane@example.com)"' in settings.env_path.read_text()
    assert state.repo.kv_get("sec_user_agent") == body["user_agent"]
    assert isinstance(state.fetchers, LiveFetchers) and state.setup_done.is_set()
    r = await client.get("/api/health")
    assert r.json()["setup_required"] is False


async def test_kv_fallback_when_env_missing(tmp_path):
    settings = Settings(fixture_mode=False, sec_user_agent="", db_path=tmp_path / "t.sqlite", auto_build_on_start=False,
                        env_path=tmp_path / ".env")
    app = create_app(settings, run_scheduler=False)
    async with app.router.lifespan_context(app):
        state = app.state.gufu
        state.repo.kv_set("sec_user_agent", "GuFu/0.1 (Saved; s@x.io)")
    settings2 = Settings(fixture_mode=False, sec_user_agent="", db_path=tmp_path / "t.sqlite", auto_build_on_start=False,
                         env_path=tmp_path / ".env")
    app2 = create_app(settings2, run_scheduler=False)
    async with app2.router.lifespan_context(app2):
        st = app2.state.gufu
        assert isinstance(st.fetchers, LiveFetchers) and st.setup_done.is_set()
        assert settings2.sec_user_agent == "GuFu/0.1 (Saved; s@x.io)"


async def test_setup_rejected_in_fixture_mode(tmp_path):
    settings = Settings(fixture_mode=True, db_path=tmp_path / "t.sqlite", auto_build_on_start=False)
    app = create_app(settings, run_scheduler=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/admin/setup", json={"name": "Jane Doe", "email": "jane@example.com"})
            assert r.status_code == 400
