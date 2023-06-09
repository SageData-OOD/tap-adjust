"""Adjust tap class."""

from datetime import datetime
from typing import List

from singer_sdk import Stream, Tap
from singer_sdk import typing as th

from tap_adjust.streams import ReportStream


class TapAdjust(Tap):
    """Adjust tap class."""

    name = "tap-adjust"

    config_jsonschema = th.PropertiesList(
        th.Property("api_token", th.StringType, required=True),
        th.Property("additional_metrics", th.ArrayType(th.StringType), required=False),
        th.Property("attribution_type", th.StringType, required=True),
        th.Property("attribution_source", th.StringType, required=True),
        th.Property("start_date", th.DateType, required=True),
        th.Property(
            "end_date",
            th.DateType,
            default=str(datetime.utcnow().date()),
            required=False,
        ),
    ).to_dict()

    def discover_streams(self: Tap) -> List[Stream]:
        """Return a list of discovered streams.

        Returns:
            List of stream instances.
        """
        return [ReportStream(tap=self)]
