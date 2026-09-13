"""Typed accessors over the SQLite tables."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from typing import Any

import orjson

from gufu.store.db import Database
from gufu.universe import CompanyProfile


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Repo:
    def __init__(self, db: Database):
        self.db = db

    # companies -------------------------------------------------------------
    def upsert_companies(self, profiles: list[CompanyProfile]) -> None:
        with self.db.lock:
            self.db.conn.executemany(
                "INSERT INTO companies(ticker,cik,name,sector,sub_industry) VALUES(?,?,?,?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET cik=excluded.cik,name=excluded.name,"
                "sector=excluded.sector,sub_industry=excluded.sub_industry",
                [(p.ticker, p.cik, p.name, p.sector, p.sub_industry) for p in profiles],
            )

    def get_companies(self) -> list[CompanyProfile]:
        rows = self.db.fetchall("SELECT * FROM companies ORDER BY ticker")
        return [CompanyProfile(r["ticker"], r["name"], r["sector"], r["sub_industry"], r["cik"]) for r in rows]

    def get_company(self, ticker: str) -> CompanyProfile | None:
        r = self.db.fetchone("SELECT * FROM companies WHERE ticker=?", (ticker,))
        if not r:
            return None
        return CompanyProfile(r["ticker"], r["name"], r["sector"], r["sub_industry"], r["cik"])

    def set_cik(self, ticker: str, cik: int) -> None:
        self.db.execute("UPDATE companies SET cik=? WHERE ticker=?", (cik, ticker))

    # raw facts -------------------------------------------------------------
    def put_raw_facts(self, cik: int, body: dict, filed_max: str | None) -> None:
        blob = gzip.compress(orjson.dumps(body), compresslevel=5)
        self.db.execute(
            "INSERT OR REPLACE INTO raw_facts(cik,fetched_at,filed_max,body) VALUES(?,?,?,?)",
            (cik, now_iso(), filed_max, blob),
        )

    def get_raw_facts(self, cik: int) -> tuple[dict, str, str | None] | None:
        r = self.db.fetchone("SELECT * FROM raw_facts WHERE cik=?", (cik,))
        if not r:
            return None
        return orjson.loads(gzip.decompress(r["body"])), r["fetched_at"], r["filed_max"]

    def raw_facts_meta(self, cik: int) -> tuple[str, str | None] | None:
        r = self.db.fetchone("SELECT fetched_at, filed_max FROM raw_facts WHERE cik=?", (cik,))
        return (r["fetched_at"], r["filed_max"]) if r else None

    # financials ------------------------------------------------------------
    def put_financials(self, cik: int, body: dict, latest_10k: str | None, latest_10q: str | None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO financials(cik,computed_at,latest_10k_filed,latest_10q_filed,body) VALUES(?,?,?,?,?)",
            (cik, now_iso(), latest_10k, latest_10q, orjson.dumps(body).decode()),
        )

    def get_financials(self, cik: int) -> dict | None:
        r = self.db.fetchone("SELECT body FROM financials WHERE cik=?", (cik,))
        return orjson.loads(r["body"]) if r else None

    # prices ----------------------------------------------------------------
    def put_prices(self, ticker: str, body: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO prices(ticker,fetched_at,currency,body) VALUES(?,?,?,?)",
            (ticker, now_iso(), body.get("currency", "USD"), orjson.dumps(body).decode()),
        )

    def get_prices(self, ticker: str) -> tuple[dict, str] | None:
        r = self.db.fetchone("SELECT body, fetched_at FROM prices WHERE ticker=?", (ticker,))
        return (orjson.loads(r["body"]), r["fetched_at"]) if r else None

    def prices_meta(self, ticker: str) -> str | None:
        r = self.db.fetchone("SELECT fetched_at FROM prices WHERE ticker=?", (ticker,))
        return r["fetched_at"] if r else None

    # metrics ---------------------------------------------------------------
    def put_metrics(self, ticker: str, body: dict, price_as_of: str | None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO metrics(ticker,computed_at,price_as_of,body) VALUES(?,?,?,?)",
            (ticker, now_iso(), price_as_of, orjson.dumps(body).decode()),
        )

    def get_metrics(self, ticker: str) -> dict | None:
        r = self.db.fetchone("SELECT body FROM metrics WHERE ticker=?", (ticker,))
        return orjson.loads(r["body"]) if r else None

    def get_all_metrics(self) -> dict[str, dict]:
        rows = self.db.fetchall("SELECT ticker, body FROM metrics")
        return {r["ticker"]: orjson.loads(r["body"]) for r in rows}

    def count_metrics(self) -> int:
        r = self.db.fetchone("SELECT COUNT(*) AS n FROM metrics")
        return int(r["n"]) if r else 0

    # jobs ------------------------------------------------------------------
    def create_job(self, kind: str, total: int) -> int:
        cur = self.db.execute(
            "INSERT INTO job_runs(kind,status,started_at,total) VALUES(?,?,?,?)",
            (kind, "running", now_iso(), total),
        )
        return int(cur.lastrowid)

    def update_job(self, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        if "errors" in fields and not isinstance(fields["errors"], str):
            fields["errors"] = json.dumps(fields["errors"])
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE job_runs SET {cols} WHERE id=?", (*fields.values(), job_id))

    def get_job(self, job_id: int) -> dict | None:
        r = self.db.fetchone("SELECT * FROM job_runs WHERE id=?", (job_id,))
        return self._job_row(r)

    def latest_job(self, kind: str | None = None) -> dict | None:
        if kind:
            r = self.db.fetchone("SELECT * FROM job_runs WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,))
        else:
            r = self.db.fetchone("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1")
        return self._job_row(r)

    @staticmethod
    def _job_row(r) -> dict | None:
        if not r:
            return None
        d = dict(r)
        try:
            d["errors"] = json.loads(d.get("errors") or "{}")
        except json.JSONDecodeError:
            d["errors"] = {}
        return d

    # legacy (pre-XBRL) ------------------------------------------------------
    def put_legacy_doc(self, cik: int, accn: str, doc: str, body: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO legacy_docs(cik,accn,doc,fetched_at,body) VALUES(?,?,?,?,?)",
            (cik, accn, doc, now_iso(), gzip.compress(body.encode("utf-8", "replace"), compresslevel=5)),
        )

    def get_legacy_doc(self, cik: int, accn: str, doc: str) -> str | None:
        r = self.db.fetchone("SELECT body FROM legacy_docs WHERE cik=? AND accn=? AND doc=?", (cik, accn, doc))
        return gzip.decompress(r["body"]).decode("utf-8", "replace") if r else None

    def put_legacy(self, cik: int, body: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO legacy_financials(cik,computed_at,body) VALUES(?,?,?)",
                        (cik, now_iso(), orjson.dumps(body).decode()))

    def get_legacy(self, cik: int) -> dict | None:
        r = self.db.fetchone("SELECT body FROM legacy_financials WHERE cik=?", (cik,))
        return orjson.loads(r["body"]) if r else None

    def delete_legacy(self, cik: int) -> None:
        self.db.execute("DELETE FROM legacy_financials WHERE cik=?", (cik,))

    def count_legacy(self) -> int:
        r = self.db.fetchone("SELECT COUNT(*) AS n FROM legacy_financials")
        return int(r["n"]) if r else 0

    # kv --------------------------------------------------------------------
    def kv_get(self, key: str) -> str | None:
        r = self.db.fetchone("SELECT value FROM kv WHERE key=?", (key,))
        return r["value"] if r else None

    def kv_set(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, value))
