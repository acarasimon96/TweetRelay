import asyncio
import datetime
import logging
from typing import Any, NamedTuple, Optional

from pymitter import EventEmitter
from sse_starlette import ServerSentEvent

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


# TODO: might need to rename this with more concise wording
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

    def __init__(self, epoch: int = TWEPOCH):
        self.listeners: list[asyncio.Queue] = []
        self.recent_events: list[SentEvent] = []
        self._id_epoch = epoch
        self._ee.on("announce-sse", self.announce)

    def listen(self) -> asyncio.Queue:
        """
        Subscribe to events sent by the `MessageAnnouncer` instance
        """
        # maxsize param defines maximum number of events that can be sent at once
        msg_q = asyncio.Queue(maxsize=10)
        self.listeners.append(msg_q)
        return msg_q

    def announce(self, sse: ServerSentEvent):
        """
        Push a new server-sent event to all subscribed clients

        Parameters
        ----------
        sse : ServerSentEvent
            The server-sent event to send
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        sse.id = make_snowflake(int(now.timestamp()), 1, 1, 1, self._id_epoch)

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

    def clean_up_recent_events(self):
        """
        Remove recently-sent server-side events from history that are older than
        15 minutes
        """
        dt = datetime.datetime.now(datetime.timezone.utc)
        self.recent_events = list(
            filter(
                lambda e: dt - e.timestamp <= datetime.timedelta(minutes=15),
                self.recent_events,
            )
        )

    def get_recent_events(self, last_id: int) -> list[SentEvent]:
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
