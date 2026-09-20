# Running Bulwark

Bulwark is one Python process with a SQLite file. There is no cluster, no message queue and no
external database.

## Options

**On a workstation.** `./start.sh` (or `start.bat`). It creates the virtual environment, installs
what is missing, builds the web interface and serves everything on <http://127.0.0.1:8800>. Good
for one person doing the work.

**On a small server with Docker.** `docker compose up --build`. Data lives in a named volume
mounted at `/data`. The compose file binds to `127.0.0.1` on purpose; put a reverse proxy in front
if others need access.

**As a service.** Any process manager works. A systemd unit:

```ini
[Unit]
Description=Bulwark
After=network.target

[Service]
User=bulwark
WorkingDirectory=/opt/bulwark/backend
Environment=BULWARK_DATA_DIR=/var/lib/bulwark
Environment=BULWARK_ADMIN_PASSWORD=<choose one>
Environment=BULWARK_SERVER_URL=https://bulwark.example
ExecStart=/opt/bulwark/.venv/bin/python -m uvicorn bulwark.main:app --host 127.0.0.1 --port 8800
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Settings

Every setting is an environment variable prefixed `BULWARK_`.

| Variable | Default | What it does |
|---|---|---|
| `BULWARK_DATA_DIR` | `backend/data` | Database, evidence files, generated secrets |
| `BULWARK_ADMIN_PASSWORD` | generated | The sign-in password |
| `BULWARK_SECRET` | generated | Session cookie signing key |
| `BULWARK_HOST` / `BULWARK_PORT` | `127.0.0.1` / `8800` | Where to listen |
| `BULWARK_SERVER_URL` | request URL | The URL agents report to, if it differs |
| `BULWARK_EVIDENCE_TTL_DAYS` | `30` | How long agent-collected evidence stays current |
| `BULWARK_AUTO_POAM` | `true` | Open a plan-of-action item for a new failing check |
| `BULWARK_CATALOG_PATH` | `catalog/cmmc_l2_catalog.json` | The requirement catalog |

Generated secrets are written to `admin_password.txt` and `secret.key` in the data directory with
owner-only permissions on first start.

## Putting it on a network

Bulwark listens on localhost by default. If agents on other machines must reach it, terminate TLS
at a reverse proxy and forward to the process. With Caddy:

```
bulwark.example {
    reverse_proxy 127.0.0.1:8800
}
```

With nginx, forward `X-Forwarded-Proto` and set `BULWARK_SERVER_URL` so the enrollment page prints
the right address. Use a real certificate: `--insecure` on the agents exists for a self-signed
certificate on a trusted network and warns every time it runs.

## Backups

Back up the whole data directory. It contains:

```
bulwark.db           every requirement record, plan of action item, asset, provider, report
evidence/            the files you uploaded
secret.key           session signing key
admin_password.txt   only when one was generated
```

This is your compliance record and part of what you would hand to an assessor. Copy it somewhere
off the machine, on a schedule, and test restoring it. (Requirement 3.8.9 asks you to protect
backups, and an assessor may well ask about the backup of the compliance system itself.)

SQLite runs in WAL mode, so copy `bulwark.db`, `bulwark.db-wal` and `bulwark.db-shm` together, or
stop the service first.

## Upgrading

Pull, then `make setup && make build`. New columns are created on start. The requirement catalog is
a built artifact committed to the repository: if you change anything under `catalog/enrichment/`,
run `make catalog` and commit the result. `make test` checks the catalog is in sync.
