/** Same closed-form two-stage DCF as backend/gufu/metrics/dcf.py, so the panel can recompute locally. */
export function dcfTwoStage(base: number | null, g1: number, g2: number, r: number, n1 = 10, n2 = 10): number | null {
  if (base === null || base <= 0 || r <= -1) return null;
  const x = (1 + g1) / (1 + r);
  const y = (1 + g2) / (1 + r);
  const stage1 = Math.abs(1 - x) < 1e-12 ? base * n1 : (base * x * (1 - Math.pow(x, n1))) / (1 - x);
  const stage2Base = base * Math.pow(x, n1);
  const stage2 = Math.abs(1 - y) < 1e-12 ? stage2Base * n2 : (stage2Base * y * (1 - Math.pow(y, n2))) / (1 - y);
  return stage1 + stage2;
}

export function marginOfSafety(value: number | null, price: number | null): number | null {
  if (value === null || price === null || value <= 0) return null;
  return (value - price) / value;
}
