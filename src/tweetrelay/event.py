import asyncio
import datetime
import json
import logging
from os import path
from typing import Any, List, NamedTuple, Optional

from pymitter import EventEmitter
from sse_starlette import ServerSentEvent

from .event import make_sse
from .settings import Settings, get_settings
from snowflake import TWEPOCH, make_snowflake

SSE_EVENT_NAME = "announce-sse"

_logger = logging.getLogger(__name__)


# https://stackoverflow.com/a/1363857/11524425
class SingletonEventEmitter(EventEmitter):
    __instance = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
        return cls.__instance


class SentEvent(NamedTuple):
    timestamp: datetime.datetime
    event: ServerSentEvent


def make_sse(
    data: Optional[Any] = None,
    *,
    id: Optional[int] = None,
    event: Optional[str] = None,
    retry: Optional[int] = None,
    comment: Optional[str] = None,
):
    r"""
    Create a `ServerSentEvent` with `\n` (LF) line endings

    Parameters
    ----------
    data : Any | None
        The data field for the message. Any datatype can be specified to this parameter,
        since the SSE instance converts them to a string before they are sent.
    id: int | None
        The event ID to set the EventSource object's last event ID value to.
    event: str | None
        The event's type. If this is specified, an event will be dispatched on the
        client to the listener for the specified event name; a website would use
        `addEventListener()` to listen for named events. The default event type
        is "message".
    retry: int | None
        The reconnection time to use when attempting to send the event. This must be an
        integer, specifying the reconnection time in milliseconds. If a non-integer
        value is specified, the field is ignored.
    comment: str | None
        A colon as the first character of a line is essence a comment, and is ignored.
        Usually used as a ping message to keep connecting. If set, this will be a
        comment message.
    """
    return ServerSentEvent(
        data, id=id, event=event, retry=retry, comment=comment, sep="\n"
    )


# Based on https://maxhalford.github.io/blog/flask-sse-no-deps/ (MIT License)
class MessageAnnouncer:
    _ee = SingletonEventEmitter()

    def __init__(self, max_event_age: int = 15, epoch: int = TWEPOCH):
        self.listeners: list[asyncio.Queue] = []
        self.recent_events: list[SentEvent] = []
        self.max_event_age = max_event_age
        self._id_epoch = epoch
        self._last_snowflake_ms = 0
        self._sequence_id = 0

        self._ee.on("announce-sse", self.announce)

        settings: Settings = get_settings()
        self.recent_events_file: str = settings.recent_events_file

        # Load recent events from file
        if path.exists(self.recent_events_file):
            with open(self.recent_events_file) as f:
                try:
                    data: list[dict] = json.load(f)
                    for event in data:
                        sse = make_sse(**event["sse_data"])
                        timestamp_dt = datetime.datetime.fromtimestamp(
                            event["timestamp"], datetime.timezone.utc
                        )
                        self.recent_events.append(SentEvent(timestamp_dt, sse))
                except Exception:  # noqa: PIE786
                    _logger.exception("Failed to read %s", self.recent_events_file)
        event_count = len(self.recent_events)
        if event_count > 0:
            _logger.debug(
                "Loaded %s recently-sent event%s from %s",
                event_count,
                "s" if event_count != 1 else "",
                self.recent_events_file,
            )

    def listen(self) -> asyncio.Queue:
        """
        Subscribe to events sent by the `MessageAnnouncer` instance
        """
        # maxsize param defines maximum number of events that can be sent at once
        msg_q = asyncio.Queue(maxsize=10)
        self.listeners.append(msg_q)
        return msg_q

    def save_recent_events(self):
        """
        Saves a list of recently-sent server-side events to a file for later use.

        The path name of the target file is specified in your application's settings file.
        """

        event_dict_list_temp: list[dict] = []
        for event in self.recent_events:
            timestamp, sse = event
            event_dict_list_temp.append(
                {
                    "timestamp": timestamp.timestamp(),
                    "sse_data": {
                        "id": sse.id,
                        "event": sse.event,
                        "data": sse.data,
                        "retry": sse.retry,
                        "comment": sse.comment,
                    },
                }
            )

        with open(self.recent_events_file, "w") as f:
            f.write(json.dumps(event_dict_list_temp))
            _logger.debug("Recent events saved to %s", self.recent_events_file)

    def announce(self, sse: ServerSentEvent):
        """
        Push a new server-sent event to all subscribed clients

        Parameters
        ----------
        sse : ServerSentEvent
            The server-sent event to send
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp_ms = int(now.timestamp() * 1000)
        if timestamp_ms != self._last_snowflake_ms:
            self._last_snowflake_ms = timestamp_ms
            self._sequence_id = 0
        sse.id = make_snowflake(timestamp_ms, 1, 1, self._sequence_id, self._id_epoch)
        self._sequence_id += 1

        for i in range(len(self.listeners) - 1, -1, -1):
            try:
                self.listeners[i].put_nowait(sse)
            except asyncio.QueueFull:
                del self.listeners[i]
        _logger.debug(
            "Pushed SSE data:\n%s",
            {
                "id": sse.id,
                "event": sse.event,
                "data": sse.data,
                "retry": sse.retry,
                "comment": sse.comment,
            },
        )
        self.recent_events.append(SentEvent(now, sse))
        self.save_recent_events()

    def clean_up_recent_events(self):
        """
        Remove recently-sent server-side events from history that are older than the
        number of minutes specified in `max_event_age`.

        By default, events from more than 15 minutes ago will be purged.
        """
        dt = datetime.datetime.now(datetime.timezone.utc)
        self.recent_events = list(
            filter(
                lambda e: dt - e.timestamp
                <= datetime.timedelta(minutes=self.max_event_age),
                self.recent_events,
            )
        )

    def get_recent_events(self, last_id: int) -> List[SentEvent]:
        """
        Retrieve the most recently-sent events, oldest first, from the given ID onwards

        Parameters
        ----------
        last_id : int
            The snowflake ID of the last received tweet
        """
        self.clean_up_recent_events()
        return [
            e.event for e in filter(lambda e: last_id < e.event.id, self.recent_events)
        ]
