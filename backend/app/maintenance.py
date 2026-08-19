import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class MaintenanceGate:
    """Drains in-flight work and blocks new API work during an exclusive restore."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._active = 0
        self._maintenance = False

    @property
    def active(self) -> bool:
        return self._maintenance

    async def begin_request(self) -> bool:
        async with self._condition:
            if self._maintenance:
                return False
            self._active += 1
            return True

    async def finish_request(self) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    @asynccontextmanager
    async def background_activity(self) -> AsyncIterator[None]:
        async with self._condition:
            while self._maintenance:
                await self._condition.wait()
            self._active += 1
        try:
            yield
        finally:
            await self.finish_request()

    @asynccontextmanager
    async def exclusive_restore(self) -> AsyncIterator[None]:
        async with self._condition:
            if self._maintenance:
                raise RuntimeError("系统已经处于维护模式")
            self._maintenance = True
            # The restore HTTP request itself occupies one request slot.
            while self._active > 1:
                await self._condition.wait()
        try:
            yield
        finally:
            async with self._condition:
                self._maintenance = False
                self._condition.notify_all()
