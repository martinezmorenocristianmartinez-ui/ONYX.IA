import asyncio
import threading

from onyx.brain.interfaces import BrainResult
from onyx.brain.processor import Processor, _set_tool_registry
from onyx.brain.router import Router
from onyx.brain.planner import Planner
from onyx.brain.context import Context


class Brain:

    def __init__(self, tool_declarations=None, local_tool_names=None):
        self.processor = Processor()
        self.router = Router()
        self.planner = Planner()
        self.context = Context()
        self._session = None
        self._loop = None
        if tool_declarations is not None and local_tool_names is not None:
            _set_tool_registry(tool_declarations, local_tool_names)

    def set_cloud_session(self, session, loop):
        self._session = session
        self._loop = loop

    def has_cloud(self) -> bool:
        return self._session is not None and self._loop is not None

    def send_to_cloud(self, text: str):
        if not self.has_cloud():
            return
        asyncio.run_coroutine_threadsafe(
            self._session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True,
            ),
            self._loop,
        )

    def process_local(self, text: str, tool_dispatch_fn=None) -> BrainResult:
        return self.processor.process(text, tool_dispatch_fn=tool_dispatch_fn)
