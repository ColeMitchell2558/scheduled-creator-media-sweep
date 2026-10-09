from datetime import datetime, timezone

from media_cleanup import CreatorDelivery, MediaRecord, ProcessingJob, SweepRequest, decide_stale_media


def test_sweep_deletes_only_old_delivered_assets() -> None:
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    old_success = ProcessingJob("succeeded", datetime(2026, 7, 1, tzinfo=timezone.utc))
    running = ProcessingJob("running", datetime(2026, 9, 23, tzinfo=timezone.utc))
    request = SweepRequest(
        now=now,
        retention_days=30,
        records=(
            MediaRecord(
                "asset-old", "creators/7/final.mp4", "delivered", now,
                old_success, CreatorDelivery(datetime(2026, 8, 1, tzinfo=timezone.utc)),
            ),
            MediaRecord("asset-running", "creators/8/source.mov", "processing", now, running),
            MediaRecord(
                "asset-recent", "creators/9/final.mp4", "delivered", now,
                old_success, CreatorDelivery(datetime(2026, 9, 20, tzinfo=timezone.utc)),
            ),
        ),
    )

    decision = decide_stale_media(request)

    assert decision.delete_keys == ("creators/7/final.mp4",)
    assert decision.retained_asset_ids == ("asset-running", "asset-recent")

