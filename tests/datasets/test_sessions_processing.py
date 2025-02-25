from typing import Any, MutableMapping

import pytest
from snuba_sdk.legacy import json_to_snql

from snuba.attribution import get_app_id
from snuba.attribution.attribution_info import AttributionInfo
from snuba.clickhouse.query import Query
from snuba.datasets.factory import get_dataset
from snuba.datasets.storages.sessions import raw_schema, read_schema
from snuba.query import SelectedExpression
from snuba.query.expressions import Column, CurriedFunctionCall, FunctionCall, Literal
from snuba.query.query_settings import (
    HTTPQuerySettings,
    QuerySettings,
    SubscriptionQuerySettings,
)
from snuba.query.snql.parser import parse_snql_query
from snuba.reader import Reader
from snuba.request import Request
from snuba.web import QueryResult


def test_sessions_processing() -> None:
    query_body = {
        "query": """
        MATCH (sessions)
        SELECT duration_quantiles, sessions, users
        WHERE org_id = 1
        AND project_id = 1
        AND started >= toDateTime('2020-01-01T12:00:00')
        AND started < toDateTime('2020-01-02T12:00:00')
        """,
        "dataset": "sessions",
    }

    sessions = get_dataset("sessions")
    query, snql_anonymized = parse_snql_query(query_body["query"], sessions)
    request = Request(
        id="a",
        original_body=query_body,
        query=query,
        snql_anonymized=snql_anonymized,
        query_settings=HTTPQuerySettings(referrer=""),
        attribution_info=AttributionInfo(get_app_id("default"), "", None, None, None),
    )

    def query_runner(
        query: Query, settings: QuerySettings, reader: Reader
    ) -> QueryResult:
        quantiles = tuple(
            Literal(None, quant) for quant in [0.5, 0.75, 0.9, 0.95, 0.99, 1]
        )
        assert query.get_selected_columns() == [
            SelectedExpression(
                "duration_quantiles",
                CurriedFunctionCall(
                    "_snuba_duration_quantiles",
                    FunctionCall(
                        None,
                        "quantilesIfMerge",
                        quantiles,
                    ),
                    (Column(None, None, "duration_quantiles"),),
                ),
            ),
            SelectedExpression(
                "sessions",
                FunctionCall(
                    "_snuba_sessions",
                    "plus",
                    (
                        FunctionCall(
                            None, "countIfMerge", (Column(None, None, "sessions"),)
                        ),
                        FunctionCall(
                            None,
                            "sumIfMerge",
                            (Column(None, None, "sessions_preaggr"),),
                        ),
                    ),
                ),
            ),
            SelectedExpression(
                "users",
                FunctionCall(
                    "_snuba_users", "uniqIfMerge", (Column(None, None, "users"),)
                ),
            ),
        ]
        return QueryResult({}, {})

    sessions.get_default_entity().get_query_pipeline_builder().build_execution_pipeline(
        request, query_runner
    ).execute()


selector_tests = [
    pytest.param(
        {
            "selected_columns": ["sessions", "bucketed_started"],
            "groupby": ["bucketed_started"],
            "conditions": [
                ["org_id", "=", 1],
                ["project_id", "=", 1],
                ["started", ">=", "2020-01-01T12:00:00"],
                ["started", "<", "2020-01-02T12:00:00"],
            ],
        },
        False,
        read_schema.get_table_name(),
        id="Select hourly by default",
    ),
    pytest.param(
        {
            "selected_columns": ["sessions"],
            "granularity": 60,
            "conditions": [
                ["org_id", "=", 1],
                ["project_id", "=", 1],
                ["started", ">=", "2020-01-01T12:00:00"],
                ["started", "<", "2020-01-02T12:00:00"],
            ],
        },
        False,
        read_schema.get_table_name(),
        id="Select hourly if not grouped by started time",
    ),
    pytest.param(
        {
            "selected_columns": ["sessions", "bucketed_started"],
            "groupby": ["bucketed_started"],
            "granularity": 60,
            "conditions": [
                ("org_id", "=", 1),
                ("project_id", "=", 1),
                ("started", ">=", "2019-09-19T10:00:00"),
                ("started", "<", "2019-09-19T12:00:00"),
            ],
        },
        False,
        raw_schema.get_table_name(),
        id="Select raw depending on granularity",
    ),
    pytest.param(
        {
            "selected_columns": [],
            "aggregations": [
                [
                    "if(greater(sessions, 0), divide(sessions_crashed, sessions), null)",
                    None,
                    "crash_rate_alert_aggregate",
                ]
            ],
            "conditions": [
                ("org_id", "=", 1),
                ("project_id", "=", 1),
                ("started", ">=", "2019-09-19T10:00:00"),
                ("started", "<", "2019-09-19T11:00:00"),
            ],
        },
        True,
        raw_schema.get_table_name(),
        id="Select raw if its a dataset subscription and time_window is <=1h",
    ),
    pytest.param(
        {
            "selected_columns": [],
            "aggregations": [
                [
                    "if(greater(sessions, 0), divide(sessions_crashed, sessions), null)",
                    None,
                    "crash_rate_alert_aggregate",
                ]
            ],
            "conditions": [
                ("org_id", "=", 1),
                ("project_id", "=", 1),
                ("started", ">=", "2019-09-19T10:00:00"),
                ("started", "<", "2019-09-19T12:00:00"),
            ],
        },
        True,
        read_schema.get_table_name(),
        id="Select materialized if its a dataset subscription and time_window > 1h",
    ),
]


@pytest.mark.parametrize(
    "query_body, is_subscription, expected_table",
    selector_tests,
)
def test_select_storage(
    query_body: MutableMapping[str, Any], is_subscription: bool, expected_table: str
) -> None:
    sessions = get_dataset("sessions")
    request = json_to_snql(query_body, "sessions")
    request.validate()
    query, snql_anonymized = parse_snql_query(str(request.query), sessions)
    subscription_settings = (
        SubscriptionQuerySettings if is_subscription else HTTPQuerySettings
    )

    request = Request(
        id="a",
        original_body=request.to_dict(),
        query=query,
        snql_anonymized=snql_anonymized,
        query_settings=subscription_settings(referrer=""),
        attribution_info=AttributionInfo(
            get_app_id("default"), "blah", None, None, None
        ),
    )

    def query_runner(
        query: Query, settings: QuerySettings, reader: Reader
    ) -> QueryResult:
        assert query.get_from_clause().table_name == expected_table
        return QueryResult({}, {})

    sessions.get_default_entity().get_query_pipeline_builder().build_execution_pipeline(
        request, query_runner
    ).execute()
