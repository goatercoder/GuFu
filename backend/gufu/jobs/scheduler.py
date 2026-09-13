"""Startup build + periodic refresh loop."""

from __future__ import annotations

import asyncio
import logging

from gufu.jobs.builder import Builder, _age_hours
from gufu.services.screener_service import rebuild_screener
from gufu.state import AppState

log = logging.getLogger("gufu.scheduler")


async def scheduler_loop(state: AppState) -> None:
    b = Builder(state)
    try:
        await b.ensure_ciks()
        rebuild_screener(state)
        n_metrics = state.repo.count_metrics()
        if state.settings.auto_build_on_start and n_metrics < len(state.profiles) * 0.5:
            log.info("cache has %d/%d companies; starting full build", n_metrics, len(state.profiles))
            await b.build_all("all")
        while True:
            await asyncio.sleep(60)
            if state.build_lock.locked():
                continue
            facts_age = _age_hours(state.repo.kv_get("last_facts_build"))
            prices_age = _age_hours(state.repo.kv_get("last_prices_build"))
            if facts_age > state.settings.facts_max_age_days * 24:
                await b.build_all("facts")
            elif prices_age > state.settings.prices_max_age_hours:
                await b.build_all("prices")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("scheduler loop crashed")
