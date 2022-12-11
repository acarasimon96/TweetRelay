from tweepy import StreamResponse  # noqa: TC002

from .event import SSE_EVENT_NAME, SingletonEventEmitter, make_sse


class BaseProcessor:
    """
    The base class for creating stream response (tweet) processors, which perform
    specific actions every time it receives a tweet from the stream client.
    """

    _ee = SingletonEventEmitter()

    async def on_data(self, data: StreamResponse):
        """
        |coroutine|

        This is called when a tweet was received from the stream client.

        Parameters
        ----------
        data : StreamResponse
            A response (tweet or error message) from Twitter that was picked
            up by the stream client
        """
        raise NotImplementedError

    async def announce(self, sse_event_name: str, payload: str):
        """
        Create a new `ServerSentEvent` object and send it to the message announcer

        Parameters
        ----------
        sse_event_name : str
            The name of the event type
        payload : str
            A string of data to be sent
        """
        sse = make_sse(event=sse_event_name, data=payload)
        await self._ee.emit_async(SSE_EVENT_NAME, sse)
