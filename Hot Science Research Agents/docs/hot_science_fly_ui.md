# DeepGreen Hot Science Fly.io Pilot

This deploys the FastAPI + React Hot Science pilot as one Fly Machine with one Fly Volume. It is suitable for internal pilot feedback, not production high availability.

## What Runs

- Backend: FastAPI at `0.0.0.0:8080`
- Frontend: React/Vite build served by the backend
- Primary output: downloadable Word `.docx`
- Persistence: SQLite and generated artifacts under `/data/hot_science`
- Auth: seven pilot users configured by Fly secrets
- UI source default: blank source field, which runs every enabled source in `config/hot_science_sources.yaml`

## Local Build Check

```bash
cd "Hot Science Research Agents"
npm run build --prefix web/frontend
python -m pytest tests/ -q
docker build -t deepgreen-hot-science .
docker run --rm -p 8080:8080 \
  -e DEEPGREEN_UI_USERS_JSON='{"user1":"<password1>","user2":"<password2>","user3":"<password3>","user4":"<password4>","user5":"<password5>","user6":"<password6>","user7":"<password7>"}' \
  -e DEEPGREEN_UI_SESSION_SECRET='<long-random-secret>' \
  deepgreen-hot-science
```

Then open `http://127.0.0.1:8080/health`.

## First Fly Setup

Install and authenticate `flyctl`, then run from the repo root:

```bash
cd "Hot Science Research Agents"
fly launch --no-deploy --copy-config
```

If Fly asks to overwrite `fly.toml`, do not overwrite it unless you intentionally want a new app name. Edit `app = "deepgreen-hot-science"` in `fly.toml` if the app name is already taken.

Create one pilot volume in the same region as `primary_region`:

```bash
fly volumes create hot_science_data --region iad --size 10
```

## Required Secrets

Set user credentials and a stable session signing secret as Fly secrets. Do not commit these values to the repo.

```bash
fly secrets set \
  DEEPGREEN_UI_USERS_JSON='{"user1":"<password1>","user2":"<password2>","user3":"<password3>","user4":"<password4>","user5":"<password5>","user6":"<password6>","user7":"<password7>"}' \
  DEEPGREEN_UI_SESSION_SECRET='<long-random-secret>'
```

Optional source/API secrets:

```bash
fly secrets set \
  DEEPGREEN_CONTACT_EMAIL='<team-email>' \
  OPENALEX_MAILTO='<team-email>' \
  CROSSREF_MAILTO='<team-email>' \
  UNPAYWALL_EMAIL='<team-email>' \
  SEMANTIC_SCHOLAR_API_KEY='<optional-key>' \
  NCBI_API_KEY='<optional-key>' \
  CORE_API_KEY='<optional-key>' \
  SPRINGER_NATURE_API_KEY='<optional-key>' \
  ELSEVIER_API_KEY='<optional-key>' \
  SCOPUS_API_KEY='<optional-key>'
```

Only set Bedrock/AWS secrets if you enable `HOT_SCIENCE_ENABLE_BEDROCK_EMBEDDINGS=1` or later route the pilot through AWS services.

## Deploy

```bash
fly deploy
fly status
fly logs
```

After deploy, visit:

```bash
fly open
```

Health check:

```bash
fly ssh console -C "python - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read().decode())
PY"
```

## Persistence Check

Artifacts and SQLite should write below `/data/hot_science`. To inspect:

```bash
fly ssh console -C "find /data/hot_science -maxdepth 3 -type f | sort | tail -50"
```

Fly Volumes are local to a Machine/region. For this pilot, keep one Machine attached to one volume. Do not scale horizontally without moving run state and artifacts to shared storage.

## Pilot Limitations

- One Machine and one Volume are intentionally simple, not high availability.
- If the Machine or volume region changes, volume attachment must be handled deliberately.
- Normal users can download the primary Word report only.
- Admin/debug users can see JSON, Markdown, review CSV, source CSV, and hidden run history.
- Generated artifacts expire based on `HOT_SCIENCE_REPORT_RETENTION_DAYS`.
- PDF output is deferred until conversion reliability is confirmed.

## Path to AWS Production

After Hot Science team feedback, move auth to Cognito or the BEF identity provider, artifacts to S3, run metadata to DynamoDB/Postgres, orchestration to Bedrock AgentCore or the approved DeepGreen runtime, and retrieval/knowledge services to the AWS DeepGreen account. Keep `config/hot_science_sources.yaml` as the editable source inventory during the migration.
