"""Price history container + parsers for Yahoo chart JSON and Stooq CSV."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta


@dataclass
class PriceHistory:
    symbol: str
    currency: str
    dates: list[str]  # ISO dates
    close: list[float]
    adjclose: list[float]
    volume: list[int]
    meta: dict = field(default_factory=dict)  # price, prev_close, high52, low52, as_of

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> PriceHistory:
        return cls(d["symbol"], d.get("currency", "USD"), d["dates"], d["close"], d.get("adjclose") or d["close"],
                   d.get("volume") or [0] * len(d["dates"]), d.get("meta") or {})

    @property
    def last_price(self) -> float | None:
        if self.meta.get("price") is not None:
            return float(self.meta["price"])
        return self.close[-1] if self.close else None

    def fill_meta_from_series(self) -> None:
        if not self.close:
            return
        last_d = date.fromisoformat(self.dates[-1])
        cutoff = (last_d - timedelta(days=365)).isoformat()
        window = [c for d, c in zip(self.dates, self.close, strict=False) if d >= cutoff]
        self.meta.setdefault("price", self.close[-1])
        self.meta.setdefault("prev_close", self.close[-2] if len(self.close) > 1 else self.close[-1])
        self.meta.setdefault("high52", max(window))
        self.meta.setdefault("low52", min(window))
        self.meta.setdefault("as_of", self.dates[-1])


def parse_yahoo_chart(data: dict, symbol: str) -> PriceHistory:
    chart = data.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart: empty result")
    res = results[0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    quote = (res.get("indicators", {}).get("quote") or [{}])[0]
    adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or quote.get("close") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    dates: list[str] = []
    c_out: list[float] = []
    a_out: list[float] = []
    v_out: list[int] = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        dates.append(datetime.fromtimestamp(t, tz=UTC).date().isoformat())
        c_out.append(round(float(c), 4))
        a = adj[i] if i < len(adj) and adj[i] is not None else c
        a_out.append(round(float(a), 4))
        v = vols[i] if i < len(vols) and vols[i] is not None else 0
        v_out.append(int(v))
    ph = PriceHistory(symbol=symbol, currency=meta.get("currency", "USD"), dates=dates, close=c_out, adjclose=a_out,
                      volume=v_out)
    if meta.get("regularMarketPrice") is not None:
        ph.meta["price"] = float(meta["regularMarketPrice"])
    pc = meta.get("previousClose", meta.get("chartPreviousClose"))
    if pc is not None:
        ph.meta["prev_close"] = float(pc)
    if meta.get("fiftyTwoWeekHigh") is not None:
        ph.meta["high52"] = float(meta["fiftyTwoWeekHigh"])
    if meta.get("fiftyTwoWeekLow") is not None:
        ph.meta["low52"] = float(meta["fiftyTwoWeekLow"])
    if meta.get("regularMarketTime"):
        ph.meta["as_of"] = datetime.fromtimestamp(meta["regularMarketTime"], tz=UTC).isoformat()
    if meta.get("longName") or meta.get("shortName"):
        ph.meta["name"] = meta.get("longName") or meta.get("shortName")
    ph.fill_meta_from_series()
    return ph


def parse_stooq_csv(text: str, symbol: str) -> PriceHistory:
    if not text or text.strip().lower().startswith("no data") or "Date" not in text[:200]:
        raise ValueError("Stooq: no data")
    reader = csv.DictReader(io.StringIO(text))
    dates, closes, vols = [], [], []
    for row in reader:
        try:
            c = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue
        dates.append(row["Date"])
        closes.append(c)
        try:
            vols.append(int(float(row.get("Volume") or 0)))
        except ValueError:
            vols.append(0)
    if not closes:
        raise ValueError("Stooq: empty series")
    ph = PriceHistory(symbol=symbol, currency="USD", dates=dates, close=closes, adjclose=list(closes), volume=vols)
    ph.fill_meta_from_series()
    return ph


RANGE_DAYS = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "max": None}


def slice_range(ph: PriceHistory, rng: str, today: date | None = None) -> tuple[list[str], list[float], list[int]]:
    today = today or (date.fromisoformat(ph.dates[-1]) if ph.dates else date.today())
    if rng == "ytd":
        cutoff = date(today.year, 1, 1).isoformat()
    else:
        days = RANGE_DAYS.get(rng, None)
        cutoff = (today - timedelta(days=days)).isoformat() if days else "0000-00-00"
    idx = [i for i, d in enumerate(ph.dates) if d >= cutoff]
    return [ph.dates[i] for i in idx], [ph.close[i] for i in idx], [ph.volume[i] for i in idx]


def downsample(dates: list[str], closes: list[float], vols: list[int], max_points: int = 1500):
    n = len(dates)
    if n <= max_points:
        return dates, closes, vols, False
    stride = -(-n // max_points)  # ceil
    idx = list(range(0, n, stride))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return [dates[i] for i in idx], [closes[i] for i in idx], [vols[i] for i in idx], True
