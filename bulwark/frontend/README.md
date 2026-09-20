# Bulwark frontend

Vite + React 19 + TypeScript, talking to the FastAPI backend at `/api`.

```bash
npm install
npm run dev        # http://localhost:5173, proxying /api to http://127.0.0.1:8800
npm run typecheck
npm run build      # -> dist/, which the backend serves at /
```

## Routes

| Path | Page |
|---|---|
| `/login` | Password sign-in |
| `/setup` | First-run wizard: organization, then the first system |
| `/` | Readiness dashboard: SPRS score, contradictions, family progress, next actions |
| `/controls`, `/controls/:id` | All 110 requirements; detail with guidance, objectives, evidence, checks |
| `/poam`, `/poam/new`, `/poam/:id` | Plan of action register, creation and the remediation workflow |
| `/evidence` | Evidence library: upload, link, download, expiry |
| `/assets` | Inventory with CMMC asset categories and per-asset check results |
| `/providers`, `/providers/:id` | Service providers and the 110-row responsibility matrix |
| `/agents` | Enrollment, install commands, agent health, failing checks |
| `/reports` | SSP, POA&M and readiness report exports, plus score history |
| `/settings` | Organization and system details, demo data, activity log |

## Colour

Status colour follows a validated palette (green, amber, blue, red, grey) checked for
colour-blind separation. Amber sits below 3:1 contrast on a light surface by design, so every
status is paired with an icon and a text label and the same numbers are always available as a
table. No chart uses two y-axes.
