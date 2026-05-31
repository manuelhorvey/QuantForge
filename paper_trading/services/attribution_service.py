import logging
import os

import pandas as pd

from paper_trading.attribution.collector import TradeAttributionRecord

logger = logging.getLogger("quantforge.attribution_service")


class AttributionService:
    def __init__(self, asset):
        self.asset = asset

    def set_experiment_context(self, experiment_id: str, export_dir: str | None = None) -> None:
        asset = self.asset
        asset._experiment_id = experiment_id
        if export_dir is not None:
            asset._attribution_export_dir = export_dir
            os.makedirs(export_dir, exist_ok=True)

    def flush_attribution(self) -> None:
        asset = self.asset
        if not asset._attribution_buffer or not asset._attribution_export_dir:
            return
        try:
            path = os.path.join(asset._attribution_export_dir, f"{asset.name}_attribution.parquet")
            records = list(asset._attribution_buffer)
            asset._attribution_buffer.clear()
            frame = TradeAttributionRecord.to_frame(records, experiment_id=asset._experiment_id)
            if os.path.exists(path):
                existing = pd.read_parquet(path)
                frame = pd.concat([existing, frame], ignore_index=True)
            frame.to_parquet(path, index=False)
            logger.debug("attribution: flushed %d records for %s to %s", len(records), asset.name, path)
        except Exception:
            logger.exception("attribution: failed to flush records for %s", asset.name)
