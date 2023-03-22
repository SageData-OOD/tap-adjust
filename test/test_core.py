"""Meltano Standard Tests."""

import datetime

from singer_sdk.testing import get_tap_test_class

from tap_adjust.tap import TapAdjust

SAMPLE_CONFIG = {
    "start_date": str(datetime.datetime.now(datetime.timezone.utc).date()),
    "api_token": "TODO: read from secrets_file",
}


# Run standard built-in tap tests from the SDK:
TestTapExample = get_tap_test_class(tap_class=TapAdjust, config=SAMPLE_CONFIG)
