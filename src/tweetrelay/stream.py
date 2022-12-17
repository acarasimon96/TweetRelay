import asyncio
import logging
import sys
from typing import Dict, Iterable, Sequence

import aiohttp
from tweepy import StreamResponse
from tweepy.asynchronous.streaming import AsyncStreamingClient

from ._utils import tweepy_ver_before
from .event import SingletonEventEmitter
from .processor import BaseProcessor

TRACE_LOG_LEVEL = 5
_logger = logging.getLogger(__name__)


class StreamClient(AsyncStreamingClient):
    """
    A Twitter API v2 filtered stream client that listens for new tweets as soon as they
    are published and passes those tweets to stream response processors
    """

    _ee = SingletonEventEmitter()
    running = False

    def __init__(
        self,
        bearer_token: str,
        processors: Sequence[BaseProcessor],
        expansions_fields: Dict[str, Iterable[str]],
        *args,
        **kwargs,
    ):
        self._expansions_fields = expansions_fields
        for processor in processors:
            self._ee.on("on_data", processor.on_data)

        return super().__init__(bearer_token, *args, **kwargs)

    async def on_connect(self):
        return await super().on_connect()

    async def on_connection_error(self):
        msg = "Stream connection has errored or timed out. Reconnecting the stream"
        if tweepy_ver_before("4.12.1"):
            exc_type, exc_value, _trace = sys.exc_info()
            _logger.error("%s\n%s: %s", msg, str(exc_type)[8:-2], exc_value)
        else:
            _logger.error(msg)

    async def on_closed(self, response: aiohttp.ClientResponse):
        if not self.task.cancelled():
            _logger.error(
                "Stream connection closed by Twitter. Reconnecting the stream"
            )

    async def on_keep_alive(self):
        _logger.log(TRACE_LOG_LEVEL, "Received keep-alive signal")

    async def on_request_error(self, status_code):
        _logger.error(
            "Stream encountered HTTP Error: %d. Reconnecting the stream", status_code
        )

    async def on_response(self, response: StreamResponse):
        await super().on_response(response)
        # Emit events to processors only when a tweet was received
        if response.data:
            await self._ee.emit_async("on_data", response)

    def disconnect(self):
        self.running = False
        if not self.session.closed:
            _logger.info("Disconnecting the stream")
        return super().disconnect()

    def run(self) -> asyncio.Task:
        self.running = True
        _logger.info("Connecting the stream")
        return self.filter(**self._expansions_fields)

    def run_forever(self):
        """
        Run the stream forever (even after uncaught exceptions) until we manually
        call `disconnect()`
        """
        self.running = True

        async def task():
            while self.running:
                await self.run()
                if self.running:
                    _logger.info("Restarting the stream")
                    await asyncio.sleep(1)

        return asyncio.create_task(task())
