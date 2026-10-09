"""Domain decisions for a stale-media cleanup sweep."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


AssetState = Literal["ingested", "processing", "ready", "delivered"]
JobState = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class ProcessingJob:
    state: JobState
    updated_at: datetime


@dataclass(frozen=True)
class CreatorDelivery:
    delivered_at: datetime


@dataclass(frozen=True)
class MediaRecord:
    asset_id: str
    object_key: str
    state: AssetState
    ingested_at: datetime
    processing_job: ProcessingJob | None = None
    creator_delivery: CreatorDelivery | None = None


@dataclass(frozen=True)
class SweepRequest:
    records: tuple[MediaRecord, ...]
    now: datetime
    retention_days: int = 30


@dataclass(frozen=True)
class SweepDecision:
    delete_keys: tuple[str, ...]
    retained_asset_ids: tuple[str, ...]


def decide_stale_media(request: SweepRequest) -> SweepDecision:
    """Delete old delivered media, while every unfinished workflow is retained."""
    cutoff = request.now - timedelta(days=request.retention_days)
    delete_keys: list[str] = []
    retained_ids: list[str] = []

    for record in request.records:
        delivery = record.creator_delivery
        completed = record.processing_job is not None and record.processing_job.state == "succeeded"
        if record.state == "delivered" and completed and delivery and delivery.delivered_at <= cutoff:
            delete_keys.append(record.object_key)
        else:
            retained_ids.append(record.asset_id)

    return SweepDecision(tuple(delete_keys), tuple(retained_ids))


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)

