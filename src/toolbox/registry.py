from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass

import toolbox.tools
from toolbox.tools.base import Tool


@dataclass(frozen=True)
class ToolRegistry:
    tools: tuple[Tool, ...]

    @classmethod
    def discover(cls) -> "ToolRegistry":
        tools: list[Tool] = []
        for module_info in pkgutil.iter_modules(toolbox.tools.__path__):
            if module_info.name.startswith("_") or module_info.name == "base":
                continue
            module = importlib.import_module(f"toolbox.tools.{module_info.name}")
            tool = getattr(module, "TOOL", None)
            if isinstance(tool, Tool):
                tools.append(tool)
        tools.sort(key=lambda t: t.name.lower())
        return cls(tools=tuple(tools))
