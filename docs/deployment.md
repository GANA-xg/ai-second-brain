# CI/CD & Deployment

Three GitHub Actions pipelines take a commit from pull request to production.
Nothing is deployed by hand.

| Workflow | File | Trigger | What it does |
| --- | --- | --- | --- |
| **CI** | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | PR to `main`/`develop`, push to those branches | Lint + migrate + pytest against real Postgres/Redis/Qdrant containers; frontend lint, typecheck, build |
| **Build** | [`.github/workflows/build.yml`](../.github/workflows/build.yml) | Push to `main` | Builds backend + frontend images, pushes to GHCR tagged with the commit SHA |
| **Deploy** | [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) | Build success on `main`, or manual dispatch | SSHes to the GCP VM, pulls images, migrates, health-checks, rolls back on failure |

```
PR ──► CI (must be green to merge)
        │
   merge to main
        │
        ▼
      Build ──► ghcr.io/<owner>/ai-second-brain/{backend,frontend}:<commit-sha>
        │
        ▼
      Deploy ──► GCP VM ──► health check ──► ✅ record tag
                                └─ ❌ ──► roll back to previous tag
```

---

## Image tagging

Every image is tagged with the **full commit SHA** plus a `sha-<short>` alias.
There is deliberately **no `latest` tag**: with `latest`, "what is running in
production?" has no reliable answer. With SHA tags, the running tag *is* the
answer, and rolling back is just naming an older one.

Images stay in GHCR until they are explicitly deleted. If you want the
30-day window the roadmap assumes, configure it under
**Settings → Packages → <package> → Retention policy** — otherwise the full
history is kept, which is strictly better for rollback.

---

## Required GitHub secrets

**Settings → Secrets and variables → Actions → Secrets**

| Secret | Used by | Notes |
| --- | --- | --- |
| `GCP_SSH_KEY` | Deploy | Private SSH key (full PEM, including header/footer) for the deploy user |
| `GCP_SSH_HOST` | Deploy | VM public IP or hostname |
| `GCP_SSH_USER` | Deploy | Linux user on the VM; must be in the `docker` group |
| `GCP_SSH_KNOWN_HOSTS` | Deploy | *Optional but recommended.* Output of `ssh-keyscan -H <host>`. Without it the workflow falls back to trust-on-first-use and logs a warning |
| `POSTGRES_PASSWORD` | Deploy | Production database password |
| `JWT_SECRET_KEY` | Deploy | Written to the VM as the app's `SECRET_KEY` (it signs JWTs — hence the name). Generate with `openssl rand -hex 32` |
| `GEMINI_API_KEY` | Deploy | Gemini provider key |
| `OPENROUTER_API_KEY` | Deploy | OpenRouter provider key (the default `LLM_PROVIDER`) |

`GITHUB_TOKEN` is provided automatically — no PAT is needed for GHCR.

### Repository variables (non-secret)

**Settings → Secrets and variables → Actions → Variables**

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_URL` | — | Public URL, shown on the Deploy job in the Actions UI |
| `HEALTH_CHECK_URL` | `http://localhost/api/v1/health/` | Checked from *inside* the VM after deploy. Set to `https://yourdomain.com/api/v1/health/` once TLS is terminated, to also validate the public path |
| `DEPLOY_DIR` | `/opt/ai-second-brain` | Deploy directory on the VM |
| `NEXT_PUBLIC_API_URL` | `/api/v1` | Baked into the frontend image at build time |

### Secret hygiene

- Secrets are written to the VM's `.env` (mode `600`) via `scp`, never passed
  as shell arguments and never printed.
- The GHCR login on the VM uses `--password-stdin`.
- **Never `echo $SECRET` in a workflow step.** GitHub redacts exact matches in
  logs, but redaction fails on transformed values (base64, JSON-encoded,
  substrings) — do not rely on it.

---

## One-time VM bootstrap

On the GCP VM, as the deploy user:

```bash
# 1. Docker + compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker

# 2. Deploy directory owned by the deploy user
sudo mkdir -p /opt/ai-second-brain/{nginx,scripts}
sudo chown -R "$USER:$USER" /opt/ai-second-brain

# 3. Authorize the CI deploy key
cat >> ~/.ssh/authorized_keys   # paste the PUBLIC half of GCP_SSH_KEY
chmod 600 ~/.ssh/authorized_keys
```

Everything else — `docker-compose.prod.yml`, `nginx/nginx.conf`,
`scripts/deploy_remote.sh`, and `.env` — is pushed by the Deploy workflow on
every run, so the VM never drifts from the repo.

The first deploy has no previous tag recorded, so a failed first deploy cannot
auto-roll-back; it leaves the stack up for inspection and fails the job.

---

## Blocking merges on red CI

Workflow files alone do not block merges — branch protection does.

**Settings → Branches → Add branch protection rule** for `main`:

1. ✅ Require a pull request before merging
2. ✅ Require status checks to pass before merging
3. Add the required checks: **`Backend tests`** and **`Frontend build`**
4. ✅ Require branches to be up to date before merging

To verify it works, open a PR that intentionally breaks a test (e.g. flip an
assertion in `backend/tests/test_integration_smoke.py`) and confirm the merge
button is disabled.

### Requiring approval before deploy

The Deploy job runs in the `production` GitHub Environment. Under
**Settings → Environments → production**, add yourself as a **required
reviewer** to make every deploy wait for a click, and restrict the environment
to the `main` branch.

---

## Rollback

**Target: under 5 minutes.**

The pipeline rolls back automatically: if the post-deploy health check fails,
`scripts/deploy_remote.sh` re-deploys the previously recorded tag from
`/opt/ai-second-brain/.deployed_tag` and re-runs the health check.

To roll back manually:

1. Find the last-known-good commit SHA — `git log --oneline main`, or the
   Deploy workflow's run history, or `/opt/ai-second-brain/deploy.log` on the VM.
2. **Actions → Deploy → Run workflow**.
3. Paste the full 40-character SHA into `image_tag`, run it.
4. Approve the `production` environment prompt if reviewers are configured.
5. The workflow pulls that SHA's images, migrates, health-checks, and records it.

Total time is dominated by the image pull (~1–2 min on a warm VM).

### ⚠️ Migrations are not rolled back

Rollback reverts **application code only**. Alembic migrations already applied
stay applied. If the bad release included a destructive migration, roll back
the code first (above), then downgrade the schema by hand:

```bash
ssh <user>@<host>
cd /opt/ai-second-brain
docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
  alembic downgrade -1
```

This is the main reason to prefer additive, backward-compatible migrations:
add columns before the code needs them, drop them a release *after* the code
stops using them.

---

## Deployment log

Every attempt appends a tab-separated line to `/opt/ai-second-brain/deploy.log`:

```
2026-08-02T14:31:07Z	success	9b3f5d5...	GANA-xg
2026-08-02T15:02:44Z	rolled-back-to-9b3f5d5...	a1c2e4f...	GANA-xg
```

Columns: timestamp (UTC), result, image tag, who triggered it. The same
information — plus the trigger type — is written to the GitHub Actions job
summary for each Deploy run.

---

## Tightening the lint gate

[`backend/ruff.toml`](../backend/ruff.toml) currently selects only the
"almost certainly a bug" rules (`E9`, `F63`, `F7`, `F82`), which the codebase
passes cleanly. The broader rule set reports ~700 style violations, most of
them auto-fixable.

To roll them in without one enormous commit, enable one rule family at a time:

```bash
cd backend
ruff check . --select I --statistics    # see the damage for import sorting
ruff check . --select I --fix           # fix it
# then add "I" to the `select` list in ruff.toml and commit
```

Suggested order: `I` (import sorting) → `F401` (unused imports) → `UP`
(pyupgrade) → `B` (bugbear). Each is a self-contained, reviewable PR.
