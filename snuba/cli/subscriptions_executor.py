import logging
import signal
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import click
from arroyo import configure_metrics
from arroyo.backends.kafka import KafkaProducer

from snuba import environment, state
from snuba.attribution.log import flush_attribution_producer
from snuba.datasets.entities.entity_key import EntityKey
from snuba.datasets.entities.factory import get_entity
from snuba.datasets.factory import get_enabled_dataset_names
from snuba.environment import setup_logging, setup_sentry
from snuba.subscriptions.executor_consumer import build_executor_consumer
from snuba.utils.metrics.wrapper import MetricsWrapper
from snuba.utils.streams.configuration_builder import build_kafka_producer_configuration
from snuba.utils.streams.metrics_adapter import StreamMetricsAdapter


@click.command()
@click.option(
    "--dataset",
    "dataset_name",
    required=True,
    type=click.Choice(get_enabled_dataset_names()),
    help="The dataset to target.",
)
@click.option(
    "--entity",
    "entity_names",
    required=True,
    multiple=True,
    type=click.Choice(
        [
            EntityKey.EVENTS.value,
            EntityKey.TRANSACTIONS.value,
            EntityKey.METRICS_COUNTERS.value,
            EntityKey.METRICS_SETS.value,
            EntityKey.GENERIC_METRICS_SETS.value,
            EntityKey.GENERIC_METRICS_DISTRIBUTIONS.value,
        ]
    ),
    help="The entity to target.",
)
@click.option(
    "--consumer-group",
    default="snuba-subscription-executor",
    help="Consumer group used for consuming the scheduled subscription topic/s.",
)
@click.option(
    "--total-concurrent-queries",
    default=64,
    type=int,
    help="Total max number of concurrent queries for all replicas. Used to calculate max_concurrent_queries.",
)
@click.option(
    "--auto-offset-reset",
    default="error",
    type=click.Choice(["error", "earliest", "latest"]),
    help="Kafka consumer auto offset reset.",
)
@click.option(
    "--no-strict-offset-reset",
    is_flag=True,
    help="Forces the kafka consumer auto offset reset.",
)
@click.option("--log-level", help="Logging level to use.")
@click.option(
    "--stale-threshold-seconds",
    type=int,
    help="Skip execution if timestamp is beyond this threshold compared to the system time",
)
# TODO: For testing alternate rebalancing strategies. To be eventually removed.
@click.option(
    "--cooperative-rebalancing",
    is_flag=True,
    default=False,
    help="Use cooperative-sticky partition assignment strategy",
)
def subscriptions_executor(
    *,
    dataset_name: str,
    entity_names: Sequence[str],
    consumer_group: str,
    total_concurrent_queries: int,
    auto_offset_reset: str,
    no_strict_offset_reset: bool,
    log_level: Optional[str],
    stale_threshold_seconds: Optional[int],
    cooperative_rebalancing: bool,
) -> None:
    """
    The subscription's executor consumes scheduled subscriptions from the scheduled
    subscription topic for that entity, executes the queries on ClickHouse and publishes
    results on the results topic.
    """
    setup_logging(log_level)
    setup_sentry()

    metrics = MetricsWrapper(
        environment.metrics,
        "subscriptions.executor",
        tags={"dataset": dataset_name},
    )

    configure_metrics(StreamMetricsAdapter(metrics))

    # Just get the result topic configuration from the first entity. Later we
    # check they all have the same result topic anyway before building the consumer.
    entity_key = EntityKey(entity_names[0])

    storage = get_entity(entity_key).get_writable_storage()
    assert storage is not None
    stream_loader = storage.get_table_writer().get_stream_loader()
    result_topic_spec = stream_loader.get_subscription_result_topic_spec()
    assert result_topic_spec is not None

    producer = KafkaProducer(
        build_kafka_producer_configuration(
            result_topic_spec.topic,
            override_params={"partitioner": "consistent"},
        )
    )

    # TODO: Consider removing and always passing via CLI.
    # If a value provided via config, it overrides the one provided via CLI.
    # This is so we can quickly change this in an emergency.
    stale_threshold_seconds = state.get_config(
        f"subscriptions_stale_threshold_sec_{dataset_name}", stale_threshold_seconds
    )

    processor = build_executor_consumer(
        dataset_name,
        entity_names,
        consumer_group,
        producer,
        total_concurrent_queries,
        auto_offset_reset,
        not no_strict_offset_reset,
        metrics,
        stale_threshold_seconds,
        cooperative_rebalancing,
    )

    def handler(signum: int, frame: Any) -> None:
        # TODO: Temporary code for debugging executor shutdown
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        processor.signal_shutdown()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    with closing(producer), flush_querylog(), flush_attribution_producer():
        processor.run()


@contextmanager
def closing(producer: KafkaProducer) -> Iterator[Optional[KafkaProducer]]:
    try:
        yield producer
    finally:
        producer.close().result()


@contextmanager
def flush_querylog() -> Iterator[None]:
    try:
        yield
    finally:
        state.flush_producer()
