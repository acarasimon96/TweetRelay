import asyncio
import json
import logging
from datetime import datetime
from ipaddress import ip_address

from sse_starlette.sse import AppStatus, EventSourceResponse, ServerSentEvent
from starlette.endpoints import HTTPEndpoint
from starlette.requests import Request

from .event import MessageAnnouncer, make_sse

_logger = logging.getLogger("tweetrelay.routes")


class StreamEndpoint(HTTPEndpoint):
    """
    The main endpoint for pushing server-sent events to a client
    """

    announcer = MessageAnnouncer()

    @staticmethod
    def ping_factory():
        return make_sse(datetime.utcnow(), event="ping")

    @staticmethod
    async def event_generator(announcer: MessageAnnouncer, request: Request):
        events = announcer.listen()
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
                # Wait for new events to arrive and send them to client as they come in
                msg: ServerSentEvent = await events.get()
                yield msg
        except asyncio.CancelledError:
            # Clean up listener on disconnect/server shutdown
            try:
                announcer.listeners.remove(events)
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

    def get(self, request: Request):
        return EventSourceResponse(
            self.event_generator(self.announcer, request),
            ping=20,
            ping_message_factory=self.ping_factory,
        )
