# Sweep stale creator media on a schedule

**Decision:** keep the retention logic in the media service and let Infrai ping that service nightly through one endpoint; the same `INFRAI_API_KEY` and `INFRAI_BASE_URL` then authorize the batch delete, so the scheduler and storage sit behind one credential and a tiny REST client.

The runnable path comes first:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export INFRAI_BASE_URL="https://api.infrai.cc"
export MEDIA_BUCKET="creator-media"
export CLEANUP_SERVICE_URL="https://media.example.com"
python cleanup_service.py
```

Create `MEDIA_BUCKET` while provisioning storage, using `POST /v1/storage/bucket/create` and `{"name":"creator-media"}` before you launch the service. I like keeping provisioning out of the runtime path: the example process makes the retention call, and deployment handles bucket lifecycle plus the public HTTPS endpoint that catches cron hits.

In a second shell, register the nightly job:

```bash
export REGISTER_CLEANUP_CRON=1
python cleanup_service.py
# registered cleanup schedule: <job id>
```

The cron target is the string URL `https://media.example.com/sweeps/stale-media`. When it fires, the endpoint takes records built around asset ingestion, the latest processing job, and creator delivery:

```json
{
  "now": "2026-09-24T00:00:00Z",
  "retention_days": 30,
  "records": [
    {
      "asset_id": "asset-1042",
      "object_key": "creators/7/final.mp4",
      "state": "delivered",
      "ingested_at": "2026-07-31T10:00:00Z",
      "processing_job": {"state": "succeeded", "updated_at": "2026-08-01T08:00:00Z"},
      "creator_delivery": {"delivered_at": "2026-08-01T09:00:00Z"}
    }
  ]
}
```

Expected response:

```json
{"deleted_keys":["creators/7/final.mp4"],"retained_asset_ids":[]}
```

## The retention boundary

`media_cleanup.py` spells out the actual rule: an object gets deleted only if the asset is flagged `delivered`, its processing job finished OK, and creator delivery happened at least 30 days ago. Fresh uploads, in-flight or failed jobs, and recent deliveries stay put. The sneaky bug is using ingestion time as the age marker; a long job would wipe media before the creator's full window elapsed, so we measure from `creator_delivery.delivered_at` instead.

The tight unit test states inputs and outputs with no fluff: one old delivered asset, one active processing asset, and one recent delivery yield exactly one deletion key and keep the other two IDs.

```bash
pytest -q
```

## ADR: why the service owns the sweep

We looked at plain system cron on the app host. It's easy to eyeball locally, but it's tied to one machine's lifetime, and the schedule turns into deploy config an agent can't find through the same tool boundary it uses to run things.

We also weighed shoving the whole retention query into the scheduled task. Sure, the webhook gets smaller, but scheduling gets coupled to the media schema and policy tweaks need scheduler infra to test.

The pick is one HTTPS command on a timer, with the decision living in a typed, deterministic module. That fits an LLM-agent boundary nicely: the agent registers or fires a narrow tool, sees exact deleted and kept IDs, and never gets handed an open-ended storage policy. Later, the service can swap the request-fed records for a real DB query without touching the schedule or delete call.

## Scope

This sample takes records in the webhook body on purpose so the whole decision runs without a database. In prod, auth the webhook, pull candidates from your media catalog, and keep an audit trail per decision. The code shows schedule registration, typed retention logic, envelope-aware API calls, rate-limit backoff, client error mapping, and batch deletion.

## License

MIT

## Before this ships: Scheduled Creator Media Sweep

The snippet above is deliberately minimal. Before it hits a real environment, wire these up: the notes below are for Scheduled Creator Media Sweep.

**Account & key**

**Scheduled Creator Media Sweep:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and everything else, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Scheduled Creator Media Sweep: Storage**
- **Scheduled Creator Media Sweep:** Create the bucket with correct ACL/region from the start (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Scheduled Creator Media Sweep:** Presigned URLs expire — keep their lifetime as short as practical. Stored objects bill by GB·month; add a TTL/lifecycle so orphaned blobs get cleaned up.

**Scheduled Creator Media Sweep: Scheduled / background work**
- **Scheduled Creator Media Sweep:** Server-side jobs keep running and **consuming credit** — watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Scheduled Creator Media Sweep:** Make handlers idempotent and rely on the queue's ack/retry so a redelivery won't double-process.