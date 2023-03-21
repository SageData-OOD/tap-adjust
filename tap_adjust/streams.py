"""REST client handling, including AdjustStream base class."""
from __future__ import annotations
from datetime import datetime, timedelta
from functools import cache
from requests import Response
from typing import Any

import singer_sdk._singerlib as singer
from singer_sdk.plugin_base import PluginBase as TapBaseClass
from singer_sdk.streams import RESTStream
from singer_sdk.authenticators import APIKeyAuthenticator
from singer_sdk.pagination import BaseAPIPaginator
from model import ReportModel, DIMENSIONS, BASE_METRICS


class AdjustStream(RESTStream):
    """Adjust report stream class."""

    url_base = "https://dash.adjust.com"

    @property
    @cache
    def authenticator(self) -> APIKeyAuthenticator:
        """Return a new authenticator object.

        Returns:
            The authenticator instance for this stream.
        """
        return APIKeyAuthenticator.create_for_stream(self,
                                                     key="Authorization",
                                                     value="Bearer " + self.tap.config["api_token"])
    
# A paginator that returns a list of dates between start_date and end_date
class DatePaginator(BaseAPIPaginator[datetime.date]):

    def __init__(self, start_value: datetime.date, end_value: datetime.date) -> None:
        """Create a new paginator.

        Args:
            start_value: Initial value.
        """
        super().__init__(start_value)
        self._start_value = start_value
        self._end_value = end_value

    def has_more(self, response: Response) -> bool:
        """Override this method to check if the endpoint has any pages left.

        Args:
            response: API response object.

        Returns:
            Boolean flag used to indicate if the endpoint has more pages.
        """
        
        return self.current_value < self.end_date

    def get_next(self, response: Response) -> datetime.date | None:
        """Get the next pagination token or index from the API response.

        Args:
            response: API response object.

        Returns:
            The next page token or index. Return `None` from this method to indicate
                the end of pagination.
        """
        return self._start_value + timedelta(days=self.count())



class ReportStream(AdjustStream):
    records_jsonpath = "$.rows[*]"
    schema = ReportModel.schema_json()
    path = "/control-center/reports-service/report"
    replication_key = "day"
    replication_method = "INCREMENTAL"

    def get_new_paginator(self) -> BaseAPIPaginator:
        """Get a fresh paginator for this API endpoint.

        Returns:
            A paginator instance.
        """
        return DatePaginator(
            datetime.strptime(self.config["start_date"], "%Y-%m-%d").date(),
            datetime.strptime(self.config["end_date"], "%Y-%m-%d").date(),
        )
    
    @property
    def primary_keys(self):
        """Return primary key dynamically based on user inputs."""
        return self.dimensions
    
    @primary_keys.setter
    def primary_keys(self, value):
        pass

    def __init__(
        self,
        tap: TapBaseClass
    ) -> None:
        """Initialize a stats report stream.

        Args:
            tap: The tap instance.
            report: The report dictionary.
        """
        super().__init__(tap)

        self.dimensions = []
        self.metrics = []

    def get_url_params(
        self, context: dict | None, next_page_token: Any | None
    ) -> dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization.

        If paging is supported, developers may override with specific paging logic.

        Args:
            context: Stream partition or context dictionary.
            next_page_token: Token, page number or any request argument to request the
                next page of data.

        Returns:
            Dictionary of URL query parameters to use in the request.
        """
        return {
            "currency": self.config.get("currency", "EUR"),
            # query data day by day
            "date_period": f"{next_page_token}:{next_page_token}",
            "dimensions": ",".join(self.dimensions),
            "metrics": ",".join(self.metrics),
        }
    
    def apply_catalog(self, catalog: singer.Catalog) -> None:
        """Extract the dimensions and metrics from the catalog."""

        catalog_entry = catalog.get_stream(self.name)
        selection = catalog_entry.metadata.resolve_selection()

        for breadcrumb, selected in selection.items():
            if breadcrumb and selected:
                if breadcrumb[-1] in DIMENSIONS:
                    self.dimensions.append(breadcrumb[-1])
                elif breadcrumb[-1] in BASE_METRICS:
                    self.metrics.append(breadcrumb[-1])

        # add custom metrics passed in config
        self.metrics += self.config.get("custom_metrics", [])

        catalog_entry.key_properties = self.dimensions
        catalog_entry.metadata.root.table_key_properties = catalog_entry.key_properties

        
        self.logger.info("Computed DIMENSIONS: %s", self.dimensions)
        self.logger.info("Computed METRICS: %s", self.metrics)
        self.logger.info("Computed PRIMARY KEYS: %s", self.primary_keys)

        super().apply_catalog(catalog)

        # mapper doesn't play well with dynamic primary keys
        # another approach would be to compute a hash based on the selected dimensions
        # and use that as the primary key instead of the dimensions themselves
        self._tap.mapper.register_raw_streams_from_catalog(catalog)
    
# curl \
# --header 'Authorization: Bearer <adjust_api_token>' \
# --location --request GET 'https://dash.adjust.com/control-center/reports-service/report?cost_mode=network&app_token__in={app_token1},{app_token2}&date_period=2021-05-01:2021-05-02&dimensions=app,partner_name,campaign,campaign_id_network,campaign_network&metrics=installs,network_installs,network_cost,network_ecpi' \


# {
#     "rows": [
#         {
#             "attr_dependency": {
#                 "campaign_id_network": "unknown",
#                 "partner_id": "-300",
#                 "partner": "Organic"
#             },
#             "app": "Test app",
#             "partner_name": "Organic",
#             "campaign": "unknown",
#             "campaign_id_network": "unknown",
#             "campaign_network": "unknown",
#             "installs": "10",
#             "network_installs": "0",
#             "network_cost": "0.0",
#             "network_ecpi": "0.0"
#         }
#     ],
#     "totals": {
#         "installs": 10.0,
#         "network_installs": 0.0,
#         "network_cost": 0.0,
#         "network_ecpi": 0.0
#     },
#     "warnings": [],
#     "pagination": null
# }

