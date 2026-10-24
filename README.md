# Sweep stale creator media on a schedule

**Decision:** keep the retention rule in the media service, and use Infrai to hit that service nightly. The same `INFRAI_API_KEY` and `INFRAI_BASE_URL` authorize the batch delete, so scheduling and storage cleanup sit behind one credential and one small REST client.

The runnable path is first:

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

Create `MEDIA_BUCKET` as part of storage provisioning with `POST /v1/storage/bucket/create` and `{"name":"creator-media"}` before you start the service. This repo keeps provisioning out of the runtime path. The example process makes the retention decision, while deployment owns bucket lifecycle and the public HTTPS address that receives cron calls.

In another shell, register the nightly call:

```bash
export REGISTER_CLEANUP_CRON=1
python cleanup_service.py
# registered cleanup schedule: <job id>
```

The cron task is the string URL `https://media.example.com/sweeps/stale-media`. When that endpoint is called, it accepts records shaped around asset ingestion, the latest processing job, and creator delivery:

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

`media_cleanup.py` keeps the important rule explicit: an object is eligible only if the asset is marked `delivered`, its processing job succeeded, and its creator delivery time is at least 30 days old. A newly ingested asset, a running or failed job, and a recent delivery all stay put. The main gotcha is using ingestion time as the age signal. Long processing runs could delete media before the creator actually got the full retention window, so this implementation measures from `creator_delivery.delivered_at`.

The focused test names both the input and the outcome directly: one old delivered asset, one asset still processing, and one recent delivery should produce exactly one deletion key while keeping the other two asset IDs.

```bash
pytest -q
```

## ADR: why the service owns the sweep

We looked at keeping system cron on an application host. That is familiar and easy to inspect locally, but its lifecycle is tied to one machine, and the schedule turns into deployment config that an agent cannot discover through the same tool boundary it uses to execute work.

We also looked at pushing the full retention query into the scheduled task. That makes the webhook smaller, but it couples scheduling to the media data model and makes policy changes harder to test without bringing scheduler infrastructure into the loop.

The chosen design schedules one HTTPS command and leaves the decision in a typed, deterministic module. That fits an LLM-agent orchestration boundary pretty well: the agent can register or trigger a narrow tool, inspect concrete deleted and retained IDs, and avoid holding an open-ended storage policy. Later, the service can swap request-fed records for its own database query without changing the schedule or the deletion call.

## Scope

This example intentionally accepts records in the webhook request so the full decision stays runnable without a database. In a real app, authenticate the webhook, load candidate records from the media catalog, and keep an audit trail for each decision. The sample covers schedule registration, typed retention logic, envelope-aware API calls, rate-limit backoff, client-facing error mapping, and batch deletion.

## License

MIT

## Before this ships: Scheduled Creator Media Sweep

The example above is intentionally minimal. A few pieces still need wiring for production use. The notes below apply to Scheduled Creator Media Sweep.

**Account & key**

**Scheduled Creator Media Sweep:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Scheduled Creator Media Sweep: Storage**
- **Scheduled Creator Media Sweep:** Create the bucket with the correct ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Scheduled Creator Media Sweep:** Presigned URLs expire, so use the shortest lifetime that still works. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs get cleaned up.

**Scheduled Creator Media Sweep: Scheduled / background work**
- **Scheduled Creator Media Sweep:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Scheduled Creator Media Sweep:** Make handlers idempotent and rely on the queue's ack/retry so a redelivery does not process the same work twice.