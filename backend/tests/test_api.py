"""End-to-end API tests in fixture mode (no network)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from gufu.config import Settings
from gufu.jobs.builder import Builder
from gufu.main import create_app


@pytest.fixture
async def client(tmp_path):
    settings = Settings(fixture_mode=True, db_path=tmp_path / "t.sqlite", auto_build_on_start=False, sec_user_agent="")
    app = create_app(settings, run_scheduler=False)
    async with app.router.lifespan_context(app):
        state = app.state.gufu
        # build a small subset so the screener / home have rows
        b = Builder(state)
        await b.ensure_ciks()
        subset = ["AAPL", "MSFT", "JPM", "XOM", "BRK.B"]
        await b.build_facts(subset)
        await b.build_prices(subset)
        await b.build_metrics(subset)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_health_and_companies(client):
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json()["fixture_mode"] is True
    r = await client.get("/api/companies?q=app")
    assert r.status_code == 200
    tickers = [c["ticker"] for c in r.json()]
    assert "AAPL" in tickers
    r = await client.get("/api/companies?q=berkshire")
    assert r.json()[0]["ticker"] == "BRK.B"
    r = await client.get("/api/companies")
    assert len(r.json()) > 400


async def test_company_page_bundle(client):
    r = await client.get("/api/company/AAPL")
    assert r.status_code == 200
    d = r.json()
    assert d["profile"]["ticker"] == "AAPL"
    assert d["quote"]["price"] is not None
    assert d["metrics"]["pe"] is not None
    assert [g["group"] for g in d["groups"]][:5] == ["valuation", "profitability", "strength", "growth", "dividend"]
    assert d["scores"]["piotroski_f"]["score"] >= 0
    assert d["dcf"]["assumptions"]["discount_rate"] == 0.10
    assert d["data_status"]["annual_years"] >= 5


async def test_company_on_demand_when_not_cached(client):
    r = await client.get("/api/company/NVDA")  # not in the prebuilt subset -> built on demand
    assert r.status_code == 200
    assert r.json()["profile"]["ticker"] == "NVDA"
    r = await client.get("/api/company/NOPE")
    assert r.status_code == 404


async def test_financials_and_prices(client):
    r = await client.get("/api/company/AAPL/financials?freq=annual")
    d = r.json()
    assert d["freq"] == "annual" and len(d["periods"]) >= 5
    assert {"key", "label", "v"} <= set(d["periods"][-1].keys())
    r = await client.get("/api/company/AAPL/financials?freq=quarterly")
    q = r.json()
    assert len(q["periods"]) > len(d["periods"])
    assert q["periods"][-1]["label"].startswith("Q")
    r = await client.get("/api/company/AAPL/prices?range=1y")
    p = r.json()
    assert 200 <= len(p["points"]) <= 270
    r = await client.get("/api/company/AAPL/prices?range=max")
    assert r.json()["downsampled"] is True


async def test_screener_and_home(client):
    r = await client.get("/api/screener?sort=pe&order=asc&page_size=10")
    d = r.json()
    assert d["total"] >= 5 and len(d["rows"]) >= 5
    pes = [row["pe"] for row in d["rows"] if row["pe"] is not None]
    assert pes == sorted(pes)
    r = await client.get("/api/screener?sector=Financials")
    assert all(row["sector"] == "Financials" for row in r.json()["rows"])
    r = await client.get("/api/screener?pe_max=1")
    assert r.json()["total"] <= d["total"]
    r = await client.get("/api/screener/facets")
    assert any(s["name"] == "Financials" for s in r.json()["sectors"])
    r = await client.get("/api/home")
    h = r.json()
    assert h["stats"]["with_data"] >= 5
    assert h["sectors"] and h["largest"]
    r = await client.get("/api/metrics/definitions")
    assert any(m["key"] == "peg" for m in r.json())


async def test_admin_job_endpoints(client):
    r = await client.get("/api/admin/jobs/latest")
    assert r.status_code == 200
