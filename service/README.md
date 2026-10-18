# camOS Snapshot processor

Standalone, request-driven Snapshot worker for Cloud Run and Cloud Tasks. Download
this directory alone; it contains all application code. No Analyse imports, model
files, GitHub access, JSON service-account keys, database migrations or watcher are
required. The application runs as `processor@camosbase.iam.gserviceaccount.com`.

## Behaviour

`POST /tasks/snapshot` accepts only `{"organisation_id": 1}` (positive signed-64-bit
integer, not a boolean/string/float; 1 KiB body limit). Cloud Run IAM authenticates
requests; caller-supplied Cloud Tasks headers are not proof of identity. Do not
expose this image on an unauthenticated service. `GET /health` checks process
health only and does not contact Google Cloud or Postgres.

Every request obtains a dedicated direct SQL connection, nonblockingly takes the
organisation's session advisory lock, then performs read-only prerequisite checks
and reads the **actual persisted** organisation snapshot timestamp. The very same
physical session is used throughout calculation and atomic persistence. It is
never pooled or reconnected. Session locks survive the existing early read commit
and optimistic conflict rollbacks; all resources close after the response's work.

| Condition | HTTP status / outcome |
|---|---|
| Committed calculation, or genuine all-`NO_OP` | 200 / `completed` |
| Persisted timestamp younger than configured interval | 200 / `fresh` |
| Organisation does not exist | 200 / `organisation_missing` |
| Organisation has no sites | 200 / `no_sites` |
| Organisation snapshot row absent | 200 / `organisation_snapshot_missing` |
| Any connected site's snapshot row absent | 200 / `site_snapshot_missing` |
| Prerequisites removed between admission and execution | 200 / `missing_prerequisite` |
| Lock held by another request | 503 / `busy` |
| Bad body or ID | 400 / `invalid_request` (oversized body: 413) |
| SQL, IAM, BigQuery, malformed state, invalid timestamp or calculation failure | 503 / `failed`; details only in server logs |

**No calculation, BigQuery query, snapshot update or row creation occurs for the
four intentional missing-prerequisite cases.** Only lightweight SQL reads and lock
management are done. Missing rows are not fabricated. A narrow internal exception
represents these skips; query/permission/calculation failures are not converted to
skips. A prerequisite disappearing during later optimistic persistence remains a
genuine retryable failure; no partially written site snapshot is committed.

Public Python API: run from this directory and `from snapshot import Snapshot`.
`Snapshot(organisation_id)` is synchronous, returns `True` for successful/all-no-op
work, returns `False` for missing prerequisites, and raises genuine errors. Direct
calls use the same execution guard but deliberately do not apply HTTP cooldown.
Lock contention raises. The worker invokes the internal same-connection execution
path instead of calling a public facade that would open another session.

### Timestamp policy

Default `SNAPSHOT_REFRESH_INTERVAL_MINUTES=30`. Comparisons are UTC. A timestamp
exactly 30 minutes old is due. Null, non-datetime, naive or future-dated persisted
timestamps fail without calculation and result in retryable HTTP failure. Repair
bad data/clock configuration through normal operations; the service neither
manufactures state nor silently reports success. Missing rows are intentional
skips instead. A fresh timestamp does not bypass missing-row checks.

The existing `ts` denotes **calculation time**, not commit time. A 12:00 calculation
committed at 12:20 is next due at 12:30. This implementation preserves that meaning;
it does not promise a full 30-minute wait after completion. A genuine all-no-op can
return `True` without changing `ts`, as before. Normally later `TIME_ONLY` calls
advance both site and organisation timestamps even without new events.

### Concurrency and failure limits

Reserve negative single-bigint advisory keys in this database for Snapshot: key
`-organisation_id`. Verify this namespace is unused by other applications before
deployment. All cooperating production Snapshot callers/revisions must use this
protocol. Distinct IDs use distinct keys. Optimistic `updated_at` predicates and
atomic site/organisation writes remain intact (three total conflict attempts).
The original source queries, classifications, reducers, UTC reporting, disabled
source treatment, rounding and state/payload representations are unchanged.

If the SQL backend is lost, the old worker cannot commit through a replacement
connection; connection errors propagate. Residual CPU/BigQuery work can briefly
overlap a new holder after PostgreSQL detects session loss. Advisory locks cannot
prove instantaneous CPU cancellation under network partitions. The service does
not reconnect or steal locks on a timer. A lost response after successful commit
is handled by durable freshness on redelivery. Existing unguarded callers and
configuration changes outside this protocol still require operational care.

## Configuration

| Environment variable | Default |
|---|---|
| `SNAPSHOT_REFRESH_INTERVAL_MINUTES` | `30`, positive integer |
| `GOOGLE_CLOUD_PROJECT` | `camosbase` |
| `CLOUD_SQL_INSTANCE` | `camosbase:europe-west2:camos-prod-postgres` |
| `CLOUD_SQL_DATABASE` | `camos_prod` |
| `PROCESSOR_SERVICE_ACCOUNT` | `processor@camosbase.iam.gserviceaccount.com` |
| `CLOUD_SQL_IP_TYPE` | `PUBLIC`; alternatively `PRIVATE` with network routing |
| `BIGQUERY_LOCATION` | unset; confirm actual dataset location before deployment |
| `PORT` | supplied by Cloud Run; image default `8080` |

ADC uses the assigned runtime identity. The IAM database user derived from the
default email is `processor@camosbase.iam`; a mismatched assigned identity fails
authentication. No `GOOGLE_APPLICATION_CREDENTIALS` key path is required. Cloud SQL
Connector uses lazy refresh for serverless execution and IAM database login. The
canonical source remains `camosbase.camos_prod.events`; tasks cannot choose tables.

Gunicorn runs one synchronous worker, one thread, with a hard 1,500-second timeout.
Use Cloud Run timeout 1,740 seconds and task dispatch deadline 1,800 seconds. The
worker process is terminated if work exceeds its bound, closing its SQL session;
do not replace it with unbounded background threads. No success is acknowledged
before work finishes. There is no new cooperative cancellation inside reducers or
event queries, preserving their behaviour. Hard termination does not necessarily
cancel a remote BigQuery job already submitted. There can be an ambiguous commit
at termination/network loss; redelivery checks persisted state. Cloud Tasks' HTTP
deadline maximum is 30 minutes; it does not itself stop worker code. Benchmark
worst expected rebuilds in staging: consistent timeout or OOM is a release blocker,
not a reason to repeatedly retry unbounded work.

## Local tests and independent build

From this directory (no parent repository needed):

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
docker build -t camos-snapshot:local .
docker run --rm -p 8080:8080 camos-snapshot:local
# In another terminal: curl --fail http://localhost:8080/health
```

`requirements.txt` pins direct dependencies and applies `requirements.lock` as
constraints for the complete tested dependency set (Python 3.12/Linux). Regenerate
the lock in a clean virtual environment when intentionally updating dependencies.
The base image is digest-pinned. Behind a TLS-inspecting build proxy, pass a trusted
CA bundle as `docker build --secret id=build_ca,src=/path/to/ca-bundle .` and use the
supported Docker proxy configuration; TLS verification is never disabled. The
optional CA is build-only and is not retained in the image.

Routine tests require no GCP access/keys. Seven integration tests skip unless a
disposable **local** PostgreSQL fixture is enabled. They create/drop fixture data
only inside database `snapshot_test`; never use a production database:

```sh
docker run -d --name snapshot-test-postgres \
  -e POSTGRES_PASSWORD=snapshot-local-test-only -e POSTGRES_DB=snapshot_test \
  -p 127.0.0.1:55432:5432 postgres:16-bookworm
docker exec snapshot-test-postgres pg_isready
SNAPSHOT_TEST_POSTGRES_PORT=55432 python -m unittest discover -s tests -v
docker rm -f snapshot-test-postgres
```

These real PostgreSQL tests cover atomic rollback after a site write and an
organisation conflict; lock retention across commit/rollback; distinct keys;
release after errors; backend termination with no reconnect; missing prerequisite
skips; real timestamp advancement and duplicate delivery. They supplement, rather
than replace, offline mocks. The 28 original calculation tests live here; the root
repository test file delegates to them. Root `test.py` remains an explicit manual
cloud-connected driver and must not be executed as a routine test.

## Manual Google Cloud setup (examples; not executed by implementation)

First confirm the exact base's schema: `enabled` fields on organisations/sites/
devices; `ts`, `state`, `payload`, `updated_at` on provisioned snapshot rows; valid
positive capacities; unique organisation/site snapshot identities; timezone-aware
timestamps; and event ownership columns in the canonical table. Newer repository
revisions use different schemas. This implementation is based on commit
`3f2db061bf14eb10867a668c29815eb01c410d6f`, not newer `main`.

Confirm dataset location, SQL IAM authentication, IP topology, Postgres role
privileges, connection budget and unused advisory-lock key namespace. Public IP
must be reachable by the Connector; private IP additionally requires configured
Direct VPC egress/VPC connector and routing. The Connector does not create routes.
The commands below assume the supported public-IP path. Do not run them unchanged
against a private-only instance.

### Resource and IAM setup

Run as an authorised deployment administrator in Cloud Shell. Existing resources
should be verified/reused rather than recreated; avoid project Owner grants.

```sh
export PROJECT=camosbase REGION=europe-west2
export SERVICE=camos-snapshot QUEUE=camos-snapshot
export PROCESSOR=processor@camosbase.iam.gserviceaccount.com
export INVOKER=snapshot-task-invoker@camosbase.iam.gserviceaccount.com
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudtasks.googleapis.com \
  sqladmin.googleapis.com bigquery.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# Only if these service accounts do not already exist:
gcloud iam service-accounts create processor --display-name='camOS Processor'
gcloud iam service-accounts create snapshot-task-invoker --display-name='Snapshot task invoker'

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$PROCESSOR" --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$PROCESSOR" --role=roles/cloudsql.instanceUser
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$PROCESSOR" --role=roles/bigquery.jobUser

# Confirm cloudsql.iam_authentication=on. If disabled, plan the flag change with
# the database operator; do not blindly replace existing flags or restart prod.
gcloud sql instances describe camos-prod-postgres
# Only if the Cloud IAM database user is not already provisioned:
gcloud sql users create processor@camosbase.iam \
  --instance=camos-prod-postgres --type=cloud_iam_service_account
```

An authorised BigQuery administrator must grant `roles/bigquery.dataViewer` on the
events table (prefer table scope; dataset scope only if accepted). For example,
with Terraform-free SQL DCL through `bq`, using the **confirmed dataset location**:

```sh
export BQ_LOCATION=EU  # example only: replace with actual dataset location
bq --location="$BQ_LOCATION" query --use_legacy_sql=false \
  'GRANT `roles/bigquery.dataViewer` ON TABLE `camosbase.camos_prod.events` TO "serviceAccount:processor@camosbase.iam.gserviceaccount.com"'
```

An authorised database administrator executes these grants in `camos_prod` (they
grant access, not schema changes). Confirm any RLS policies and triggers separately:

```sql
GRANT CONNECT ON DATABASE camos_prod TO "processor@camosbase.iam";
GRANT USAGE ON SCHEMA public TO "processor@camosbase.iam";
GRANT SELECT ON public.organisations, public.sites, public.devices,
  public.site_snapshots, public.organisation_snapshots TO "processor@camosbase.iam";
GRANT UPDATE (ts,payload,state,updated_at) ON public.site_snapshots,
  public.organisation_snapshots TO "processor@camosbase.iam";
```

No INSERT/DELETE, sequence privileges, schema ownership, BigQuery write permission
or Analyse permissions are needed. If built-in advisory lock function execution
has been revoked in this database, the administrator must grant it appropriately.

### Build and deploy the downloaded directory

From the uploaded `service/` directory in Cloud Shell:

```sh
# Only if the repository does not already exist:
gcloud artifacts repositories create camos-processors \
  --repository-format=docker --location="$REGION"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT/camos-processors/snapshot:reviewed"
gcloud builds submit --tag "$IMAGE" .
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$PROCESSOR" --no-allow-unauthenticated \
  --cpu=1 --memory=1Gi --concurrency=1 --min=0 --max=3 --timeout=1740 \
  --set-env-vars="SNAPSHOT_REFRESH_INTERVAL_MINUTES=30,GOOGLE_CLOUD_PROJECT=$PROJECT,PROCESSOR_SERVICE_ACCOUNT=$PROCESSOR,BIGQUERY_LOCATION=$BQ_LOCATION,CLOUD_SQL_IP_TYPE=PUBLIC"
export SERVICE_URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:$INVOKER" --role=roles/run.invoker
```

The deployer needs scoped Run deployment, build/registry access and actAs on the
runtime identity. The build identity needs registry write access and the standard
build/log permissions. Do not grant these to the runtime account. Keep default
supported ingress plus IAM unless stricter ingress is verified with Cloud Tasks.
No unauthenticated `allUsers` invoker binding should exist. Restrict other invokers
to trusted operators; the application deliberately relies on the IAM boundary.

### Queue and authorised manual task

```sh
gcloud tasks queues create "$QUEUE" --location="$REGION" \
  --max-concurrent-dispatches=3 --max-dispatches-per-second=1 \
  --max-attempts=5 --max-retry-duration=0s \
  --min-backoff=60s --max-backoff=300s --max-doublings=3
gcloud tasks queues describe "$QUEUE" --location="$REGION"
```

Confirm the Google-managed Cloud Tasks service agent exists and has the documented
`roles/cloudtasks.serviceAgent` project binding. Do not grant broad token-creator
permissions to the Processor. The task creator requires queue-scoped
`roles/cloudtasks.enqueuer` plus actAs on the invoker account:

```sh
# Replace with the actual authorised operator or later Portal service account.
export PRODUCER_MEMBER='user:operator@example.com'
gcloud tasks queues add-iam-policy-binding "$QUEUE" --location="$REGION" \
  --member="$PRODUCER_MEMBER" --role=roles/cloudtasks.enqueuer
gcloud iam service-accounts add-iam-policy-binding "$INVOKER" \
  --member="$PRODUCER_MEMBER" --role=roles/iam.serviceAccountUser

# Use the REST API to set dispatchDeadline explicitly; some gcloud create-task
# releases do not expose this field. No Cloud Tasks Python dependency is needed.
python3 - <<'PY'
import base64, json, os
task = {"task": {
    "dispatchDeadline": "1800s",
    "httpRequest": {
        "httpMethod": "POST",
        "url": os.environ["SERVICE_URL"] + "/tasks/snapshot",
        "headers": {"Content-Type": "application/json"},
        "body": base64.b64encode(b'{"organisation_id":1}').decode(),
        "oidcToken": {"serviceAccountEmail": os.environ["INVOKER"],
                      "audience": os.environ["SERVICE_URL"]},
    },
}}
with open("task-request.json", "w") as stream:
    json.dump(task, stream)
PY
# This performs REAL Snapshot writes when prerequisites exist and work is due.
# Use an authorised staging organisation first. Do not enqueue arbitrary customers.
curl --fail-with-body --request POST \
  --header "Authorization: Bearer $(gcloud auth print-access-token)" \
  --header 'Content-Type: application/json' --data-binary @task-request.json \
  "https://cloudtasks.googleapis.com/v2/projects/$PROJECT/locations/$REGION/queues/$QUEUE/tasks"
rm task-request.json
```

Cloud Tasks retries non-2xx, including invalid-request 4xx. Five attempts with no
retry-duration limit deliberately bounds attempts; if changing both settings,
check Cloud Tasks' documented combined stopping rules. Permanent malformed data
and invalid producers require operator repair, not unlimited retries. Task names
are not an exactly-once mechanism and are unnecessary for correctness.

## Operational release checks

Before production approval, validate ADC and the actual IAM SQL user, dataset
location/access, source schema, authenticated Tasks-to-Run invocation, rejection of
anonymous/wrong principals, and representative worst-case duration/memory/query
bytes. These require staging GCP access and are not established by offline tests.
Log outcomes/organisation IDs and internal failures; never log credentials or whole
snapshot payloads. Alert on repeated failures, exhausted retries, growing queue
age, lock contention, timeout/worker kills and OOM. Cloud Tasks does not provide an
automatic application dead-letter queue here; use logs/alerts and explicitly
enqueue again after repair. The Portal must later authorise organisation access
before enqueueing and keep its normal reads independent; no Portal change is
included in this service.
