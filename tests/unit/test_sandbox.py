import pytest

from engine.strategy.sandbox import StrategySandboxViolation, validate_code

VALID_STRATEGY = """
from ate_smp import StrategyBase, Signal

class MyStrategy(StrategyBase):
    def initialize(self, config):
        pass
    def on_bar(self, bar):
        return []
    def on_tick(self, tick):
        return []
    def on_fill(self, fill):
        pass
    def get_parameters_schema(self):
        return []
    def get_win_probability(self):
        return 0.5
    def get_win_loss_ratio(self):
        return 1.0
    def get_state(self):
        return {}
    def set_state(self, state):
        pass
"""


def test_valid_strategy_passes():
    validate_code(VALID_STRATEGY)  # should not raise


def test_missing_strategy_base_rejected():
    source = "class NotAStrategy:\n    pass\n"
    with pytest.raises(StrategySandboxViolation, match="no StrategyBase subclass"):
        validate_code(source)


def test_syntax_error_rejected():
    with pytest.raises(StrategySandboxViolation, match="syntax error"):
        validate_code("def broken(:\n")


@pytest.mark.parametrize(
    "forbidden_import",
    [
        "import os",
        "import subprocess",
        "import socket",
        "import shutil",
        "import pickle",
        "import threading",
        "import asyncio",
        "import sys",
        "import importlib",
        "from os import path",
        "from urllib import request",
    ],
)
def test_forbidden_modules_rejected(forbidden_import):
    source = f"{forbidden_import}\nfrom ate_smp import StrategyBase\nclass S(StrategyBase):\n    pass\n"
    with pytest.raises(StrategySandboxViolation, match="forbidden import"):
        validate_code(source)


def test_import_outside_allowlist_rejected():
    source = "import somerandompkg\nfrom ate_smp import StrategyBase\nclass S(StrategyBase):\n    pass\n"
    with pytest.raises(StrategySandboxViolation, match="not in allow-list"):
        validate_code(source)


@pytest.mark.parametrize(
    "builtin_usage",
    [
        "open('x')",
        "exec('x')",
        "eval('x')",
        "compile('x', 'x', 'exec')",
        "globals()",
        "locals()",
        "vars()",
        "input()",
        "breakpoint()",
    ],
)
def test_forbidden_builtins_rejected(builtin_usage):
    source = (
        "from ate_smp import StrategyBase\n"
        "class S(StrategyBase):\n"
        f"    def f(self):\n        return {builtin_usage}\n"
    )
    with pytest.raises(StrategySandboxViolation, match="forbidden builtin usage"):
        validate_code(source)


@pytest.mark.parametrize(
    "attr",
    ["__subclasses__", "__bases__", "__mro__", "__globals__", "__builtins__", "__code__"],
)
def test_forbidden_dunder_attributes_rejected(attr):
    source = (
        "from ate_smp import StrategyBase\n"
        "class S(StrategyBase):\n"
        f"    def f(self):\n        return self.{attr}\n"
    )
    with pytest.raises(StrategySandboxViolation, match="forbidden attribute access"):
        validate_code(source)


def test_allowed_third_party_imports_pass():
    source = (
        "import numpy\nimport pandas\nimport math\nimport statistics\n"
        "from ate_smp import StrategyBase\nclass S(StrategyBase):\n    pass\n"
    )
    validate_code(source)
