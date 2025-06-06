# ==============================================================================
# penny_v2_api/core/event_bus.py
# ==============================================================================
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Type, TypeVar, DefaultDict, List

logger_event_bus = logging.getLogger(__name__)
T_Event = TypeVar("T_Event")

class EventBus:
    def __init__(self):
        self._async_subscribers: DefaultDict[Type, List[Callable]] = defaultdict(list)

    def subscribe_async(self, event_type: Type[T_Event], coro_callback: Callable[[T_Event], asyncio.Future]):
        self._async_subscribers[event_type].append(coro_callback)

    async def publish(self, event: T_Event):
        event_type = type(event)
        if self._async_subscribers[event_type]:
            tasks = [cb(event) for cb in self._async_subscribers[event_type]]
            await asyncio.gather(*tasks, return_exceptions=True)