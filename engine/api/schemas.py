"""Wire schemas for the Engine internal API (:9000, DOC 2 §6). `config` on
LoadStrategyRequest is the same JSON shape produced by
engine.strategy.serialization.encode_config — decoded with decode_config()
before being handed to the Engine."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoadStrategyRequest(BaseModel):
    strategy_id: str
    config: dict
    module_path: Optional[str] = None
    class_name: Optional[str] = None


class SwapStrategyRequest(BaseModel):
    module_path: str
    class_name: str
