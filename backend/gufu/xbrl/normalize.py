"""Turn an SEC companyfacts JSON document into clean annual / quarterly / TTM period rows.

Pipeline
  1. collect facts per canonical field from the tag fallback lists (10-K / 10-Q only, right unit)
  2. dedupe restatements: per (tag, period) keep the latest filing, tiebreak on `frame`, then 10-K
  3. across tags: for each period take the highest-priority tag that has a value
  4. derive discrete quarters from cumulative (H1 / 9M / FY) facts: Q(E) = YTD(E) - YTD(E - 3 months)
  5. assemble annual and quarterly rows; attach balance-sheet instants; compute derived fields
  6. trailing twelve months = the last four consecutive quarters
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from gufu.xbrl import periods as P
from gufu.xbrl.models import Fact, Financials, PeriodRow
from gufu.xbrl.tags import ACCEPTED_FORMS, DURATION, FIELD_SPECS, INSTANT, FieldSpec

MAX_DURATION_DAYS = 400
ROW_ANCHOR_FIELDS = ("revenue", "net_income", "operating_income", "ocf", "eps_diluted")


# ----------------------------------------------------------------------------------------------
# step 1: collect
# ----------------------------------------------------------------------------------------------
def _iter_raw(cf: dict, tag: str) -> tuple[str, list[dict]] | None:
    taxonomy, _, name = tag.partition(":")
    if not name:
        taxonomy, name = "us-gaap", tag
    node = cf.get("facts", {}).get(taxonomy, {}).get(name)
    if not node:
        return None
    return name, node.get("units", {})


def _unit_series(units: dict, unit: str) -> list[dict]:
    if unit in units:
        return units[unit]
    # be lenient about unit spelling (e.g. 'USD/shares' vs 'USD/share')
    for k, v in units.items():
        if k.lower().replace("/share", "/shares") == unit.lower():
            return v
    return []


def collect_facts(cf: dict, spec: FieldSpec, tags: tuple[str, ...] | None = None) -> list[Fact]:
    out: list[Fact] = []
    for prio, tag in enumerate(tags or spec.tags):
        found = _iter_raw(cf, tag)
        if not found:
            continue
        name, units = found
        for raw in _unit_series(units, spec.unit):
            form = raw.get("form", "")
            if form not in ACCEPTED_FORMS:
                continue
            val = raw.get("val")
            if val is None:
                continue
            try:
                end = P.parse_date(raw["end"])
                filed = P.parse_date(raw["filed"])
            except (KeyError, ValueError):
                continue
            start = P.parse_date(raw["start"]) if raw.get("start") else None
            if spec.kind == DURATION:
                if start is None or start >= end or (end - start).days > MAX_DURATION_DAYS:
                    continue
                cls = P.classify_duration(start, end)
                if cls is None:
                    continue
            else:
                if start is not None:
                    continue
                cls = None
            out.append(
                Fact(
                    tag=name, prio=prio, start=start, end=end, val=float(val),
                    accn=raw.get("accn", ""), form=form, filed=filed, frame=raw.get("frame"), cls=cls,
                )
            )
    return out


def _aggregate_share_classes(facts: list[Fact]) -> list[Fact]:
    """dei:EntityCommonStockSharesOutstanding is reported once per share class; sum per (end, accn)."""
    groups: dict[tuple[date, str], list[Fact]] = defaultdict(list)
    for f in facts:
        groups[(f.end, f.accn)].append(f)
    out: list[Fact] = []
    for _, fs in groups.items():
        base = fs[0]
        if len(fs) == 1:
            out.append(base)
            continue
        # identical duplicates (same value repeated) are not classes; sum distinct entries only
        seen: set[float] = set()
        total = 0.0
        for f in fs:
            if f.val in seen:
                continue
            seen.add(f.val)
            total += f.val
        out.append(Fact(base.tag, base.prio, None, base.end, total, base.accn, base.form, base.filed, base.frame))
    return out


# ----------------------------------------------------------------------------------------------
# step 2 + 3: dedupe and pick per period
# ----------------------------------------------------------------------------------------------
def _fact_rank(f: Fact) -> tuple:
    return (f.filed, f.frame is not None, f.form.startswith("10-K"))


def select_per_period(facts: list[Fact]) -> dict[tuple[str, str | None], Fact]:
    """Return {(period_key, cls): Fact} choosing, per period, the best tag then the latest filing."""
    by_period: dict[tuple[str, str | None], dict[str, Fact]] = defaultdict(dict)
    for f in facts:
        k = (P.period_key(f.end), f.cls)
        cur = by_period[k].get(f.tag)
        if cur is None or _fact_rank(f) > _fact_rank(cur):
            by_period[k][f.tag] = f
    chosen: dict[tuple[str, str | None], Fact] = {}
    for k, per_tag in by_period.items():
        chosen[k] = min(per_tag.values(), key=lambda f: f.prio)
    return chosen


# ----------------------------------------------------------------------------------------------
# step 4: quarter derivation
# ----------------------------------------------------------------------------------------------
def derive_quarters(chosen: dict[tuple[str, str | None], Fact], no_subtract: bool = False) -> dict[str, Fact]:
    quarters: dict[str, Fact] = {k: f for (k, cls), f in chosen.items() if cls == P.Q}
    if no_subtract:
        # e.g. weighted share counts: use the cumulative figure as a stand-in for the last quarter
        for (k, cls), f in chosen.items():
            if cls != P.Q and k not in quarters:
                quarters[k] = Fact(f.tag, f.prio, f.start, f.end, f.val, f.accn, f.form, f.filed, f.frame, P.Q, True)
        return quarters

    shorter = {P.H: P.Q, P.NINE_M: P.H, P.FY: P.NINE_M}
    # pass 1: YTD(E) - YTD(E - 3 months) with the same start date
    for (k, cls), f in sorted(chosen.items(), key=lambda kv: kv[0][0]):
        if cls == P.Q or k in quarters:
            continue
        prev_key = P.key_minus_months(k, 3)
        prev = chosen.get((prev_key, shorter[cls]))
        if prev is None and cls == P.H:
            prev = quarters.get(prev_key)
        if prev is not None and f.start and prev.start and P.starts_match(f.start, prev.start):
            q_start = P.shift_months(prev.end, 0)
            quarters[k] = Fact(
                f.tag, f.prio, q_start, f.end, f.val - prev.val, f.accn, f.form, f.filed, f.frame, P.Q, True
            )
    # pass 2: FY - (Q1 + Q2 + Q3) when the 9M figure is missing
    for (k, cls), f in chosen.items():
        if cls != P.FY or k in quarters:
            continue
        prev_keys = [P.key_minus_months(k, n) for n in (9, 6, 3)]
        qs = [quarters.get(pk) for pk in prev_keys]
        if all(q is not None for q in qs) and f.start and qs[0].start and P.starts_match(f.start, qs[0].start):
            total = sum(q.val for q in qs)  # type: ignore[union-attr]
            quarters[k] = Fact(
                f.tag, f.prio, P.shift_months(qs[-1].end, 0), f.end, f.val - total,  # type: ignore[union-attr]
                f.accn, f.form, f.filed, f.frame, P.Q, True,
            )
    return quarters


# ----------------------------------------------------------------------------------------------
# step 5: rows
# ----------------------------------------------------------------------------------------------
def _short_term_debt(cf: dict, spec: FieldSpec) -> dict[str, Fact]:
    """DebtCurrent when reported, else the sum of the current-debt components at the same period."""
    direct = select_per_period(collect_facts(cf, spec))
    result: dict[str, Fact] = {k: f for (k, _), f in direct.items()}
    comp_facts: dict[str, dict[str, Fact]] = {}
    for tag in spec.components:
        chosen = select_per_period(collect_facts(cf, spec, (tag,)))
        for (k, _), f in chosen.items():
            comp_facts.setdefault(k, {})[tag] = f
    for k, per_tag in comp_facts.items():
        if k in result:
            continue
        seen_vals: set[float] = set()
        total = 0.0
        base = None
        for tag in spec.components:
            f = per_tag.get(tag)
            if f is None or f.val in seen_vals:
                continue
            seen_vals.add(f.val)
            total += f.val
            base = base or f
        if base is not None:
            result[k] = Fact("+".join(sorted(per_tag)), 99, None, base.end, total, base.accn, base.form, base.filed, None)
    return result


def _add_derived(row: PeriodRow) -> None:
    v = row.values
    s = row.sources

    def has(*keys: str) -> bool:
        return all(v.get(k) is not None for k in keys)

    if v.get("gross_profit") is None and has("revenue", "cost_of_revenue"):
        v["gross_profit"] = v["revenue"] - v["cost_of_revenue"]
        row.derived.add("gross_profit")
    if v.get("operating_income") is None and has("pretax_income", "interest_expense"):
        v["operating_income"] = v["pretax_income"] + v["interest_expense"]
        row.derived.add("operating_income")
    if v.get("total_liabilities") is None:
        eq = v.get("equity_incl_nci") if v.get("equity_incl_nci") is not None else v.get("equity")
        base = v.get("liabilities_and_equity") if v.get("liabilities_and_equity") is not None else v.get("total_assets")
        if eq is not None and base is not None:
            v["total_liabilities"] = base - eq
            row.derived.add("total_liabilities")
    if v.get("goodwill_intangibles") is None and (has("goodwill") or has("intangibles")):
        v["goodwill_intangibles"] = (v.get("goodwill") or 0.0) + (v.get("intangibles") or 0.0)
        row.derived.add("goodwill_intangibles")
    if has("operating_income", "dna"):
        v["ebitda"] = v["operating_income"] + v["dna"]
        row.derived.add("ebitda")
    if has("ocf"):
        v["fcf"] = v["ocf"] - (v.get("capex") or 0.0)
        row.derived.add("fcf")
    # debt
    if v.get("total_debt_reported") is not None:
        v["total_debt"] = v["total_debt_reported"]
    elif v.get("long_term_debt") is not None or v.get("short_term_debt") is not None:
        lt = v.get("long_term_debt") or 0.0
        st = v.get("short_term_debt") or 0.0
        # 'LongTermDebt' (no suffix) already includes current maturities
        if s.get("long_term_debt") in ("LongTermDebt", "LongTermDebtAndCapitalLeaseObligations") and (
            "LongTermDebtCurrent" in s.get("short_term_debt", "")
        ):
            st = 0.0
        v["total_debt"] = lt + st
    if v.get("total_debt") is not None:
        row.derived.add("total_debt")
        if has("cash"):
            v["net_debt"] = v["total_debt"] - v["cash"] - (v.get("short_term_investments") or 0.0)
            row.derived.add("net_debt")
    if has("current_assets", "current_liabilities"):
        v["working_capital"] = v["current_assets"] - v["current_liabilities"]
        row.derived.add("working_capital")
    shares = v.get("shares_outstanding") or v.get("shares_diluted")
    if shares:
        if has("equity"):
            v["bvps"] = v["equity"] / shares
            row.derived.add("bvps")
        if v.get("fcf") is not None:
            v["fcf_per_share"] = v["fcf"] / shares
            row.derived.add("fcf_per_share")
        if v.get("dividends_paid") is not None:
            v["dps_derived"] = v["dividends_paid"] / shares
            row.derived.add("dps_derived")


def _primary_fact(row_facts: dict[str, Fact]) -> Fact | None:
    for k in ROW_ANCHOR_FIELDS:
        if k in row_facts:
            return row_facts[k]
    return next(iter(row_facts.values()), None)


def normalize(cf: dict, today: date | None = None) -> Financials:
    today = today or date.today()
    cik = int(cf.get("cik", 0))
    entity = cf.get("entityName", "")
    warnings: list[str] = []

    duration_fields: dict[str, dict[tuple[str, str | None], Fact]] = {}
    quarter_facts: dict[str, dict[str, Fact]] = {}
    instant_fields: dict[str, dict[str, Fact]] = {}

    for key, spec in FIELD_SPECS.items():
        if spec.kind == DURATION:
            facts = collect_facts(cf, spec)
            if not facts:
                if key in ("revenue", "net_income", "ocf", "eps_diluted"):
                    warnings.append(f"no {spec.label.lower()} facts found")
                continue
            chosen = select_per_period(facts)
            duration_fields[key] = chosen
            quarter_facts[key] = derive_quarters(chosen, spec.no_subtract)
        else:
            if key == "short_term_debt":
                chosen_i = _short_term_debt(cf, spec)
            else:
                facts = collect_facts(cf, spec)
                if key == "shares_outstanding":
                    facts = _aggregate_share_classes(facts)
                if not facts:
                    if key in ("total_assets", "equity", "cash"):
                        warnings.append(f"no {spec.label.lower()} facts found")
                    continue
                chosen_i = {k: f for (k, _), f in select_per_period(facts).items()}
            instant_fields[key] = chosen_i

    # --- fiscal year end month: mode of FY period-end months, most recent wins ties
    fy_keys = [k for field in duration_fields.values() for (k, cls) in field if cls == P.FY]
    fye_month = 12
    if fy_keys:
        counts: dict[int, int] = defaultdict(int)
        latest: dict[int, str] = {}
        for k in fy_keys:
            m = P.key_parts(k)[1]
            counts[m] += 1
            latest[m] = max(latest.get(m, ""), k)
        fye_month = max(counts, key=lambda m: (counts[m], latest[m]))

    # --- annual rows
    annual_keys: set[str] = set()
    for field_key in ROW_ANCHOR_FIELDS:
        for (k, cls) in duration_fields.get(field_key, {}):
            if cls == P.FY:
                annual_keys.add(k)
    annual: list[PeriodRow] = []
    for k in sorted(annual_keys):
        row_facts = {f: chosen[(k, P.FY)] for f, chosen in duration_fields.items() if (k, P.FY) in chosen}
        prim = _primary_fact(row_facts)
        if prim is None:
            continue
        row = PeriodRow(
            key=k, end=prim.end, start=prim.start, fiscal_year=P.fiscal_year_for(k, fye_month),
            fiscal_quarter=None, form=prim.form, filed=max(f.filed for f in row_facts.values()),
        )
        for f, fact in row_facts.items():
            row.values[f] = fact.val
            row.sources[f] = fact.tag
        _attach_instants(row, instant_fields)
        _add_derived(row)
        annual.append(row)

    # --- quarterly rows
    q_keys: set[str] = set()
    for field_key in ROW_ANCHOR_FIELDS:
        q_keys.update(quarter_facts.get(field_key, {}).keys())
    quarterly: list[PeriodRow] = []
    for k in sorted(q_keys):
        row_facts = {f: qf[k] for f, qf in quarter_facts.items() if k in qf}
        prim = _primary_fact(row_facts)
        if prim is None:
            continue
        row = PeriodRow(
            key=k, end=prim.end, start=prim.start, fiscal_year=P.fiscal_year_for(k, fye_month),
            fiscal_quarter=P.fiscal_quarter_for(k, fye_month), form=prim.form,
            filed=max(f.filed for f in row_facts.values()),
        )
        for f, fact in row_facts.items():
            row.values[f] = fact.val
            row.sources[f] = fact.tag
            if fact.derived:
                row.derived.add(f)
        _attach_instants(row, instant_fields)
        _add_derived(row)
        quarterly.append(row)

    ttm = compute_ttm(quarterly, annual, duration_fields, today)

    all_facts = [f for ch in duration_fields.values() for f in ch.values()] + [
        f for ch in instant_fields.values() for f in ch.values()
    ]
    k_filed = [f.filed for f in all_facts if f.form.startswith("10-K")]
    q_filed = [f.filed for f in all_facts if f.form.startswith("10-Q")]
    fin = Financials(
        cik=cik, entity_name=entity, fye_month=fye_month, annual=annual, quarterly=quarterly, ttm=ttm,
        warnings=warnings, latest_10k_filed=max(k_filed) if k_filed else None,
        latest_10q_filed=max(q_filed) if q_filed else None,
        latest_filed=max(k_filed + q_filed) if (k_filed or q_filed) else None,
    )
    if not annual:
        fin.warnings.append("no annual periods could be built")
    return fin


def _attach_instants(row: PeriodRow, instant_fields: dict[str, dict[str, Fact]]) -> None:
    for f, per_key in instant_fields.items():
        fact = per_key.get(row.key)
        if fact is None and f == "shares_outstanding":
            # cover-page share count is dated after period end; accept the next month's fact
            fact = per_key.get(P.key_minus_months(row.key, -1)) or per_key.get(P.key_minus_months(row.key, -2))
        if fact is not None:
            row.values[f] = fact.val
            row.sources[f] = fact.tag


# ----------------------------------------------------------------------------------------------
# step 6: TTM
# ----------------------------------------------------------------------------------------------
def _consecutive(rows: list[PeriodRow]) -> bool:
    for a, b in zip(rows, rows[1:], strict=False):
        if P.key_minus_months(b.key, 3) != a.key:
            return False
    return True


def compute_ttm(
    quarterly: list[PeriodRow],
    annual: list[PeriodRow],
    duration_fields: dict[str, dict[tuple[str, str | None], Fact]],
    today: date,
) -> PeriodRow | None:
    if not quarterly and not annual:
        return None
    last4 = quarterly[-4:] if len(quarterly) >= 4 else []
    latest_annual = annual[-1] if annual else None

    use_annual = False
    if latest_annual and (not last4 or latest_annual.end >= last4[-1].end):
        use_annual = True
    if not use_annual and last4 and not _consecutive(last4):
        use_annual = latest_annual is not None
    if not use_annual and last4 and (today - last4[-1].end).days > 550:
        use_annual = latest_annual is not None

    if use_annual and latest_annual:
        row = PeriodRow(
            key=latest_annual.key, end=latest_annual.end, start=latest_annual.start,
            fiscal_year=latest_annual.fiscal_year, fiscal_quarter=None, form=latest_annual.form,
            filed=latest_annual.filed, values=dict(latest_annual.values), sources=dict(latest_annual.sources),
            derived=set(latest_annual.derived),
        )
        row.derived.add("ttm=annual")
        return row
    if not last4:
        return None

    last = last4[-1]
    row = PeriodRow(
        key=last.key, end=last.end, start=last4[0].start, fiscal_year=last.fiscal_year,
        fiscal_quarter=last.fiscal_quarter, form=last.form, filed=last.filed,
    )
    for field_key, spec in FIELD_SPECS.items():
        if spec.kind != DURATION:
            continue
        vals = [r.values.get(field_key) for r in last4]
        if any(v is None for v in vals):
            continue
        if spec.no_subtract:
            row.values[field_key] = vals[-1]
        else:
            row.values[field_key] = float(sum(vals))  # type: ignore[arg-type]
        row.sources[field_key] = last.sources.get(field_key, "")
        if any(field_key in r.derived for r in last4):
            row.derived.add(field_key)
    # balance sheet: latest quarter that has one
    bal = next((r for r in reversed(quarterly) if r.values.get("total_assets") is not None), None)
    if bal is not None:
        for k, v in bal.values.items():
            if FIELD_SPECS.get(k) and FIELD_SPECS[k].kind == INSTANT and v is not None:
                row.values[k] = v
                row.sources[k] = bal.sources.get(k, "")
    _add_derived(row)
    row.derived.add("ttm=4q")
    return row
