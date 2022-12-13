import asyncio
import json
import logging
from ipaddress import ip_address
from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Mapping,
    Optional,
    Sequence,
    Type,
    Union,
)

from sse_starlette.sse import AppStatus, EventSourceResponse, ServerSentEvent
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .event import MessageAnnouncer, make_sse
from .processor import BaseProcessor
from .settings import Settings, get_settings
from .stream import StreamClient
from snowflake import TWEPOCH

_logger = logging.getLogger(__name__)


class TweetRelay(Starlette):
    """
    This class manages dependencies between the Twitter API stream client (which
    listens for new tweets in realtime), stream response processors (which processes a
    tweet every time one is received), and the message announcer (which is responsible
    for sending server-sent events to all connected clients)
    """

    stream_client: StreamClient

    def __init__(
        self,
        processors: Sequence[BaseProcessor],
        expansions_fields: Optional[dict] = None,
        settings: Optional[Settings] = None,
        stream_client_cls: Type = StreamClient,
        sse_id_epoch: int = TWEPOCH,
        max_event_age: int = 15,
        ping_factory: Optional[Callable[..., ServerSentEvent]] = None,
        debug: bool = False,
        middleware: Optional[Sequence[Middleware]] = None,
        exception_handlers: Optional[
            Mapping[
                Any,
                Callable[
                    [Request, Exception],
                    Union[Response, Awaitable[Response]],
                ],
            ]
        ] = None,
        lifespan: Optional[Callable[["Starlette"], AsyncContextManager]] = None,
    ):
        routes = [Route("/", self.stream)]
        on_startup = [self.startup]
        on_shutdown = [self.shutdown]
        super().__init__(
            debug,
            routes,
            middleware,
            exception_handlers,
            on_startup,
            on_shutdown,
            lifespan,
        )

        self.announcer = MessageAnnouncer(max_event_age, sse_id_epoch)
        self._ping_factory = ping_factory

        if settings is None:
            settings = get_settings()
        assert isinstance(stream_client_cls, type) and issubclass(
            stream_client_cls, StreamClient
        ), "stream_client_cls must be of type StreamClient or a subclass of it"
        self.stream_client = stream_client_cls(
            settings.bearer_token, processors, expansions_fields or {}
        )

    def startup(self):
        """
        Connects the stream client when server starts up
        """
        if not self.stream_client.running:
            self.stream_client.run_forever()

    async def shutdown(self):
        """
        Disconnects stream client when server shuts down
        """
        if (
            isinstance(self.stream_client, StreamClient)
            and not self.stream_client.task.cancelled()
        ):
            self.stream_client.disconnect()
            # App shutdown is not over until `stream_client.task` finishes
            await self.stream_client.task

    @staticmethod
    async def event_generator(announcer: MessageAnnouncer, request: Request):
        sse_queue = announcer.listen()
        ip = ip_address(request.client.host)
        client_addr = f"{ip.compressed}"
        if request.client.port:
            client_addr = f"{client_addr}:{request.client.port}"

        # Send event backfill if Last-Event-ID header was provided
        last_id = int(request.headers.get("Last-Event-ID", "0"))
        if last_id:
            _logger.debug("Received Last-Event-ID: %s", last_id)
            for event in announcer.get_recent_events(last_id):
                yield event

        try:
            while True:
                # Wait for new events to arrive and send them to all connected clients
                # as they come in
                msg: ServerSentEvent = await sse_queue.get()
                yield msg
        except asyncio.CancelledError:
            # Clean up listener on disconnect/server shutdown
            try:
                announcer.listeners.remove(sse_queue)
            except ValueError:
                pass
            _logger.debug(
                "Cleaned up message queue for aborted connection from %s",
                client_addr,
            )

        if AppStatus.should_exit:
            # App is shutting down/reloading
            _logger.debug("Sending disconnect event to %s", client_addr)
            yield make_sse(
                json.dumps({"message": "Server is shutting down or restarting"}),
                event="disconnect",
                retry=25_000,
            )
        else:
            # Check if connection was really disconnected
            if await request.is_disconnected():
                _logger.debug("Connection from %s was disconnected", client_addr)

    async def stream(self, request: Request):
        """
        The main endpoint for pushing server-sent events to a client

        Parameters
        ----------
        request: Request
            An incoming request from a connected client
        """
        return EventSourceResponse(
            self.event_generator(self.announcer, request),
            ping=20,
            ping_message_factory=self._ping_factory,
        )
