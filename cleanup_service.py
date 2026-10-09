"""Runnable webhook and scheduler registration for stale creator media."""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request

from infrai import InfraiClient, InfraiError
from media_cleanup import CreatorDelivery, MediaRecord, ProcessingJob, SweepRequest, decide_stale_media, parse_utc


def record_from_json(value: dict[str, Any]) -> MediaRecord:
    job = value.get("processing_job")
    delivery = value.get("creator_delivery")
    return MediaRecord(
        asset_id=str(value["asset_id"]),
        object_key=str(value["object_key"]),
        state=value["state"],
        ingested_at=parse_utc(value["ingested_at"]),
        processing_job=ProcessingJob(job["state"], parse_utc(job["updated_at"])) if job else None,
        creator_delivery=CreatorDelivery(parse_utc(delivery["delivered_at"])) if delivery else None,
    )


def create_app(client: InfraiClient | None = None) -> Flask:
    app = Flask(__name__)

    @app.post("/sweeps/stale-media")
    def sweep_stale_media():
        try:
            body = request.get_json(force=True)
            sweep = SweepRequest(
                records=tuple(record_from_json(item) for item in body["records"]),
                now=parse_utc(body["now"]),
                retention_days=int(body.get("retention_days", 30)),
            )
            decision = decide_stale_media(sweep)
            if decision.delete_keys:
                (client or InfraiClient()).delete_objects(
                    bucket=os.environ["MEDIA_BUCKET"], keys=decision.delete_keys
                )
            return jsonify(
                deleted_keys=list(decision.delete_keys),
                retained_asset_ids=list(decision.retained_asset_ids),
            )
        except (KeyError, TypeError, ValueError) as error:
            return jsonify(error=str(error)), 400
        except InfraiError as error:
            status = error.status if 400 <= error.status < 500 else 502
            return jsonify(error=error.code, detail=error.detail), status

    return app


def register_schedule(client: InfraiClient | None = None) -> str:
    service_url = os.environ["CLEANUP_SERVICE_URL"].rstrip("/")
    return (client or InfraiClient()).create_cron(
        cron_expr="0 2 * * *",
        task=f"{service_url}/sweeps/stale-media",
    )


if __name__ == "__main__":
    if os.environ.get("REGISTER_CLEANUP_CRON") == "1":
        print(f"registered cleanup schedule: {register_schedule()}")
    else:
        create_app().run(host="127.0.0.1", port=8080)

