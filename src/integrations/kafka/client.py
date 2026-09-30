"""Kafka producer/consumer helpers for video preprocessing jobs."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewPartitions, NewTopic

from src.config import logger, resolve_cert_path

DEFAULT_VIDEO_TOPIC = "video-preprocessing"
DEFAULT_VIDEO_DLQ_TOPIC = "video-preprocessing-dlq"
DEFAULT_VIDEO_GROUP_ID = "mtc-video-worker"
DEFAULT_VIDEO_PARTITIONS = 3
DEFAULT_VIDEO_CONSUMERS = 3
DEFAULT_VIDEO_MAX_RETRIES = 3
DEFAULT_VIDEO_RETRY_BACKOFF_SEC = 5


def video_topic() -> str:
    return os.getenv("KAFKA_VIDEO_TOPIC") or DEFAULT_VIDEO_TOPIC


def video_dlq_topic() -> str:
    return os.getenv("KAFKA_VIDEO_DLQ_TOPIC") or DEFAULT_VIDEO_DLQ_TOPIC


def video_max_retries() -> int:
    return int(os.getenv("KAFKA_VIDEO_MAX_RETRIES") or DEFAULT_VIDEO_MAX_RETRIES)


def video_retry_backoff_sec() -> int:
    return int(os.getenv("KAFKA_VIDEO_RETRY_BACKOFF_SEC") or DEFAULT_VIDEO_RETRY_BACKOFF_SEC)


def normalize_video_job(job: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(job)
    normalized["retry_count"] = int(normalized.get("retry_count") or 0)
    normalized["max_retries"] = int(
        normalized.get("max_retries") or video_max_retries()
    )
    return normalized


def video_group_id() -> str:
    return os.getenv("KAFKA_VIDEO_GROUP_ID") or DEFAULT_VIDEO_GROUP_ID


def video_partition_count() -> int:
    return int(os.getenv("KAFKA_VIDEO_PARTITIONS") or DEFAULT_VIDEO_PARTITIONS)


def video_consumer_count() -> int:
    return int(os.getenv("KAFKA_VIDEO_CONSUMERS") or DEFAULT_VIDEO_CONSUMERS)


def _kafka_conf() -> dict[str, Any]:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if not bootstrap:
        raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is required")

    is_onprem = os.getenv("isOnprem", "False").strip().lower() in ("true", "1", "yes")

    base_conf: dict[str, Any] = {
        "bootstrap.servers": bootstrap,
        "api.version.request": False,
        "broker.version.fallback": "2.6.0",
        "socket.timeout.ms": 30000,
        "log.connection.close": False,
        "api.version.fallback.ms": 0,
    }

    if is_onprem:
        # On-premises: no SSL, plain TCP
        logger.info("Kafka using PLAINTEXT (isOnprem=True)")
        base_conf["security.protocol"] = "PLAINTEXT"
    else:
        base_conf.update(_ssl_conf())

    return base_conf


def _ssl_conf() -> dict[str, Any]:
    """mTLS using existing PEM files only. JKS truststores are not supported by librdkafka."""
    ca_path = resolve_cert_path(
        os.getenv("KAFKA_SSL_CA_LOCATION", "certificates/ca-cert.pem")
    )
    cert_path = resolve_cert_path(
        os.getenv("KAFKA_SSL_CERTIFICATE_LOCATION", "certificates/client-cert.pem")
    )
    key_path = resolve_cert_path(
        os.getenv("KAFKA_SSL_KEY_LOCATION", "certificates/client-key.pem")
    )
    extra_ca = resolve_cert_path(
        os.getenv("KAFKA_SSL_EXTRA_CA_LOCATION")
        or os.getenv("CAFile")
        or "certificates/mongodbCAFile.pem"
    )

    missing = [
        name
        for name, path in (
            ("CA", ca_path),
            ("client cert", cert_path),
            ("client key", key_path),
        )
        if not path or not os.path.exists(path)
    ]
    if missing:
        raise RuntimeError("Kafka SSL PEM files missing: " + ", ".join(missing))

    ca_files: list[str] = []
    for path in (ca_path, extra_ca):
        if path and os.path.exists(path) and path not in ca_files:
            ca_files.append(path)

    ident = os.getenv("KAFKA_SSL_ENDPOINT_IDENTIFICATION", "none")
    logger.info(
        "Kafka using SSL PEM (isOnprem=False) ca=%s cert=%s key=%s",
        ",".join(ca_files),
        cert_path,
        key_path,
    )
    conf: dict[str, Any] = {
        "security.protocol": "SSL",
        "ssl.ca.pem": "\n".join(
            Path(path).read_text(encoding="utf-8").strip() for path in ca_files
        )
        + "\n",
        "ssl.certificate.location": cert_path,
        "ssl.key.location": key_path,
        "ssl.endpoint.identification.algorithm": ident,
    }
    key_password = os.getenv("KAFKA_SSL_KEY_PASSWORD", "")
    if key_password:
        conf["ssl.key.password"] = key_password
    return conf


def _ensure_topic(topic: str, *, num_partitions: int, scale_up: bool = True) -> None:
    admin = AdminClient(_kafka_conf())
    metadata = admin.list_topics(timeout=20)
    existing = metadata.topics.get(topic)

    if existing is None or existing.error is not None:
        futures = admin.create_topics(
            [
                NewTopic(
                    topic,
                    num_partitions=num_partitions,
                    replication_factor=int(os.getenv("KAFKA_VIDEO_REPLICATION") or 1),
                )
            ]
        )
        try:
            futures[topic].result(timeout=30)
            logger.info("Created Kafka topic %s with %s partitions", topic, num_partitions)
        except KafkaException as e:
            logger.warning("Create topic %s: %s", topic, e)
        return

    current = len(existing.partitions)
    if not scale_up or current >= num_partitions:
        logger.info("Kafka topic %s already has %s partition(s)", topic, current)
        return

    futures = admin.create_partitions([NewPartitions(topic, num_partitions)])
    try:
        futures[topic].result(timeout=30)
        logger.info(
            "Increased Kafka topic %s partitions from %s to %s",
            topic,
            current,
            num_partitions,
        )
    except KafkaException as e:
        logger.warning("Could not increase partitions on %s: %s", topic, e)


def ensure_video_topic() -> None:
    """Create video-preprocessing with 3 partitions, or scale up if it already exists."""
    _ensure_topic(video_topic(), num_partitions=video_partition_count(), scale_up=True)


def ensure_video_dlq_topic() -> None:
    """Create the video preprocessing dead-letter topic."""
    _ensure_topic(video_dlq_topic(), num_partitions=1, scale_up=False)


_producer_lock = threading.Lock()
_producer: Optional[Producer] = None


def get_producer() -> Producer:
    global _producer
    with _producer_lock:
        if _producer is None:
            _producer = Producer(
                {
                    **_kafka_conf(),
                    "client.id": os.getenv("KAFKA_PRODUCER_CLIENT_ID") or "mtc-video-api",
                    "acks": "1",
                    "message.timeout.ms": 20000,
                    "api.version.request": False,
                    "broker.version.fallback": "2.6.0",
                }
            )
        return _producer


def _produce_to_topic(
    topic: str,
    job: dict[str, Any],
    *,
    key: Optional[str] = None,
) -> None:
    producer = get_producer()
    payload = json.dumps(job, default=str).encode("utf-8")
    kafka_key = (key or str(job.get("video_id") or "")).encode("utf-8")
    delivery_error: dict[str, Any] = {}

    def _on_delivery(err, _msg):
        if err is not None:
            delivery_error["error"] = err

    producer.produce(topic, value=payload, key=kafka_key, callback=_on_delivery)
    remaining = producer.flush(20)
    if remaining:
        global _producer
        with _producer_lock:
            _producer = None
        raise RuntimeError(
            f"Kafka flush timed out with {remaining} message(s) still in queue"
        )
    if delivery_error.get("error"):
        raise RuntimeError(f"Kafka produce failed: {delivery_error['error']}")
    logger.info("Published video job to %s key=%s", topic, kafka_key.decode())


def produce_video_job(job: dict[str, Any], *, key: Optional[str] = None) -> None:
    normalized = normalize_video_job(job)
    _produce_to_topic(video_topic(), normalized, key=key)


def produce_video_job_retry(job: dict[str, Any], *, key: Optional[str] = None) -> None:
    normalized = normalize_video_job(job)
    _produce_to_topic(video_topic(), normalized, key=key)


def produce_video_dlq(
    job: dict[str, Any],
    *,
    error_message: str,
    failure_code: str | None = None,
) -> None:
    payload = {
        **normalize_video_job(job),
        "dlq_reason": error_message,
        "dlq_failure_code": failure_code,
        "dlq_at": datetime.now(timezone.utc).isoformat(),
    }
    _produce_to_topic(video_dlq_topic(), payload, key=str(job.get("video_id") or ""))


def create_video_consumer(*, worker_index: int = 0) -> Consumer:
    base_id = os.getenv("KAFKA_CONSUMER_CLIENT_ID") or "mtc-video-worker"
    return Consumer(
        {
            **_kafka_conf(),
            "group.id": video_group_id(),
            "enable.auto.commit": False,
            "enable.partition.eof": False,
            "auto.offset.reset": "earliest",
            "client.id": f"{base_id}-{worker_index}",
        }
    )
