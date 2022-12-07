"""
snowflake.py by Falcon Dai (https://github.com/falcondai/python-snowflake), MIT License

Modified for Python 3 with some additions and style fixes
"""

from datetime import datetime, timezone

# Twitter's snowflake parameters
TWEPOCH = 1288834974657
DATACENTER_ID_BITS = 5
WORKER_ID_BITS = 5
SEQUENCE_ID_BITS = 12
MAX_DATACENTER_ID = 1 << DATACENTER_ID_BITS
MAX_WORKER_ID = 1 << WORKER_ID_BITS
MAX_SEQUENCE_ID = 1 << SEQUENCE_ID_BITS
MAX_TIMESTAMP = 1 << (64 - DATACENTER_ID_BITS - WORKER_ID_BITS - SEQUENCE_ID_BITS)


def make_snowflake(
    timestamp_ms: int,
    datacenter_id: int,
    worker_id: int,
    sequence_id: int,
    epoch: int = TWEPOCH,
) -> int:
    """
    Generate a Twitter Snowflake ID, based on
    https://github.com/twitter-archive/snowflake/blob/snowflake-2010/src/main/scala/com/twitter/service/snowflake/IdWorker.scala

    Parameters
    ----------
    timestamp_ms : int
        Time since Unix epoch in milliseconds

    epoch : int
        Unix timestamp of starting epoch in milliseconds.
        Defaults to `snowflake.TWEPOCH` (1288834974657)
    """

    sid = (
        ((int(timestamp_ms) - epoch) % MAX_TIMESTAMP)
        << DATACENTER_ID_BITS
        << WORKER_ID_BITS
        << SEQUENCE_ID_BITS
    )
    sid += (datacenter_id % MAX_DATACENTER_ID) << WORKER_ID_BITS << SEQUENCE_ID_BITS
    sid += (worker_id % MAX_WORKER_ID) << SEQUENCE_ID_BITS
    sid += sequence_id % MAX_SEQUENCE_ID
    return sid


def melt(snowflake_id: int, epoch: int = TWEPOCH) -> tuple:
    """
    Inversely transform a Snowflake ID back to its parts.
    """
    sequence_id = snowflake_id & (MAX_SEQUENCE_ID - 1)
    worker_id = (snowflake_id >> SEQUENCE_ID_BITS) & (MAX_WORKER_ID - 1)
    datacenter_id = (snowflake_id >> SEQUENCE_ID_BITS >> WORKER_ID_BITS) & (
        MAX_DATACENTER_ID - 1
    )
    timestamp_ms = (
        snowflake_id >> SEQUENCE_ID_BITS >> WORKER_ID_BITS >> DATACENTER_ID_BITS
    )
    timestamp_ms += epoch

    return (timestamp_ms, int(datacenter_id), int(worker_id), int(sequence_id))


def to_datetime(timestamp_ms: int, localtime: bool = False) -> datetime:
    """
    Convert a timestamp with milliseconds to a datetime object.

    Parameters
    ----------
    localtime : bool
        Whether to return as a `datetime` object in the machine's local timezone or
        UTC (default)
    """
    if localtime:
        return datetime.fromtimestamp(timestamp_ms // 1000).astimezone()
    return datetime.fromtimestamp(timestamp_ms // 1000, timezone.utc)
