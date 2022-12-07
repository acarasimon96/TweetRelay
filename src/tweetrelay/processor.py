from tweepy import StreamResponse  # noqa: TC002

from .event import SSE_EVENT_NAME, SingletonEventEmitter, make_sse


class BaseProcessor:
    _ee = SingletonEventEmitter()

    async def on_data(self, data: StreamResponse):
        raise NotImplementedError

    async def announce(self, sse_event_name: str, payload: str):
        sse = make_sse(event=sse_event_name, data=payload)
        await self._ee.emit_async(SSE_EVENT_NAME, sse)
