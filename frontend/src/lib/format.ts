export function fmtMoney(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(digits)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(digits)}K`;
  return `${sign}$${a.toFixed(digits)}`;
}

export function fmtCompact(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e12) return `${sign}${(a / 1e12).toFixed(digits)}T`;
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(digits)}K`;
  return `${sign}${a.toFixed(digits)}`;
}

export function fmtPct(v: number | null | undefined, digits = 2, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  const s = (v * 100).toFixed(digits) + "%";
  return signed && v > 0 ? `+${s}` : s;
}

export function fmtRatio(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  if (Math.abs(v) >= 1000) return v.toFixed(0);
  return v.toFixed(digits);
}

export function fmtPrice(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  return Math.round(v).toString();
}

export function fmtMetric(fmt: string, v: number | null | undefined, decimals = 2): string {
  switch (fmt) {
    case "pct": return fmtPct(v, decimals);
    case "money": return fmtMoney(v);
    case "price": return fmtPrice(v, decimals);
    case "int": return fmtInt(v);
    case "score": return fmtRatio(v, 2);
    default: return fmtRatio(v, decimals);
  }
}

export function fmtDate(s: string | null | undefined): string {
  if (!s) return "N/A";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function changeClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "muted";
  return v > 0 ? "up" : v < 0 ? "down" : "text-2";
}
