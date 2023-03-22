"""REST client handling, including AdjustStream base class."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import cache
from typing import Any, List, get_args

import singer_sdk._singerlib as singer
from requests import Response
from singer_sdk.authenticators import APIKeyAuthenticator
from singer_sdk.pagination import BaseAPIPaginator
from singer_sdk.plugin_base import PluginBase as TapBaseClass
from singer_sdk.streams import RESTStream

from .model import BASE_METRICS, DIMENSIONS, ReportModel


class AdjustStream(RESTStream):
    """Adjust report stream class."""

    url_base = "https://dash.adjust.com"

    @property
    @cache
    def authenticator(self: RESTStream) -> APIKeyAuthenticator:
        """Return a new authenticator object.

        Returns:
            The authenticator instance for this stream.
        """
        return APIKeyAuthenticator.create_for_stream(
            self,
            key="Authorization",
            value=f"Bearer {self.config['api_token']}",
            location="header",
        )


# A paginator that returns a list of dates between start_date and end_date
class DatePaginator(BaseAPIPaginator[datetime.date]):
    """Paginates data day by day."""

    def __init__(self: DatePaginator, start_value: date, end_value: date) -> None:
        """
        Create a new paginator.

        Args:
            start_value: Initial value.
            end_value: End date value.
        """
        super().__init__(start_value)
        self._start_value = start_value
        self._end_value = end_value

    def has_more(self: DatePaginator, response: Response) -> bool:
        """Override this method to check if the endpoint has any pages left.

        Args:
            response: API response object.

        Returns:
            Boolean flag used to indicate if the endpoint has more pages.
        """
        return self.current_value < self.end_date

    def get_next(self: DatePaginator, response: Response) -> date | None:
        """Get the next pagination token or index from the API response.

        Args:
            response: API response object.

        Returns:
            The next page token or index. Return `None` from this method to indicate
                the end of pagination.
        """
        return self._start_value + timedelta(days=self.count())


class ReportStream(AdjustStream):
    """Adjust report stream class."""

    name = "report"
    records_jsonpath = "$.rows[*]"
    schema = json.loads(ReportModel.schema_json())
    path = "/control-center/reports-service/report"
    replication_key = "day"
    replication_method = "INCREMENTAL"

    def __init__(self: ReportStream, tap: TapBaseClass) -> None:
        """
        Initialize a stats report stream.

        Args:
            tap: The tap instance.
        """
        super().__init__(tap=tap)

        self.dimensions: List[str] = []
        self.metrics: List[str] = []

    def get_new_paginator(self: ReportStream) -> BaseAPIPaginator:
        """Get a fresh paginator for this API endpoint.

        Returns:
            A paginator instance.
        """
        return DatePaginator(
            datetime.strptime(self.config["start_date"], "%Y-%m-%d").date(),
            datetime.strptime(self.config["end_date"], "%Y-%m-%d").date(),
        )

    @property
    def primary_keys(self: ReportStream) -> List[str]:
        """Return primary key dynamically based on user inputs.

        Returns:
            List of primary keys.
        """
        return self.dimensions

    @primary_keys.setter
    def primary_keys(self: ReportStream, value: Any) -> None:
        """Set primary keys.

        Args:
            value: Value to set.
        """
        pass

    def get_url_params(self: ReportStream, context: dict | None, next_page_token: Any | None) -> dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization.

        If paging is supported, developers may override with specific paging logic.

        Args:
            context: Stream partition or context dictionary.
            next_page_token: Token, page number or any request argument to request the
                next page of data.

        Returns:
            Dictionary of URL query parameters to use in the request.
        """
        request_params = {
            # query data day by day
            "date_period": f"{next_page_token}:{next_page_token}",
            "dimensions": ",".join(self.dimensions),
            "metrics": ",".join(self.metrics),
        }

        currency = self.config.get("currency")

        if currency:
            request_params["currency"] = currency

        return request_params

    def apply_catalog(self: ReportStream, catalog: singer.Catalog) -> None:
        """Extract the dimensions and metrics from the catalog.

        Args:
            catalog: configured singer catalog
        """
        catalog_entry = catalog.get_stream(self.name)
        selection = catalog_entry.metadata.resolve_selection()

        for breadcrumb, selected in selection.items():
            if breadcrumb and selected:
                if breadcrumb[-1] in get_args(DIMENSIONS):
                    self.dimensions.append(breadcrumb[-1])
                elif breadcrumb[-1] in get_args(BASE_METRICS):
                    self.metrics.append(breadcrumb[-1])

        # add custom metrics passed in config
        self.metrics += self.config.get("custom_metrics", [])

        catalog_entry.key_properties = self.dimensions
        catalog_entry.metadata.root.table_key_properties = catalog_entry.key_properties

        self.logger.info("Computed DIMENSIONS: %s", self.dimensions)
        self.logger.info("Computed METRICS: %s", self.metrics)

        super().apply_catalog(catalog)

        # mapper doesn't work with dynamic primary keys
        # another approach would be to compute a hash based on the selected dimensions
        # and use that as the primary key instead of the set of selected dimensions
        self._tap.mapper.register_raw_streams_from_catalog(catalog)
