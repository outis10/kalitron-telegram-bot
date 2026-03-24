from typing import Protocol


class InboundChannelAdapter(Protocol):
    def register(self) -> None: ...
