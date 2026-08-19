# Oracle Cloud Always Free deployment

This guide prepares the ContextIQ FastAPI backend for a small, manually operated Oracle VM. It
does not deploy the Vercel frontend or replace Neon PostgreSQL, Qdrant Cloud, or OpenAI.

## Target and operational constraints

- Oracle Ampere A1 Flex (`aarch64`), Ubuntu 24.04, 1 OCPU, 6 GB RAM, 80 GB boot volume
- CPython 3.12, one Uvicorn worker, systemd, and Caddy
- Neon PostgreSQL, Qdrant Cloud, OpenAI, and the existing Vercel frontend
- `Xenova/ms-marco-MiniLM-L-6-v2` remains the ACCURATE reranker

Python 3.12 is intentional. It has mature Linux ARM64 wheels for the Docling/PyTorch,
ONNX/FastEmbed, and scientific-Python stack, while avoiding Python 3.14 dependency maturity
problems. The repository-level `.python-version`, Ruff, and Mypy all express this target. Local
development may use another supported interpreter temporarily, but production releases must use
3.12.

Always Free capacity is not guaranteed, and Oracle may reclaim instances it classifies as idle.
Keep a documented fallback and monitor Oracle instance events. One OCPU is suitable for a
portfolio workload, but parsing/OCR, evaluation, and local reranking are CPU-bound and may take
noticeably longer than on a paid service. Do not add Uvicorn workers to improve throughput: each
worker can hold its own model state and multiplies memory use.

## VM and network setup

Create the VM manually in the tenancy home region with the target shape, Ubuntu 24.04 ARM64,
and an 80 GB boot volume. Reserve the public IP before DNS cutover. Add an `A` record such as
`api.example.com` for that address.

At both the Oracle NSG/security-list layer and Ubuntu firewall, expose only:

| Port | Purpose | Source |
| --- | --- | --- |
| 22/TCP | SSH | Prefer a fixed administrator CIDR |
| 80/TCP | ACME and HTTPS redirect | Internet |
| 443/TCP | Public API HTTPS | Internet |

Never expose Uvicorn port 8000, PostgreSQL, or Qdrant ports. Uvicorn binds only to loopback.
Use SSH keys, disable SSH password authentication and direct root login, and keep the OS updated.
For example, after confirming key-based access in a second session:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from ADMIN_CIDR to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Replace `ADMIN_CIDR`; do not paste the example literally. Configure `PasswordAuthentication no`
and `PermitRootLogin no` in an SSH server drop-in, validate with `sshd -t`, then reload SSH.

## System packages, identity, and directories

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv git caddy
sudo useradd --system --home /var/lib/contextiq --create-home --shell /usr/sbin/nologin contextiq
sudo install -d -o ubuntu -g contextiq -m 0750 /opt/contextiq/releases
sudo install -d -o root -g contextiq -m 0750 /etc/contextiq
sudo install -d -o contextiq -g contextiq -m 0750 \
  /var/lib/contextiq/cache/huggingface \
  /var/lib/contextiq/cache/docling \
  /var/lib/contextiq/cache/fastembed \
  /var/lib/contextiq/tmp
```

This layout separates concerns:

```text
/opt/contextiq/releases/<commit>/   immutable release checkout and its .venv
/opt/contextiq/current              symlink to the active release
/etc/contextiq/backend.env          secrets and deployment configuration
/var/lib/contextiq/cache/           persistent model/download caches
/var/lib/contextiq/tmp/             ingestion temporary files
```

The application currently lets FastEmbed use Hugging Face downloads when no constructor cache is
specified, and Docling also obtains model artifacts through its supported Hugging Face paths.
Set `HF_HOME=/var/lib/contextiq/cache/huggingface` and
`XDG_CACHE_HOME=/var/lib/contextiq/cache`. The `docling` and `fastembed` subdirectories are
reserved for explicit library cache paths if the application later adopts those supported APIs;
there are no invented `DOCLING_CACHE` or `FASTEMBED_CACHE` environment variables here.

## Production dependency lock and ARM64 check

`backend/requirements.txt` remains the human-maintained input with compatible ranges.
`backend/requirements-prod.txt` is the reviewed, fully pinned production artifact. It captures
the versions validated during deployment preparation without replacing the development workflow.
Change it only as an explicit dependency update, then rerun all checks and validate on Ampere.

Before installing a release, verify that the critical native packages have CPython 3.12 aarch64
wheels. This downloads wheels to a temporary directory and never installs them:

```bash
cd /opt/contextiq/releases/COMMIT/backend
python3.12 scripts/verify_arm64_wheels.py
```

The script checks `torch`, `torchvision`, `onnxruntime`, `numpy`, `scipy`, `opencv-python`,
`tokenizers`, `tiktoken`, `asyncpg`, and `pypdfium2` with `--only-binary=:all:`. If it fails, stop
the release. Do not compile those packages on the 1-OCPU VM; review and update the relevant pin.
The definitive check is a clean install and test run on the actual Ampere VM.

Create the release environment and install only from the production lock:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-prod.txt
.venv/bin/python -m pip check
```

## Environment file

Copy `deploy/oracle/backend.env.example` to `/etc/contextiq/backend.env`, replace every placeholder,
and preserve the application’s actual production tuning values:

```bash
sudo install -o root -g contextiq -m 0640 \
  deploy/oracle/backend.env.example /etc/contextiq/backend.env
sudoedit /etc/contextiq/backend.env
```

Required secrets are `DATABASE_URL`, `QDRANT_API_KEY`, `OPENAI_API_KEY`, and a random
`JWT_SECRET` of at least 32 characters. `DEMO_USER_PASSWORD` is required only if demo-user seeding
is run. Never place these values in source control, shell history, the unit file, or the Caddyfile.

Required deployment values include `APP_ENV=production`, `QDRANT_URL`,
`QDRANT_DOCUMENTS_COLLECTION=ekip_documents`, the exact Vercel origin in `CORS_ORIGINS`, and
`RERANKER_MODEL=Xenova/ms-marco-MiniLM-L-6-v2`. Preserve the existing embedding dimensions and
models, chat/RAGAS models, retrieval threshold, context/token/history limits, upload and chunking
limits, and JWT algorithm/expiry/issuer. `DATABASE_URL` must use `postgresql+asyncpg://`; retain
the Neon TLS query parameters supplied by Neon.

The repository `.env` remains ignored and is not used as the Oracle secret store.

## Temporary upload cleanup

`TMPDIR=/var/lib/contextiq/tmp` makes Python's `NamedTemporaryFile` use the dedicated directory.
Normal ingestion deletes its file in a `finally` block. A hard kill can leave a file behind, so
install the age-based tmpfiles rule:

```bash
sudo install -o root -g root -m 0644 \
  deploy/oracle/contextiq-tmpfiles.conf /etc/tmpfiles.d/contextiq.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/contextiq.conf
```

The `e` rule cleans directory contents only after one day of inactivity. Do not replace it with an
unconditional wildcard removal, which could delete an active upload.

## systemd and Caddy

After `/opt/contextiq/current` points to a prepared release:

```bash
sudo install -o root -g root -m 0644 \
  deploy/oracle/contextiq.service /etc/systemd/system/contextiq.service
sudo systemd-analyze verify /etc/systemd/system/contextiq.service
sudo systemctl daemon-reload
sudo systemctl enable contextiq
```

The service runs as `contextiq`, reads the root-owned environment file, writes only under
`/var/lib/contextiq`, logs to journald, restarts after failure, allows 45 seconds for shutdown, and
runs exactly one worker on `127.0.0.1:8000`.

Replace `api.example.com` in the Caddy template with the real DNS name, then install and validate:

```bash
sudo install -o root -g root -m 0644 deploy/oracle/Caddyfile /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy automatically obtains/renews HTTPS certificates and redirects HTTP to HTTPS. Its standard
`reverse_proxy` supports the chat SSE stream without buffering configuration or API rewrites.

## First release and smoke checks

Use an exact reviewed commit, not a moving branch. The commands below assume the `ubuntu` admin
user owns the releases directory and can read the repository:

```bash
export RELEASE_COMMIT=FULL_REVIEWED_COMMIT_SHA
git clone REPOSITORY_URL "/opt/contextiq/releases/$RELEASE_COMMIT"
cd "/opt/contextiq/releases/$RELEASE_COMMIT"
git checkout --detach "$RELEASE_COMMIT"
cd backend
python3.12 scripts/verify_arm64_wheels.py
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-prod.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest
sudo systemd-run --wait --pipe --collect \
  --unit="contextiq-migrate-$RELEASE_COMMIT" \
  --property=User=contextiq \
  --property=Group=contextiq \
  --property="WorkingDirectory=/opt/contextiq/releases/$RELEASE_COMMIT/backend" \
  --property=EnvironmentFile=/etc/contextiq/backend.env \
  "/opt/contextiq/releases/$RELEASE_COMMIT/backend/.venv/bin/python" -m alembic upgrade head
cd ..
sudo chown -R root:contextiq "/opt/contextiq/releases/$RELEASE_COMMIT"
sudo chmod -R o-rwx "/opt/contextiq/releases/$RELEASE_COMMIT"
sudo ln -sfn "/opt/contextiq/releases/$RELEASE_COMMIT" /opt/contextiq/current
sudo systemctl restart contextiq
```

Do not reuse `RELEASE_COMMIT` for a different checkout. After startup:

```bash
sudo systemctl status contextiq --no-pager
sudo journalctl -u contextiq -n 200 --no-pager
curl --fail --silent --show-error https://api.example.com/health
```

Then run an authenticated login/API smoke test without putting credentials in shell history. From
the UI, verify document listing and one BALANCED query; verify an ACCURATE query initializes and
uses the MiniLM reranker. Only after the backend is stable should Vercel's
`VITE_API_BASE_URL` be changed to the new HTTPS origin and the frontend redeployed. Keep Render
available during the stabilization window. Never run the old and new backends concurrently while
an ingestion task is active because startup recovery treats `PROCESSING` rows as interrupted.

## Updating and rolling back

For each update, repeat the release steps in a new commit-named directory: fetch the exact commit,
run the ARM wheel check, create its venv, install the lock, run tests and `pip check`, run Alembic
through a transient systemd unit that loads `/etc/contextiq/backend.env`, atomically switch
`current`, restart, and check systemd, journald, `/health`,
login, and an authenticated API request. Retain at least one known-good release.

For a compute-only rollback:

```bash
sudo ln -sfn /opt/contextiq/releases/PREVIOUS_COMMIT /opt/contextiq/current
sudo systemctl restart contextiq
sudo systemctl status contextiq --no-pager
curl --fail --silent --show-error https://api.example.com/health
```

Verify login plus one BALANCED and one ACCURATE query. If the frontend had already been cut over
and the Oracle backend is unavailable, restore the previous Render API value for
`VITE_API_BASE_URL` and redeploy the frontend. Do not roll back Neon or Qdrant for a compute-only
release. A future migration requires its own forward/backward compatibility and rollback plan.

## Operations and troubleshooting

- Follow logs with `sudo journalctl -u contextiq -f`; inspect prior boots with `-b -1`.
- `/health` returns unhealthy when Neon or Qdrant is unavailable; test both DNS and TLS connectivity.
- Check memory and disk with `systemctl status contextiq`, `free -h`, and `df -h`. Model caches and
  release venvs need periodic capacity review.
- A first PDF or ACCURATE request may download and initialize models. Confirm that `HF_HOME` is
  writable by `contextiq` and that subsequent requests reuse `/var/lib/contextiq/cache`.
- If a native package starts compiling, stop it and rerun the wheel verifier. Do not install a
  compiler toolchain as a workaround for a missing heavy wheel.
- If Caddy cannot issue a certificate, confirm public DNS points to the reserved IP and ports 80/443
  are open in both Oracle and UFW.
- If systemd reports a permission error, verify release traversal permissions, environment-file
  group/mode, and ownership of `/var/lib/contextiq`.
- If Oracle reports capacity unavailable, retry later or another availability domain when allowed.
  If Oracle reports idle reclamation, restore from the documented release and secret backups or use
  the Render rollback path.

Before production cutover, validate the clean locked install, imports, full backend tests, one
document of every supported format, BALANCED Hybrid RRF, and ACCURATE reranking on the actual A1
host. Also observe peak RSS, cold model-download time, ingestion latency, SSE behavior through
Caddy, restart recovery, and boot-time service startup.
