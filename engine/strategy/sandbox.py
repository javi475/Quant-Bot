"""Static (AST-based) code validation and process resource limits for uploaded
strategy modules (DOC 3 §6). validate_code() runs *before* a strategy is ever
imported/exec'd; apply_resource_limits() is called inside the strategy
subprocess (engine/strategy/runtime.py) immediately before importing the
strategy module."""

from __future__ import annotations

import ast
import sys

FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "shutil",
        "pathlib",
        "io",
        "pickle",
        "shelve",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "signal",
        "fcntl",
        "resource",
        "sys",
        "importlib",
    }
)

FORBIDDEN_BUILTINS: frozenset[str] = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "input",
        "breakpoint",
        "memoryview",
    }
)

# Dunder "escape hatches" that can be used to reach forbidden functionality
# (e.g. ().__class__.__bases__[0].__subclasses__() sandbox breakout patterns).
FORBIDDEN_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__class__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "__import__",
    }
)

# Stdlib + pre-approved third-party packages a strategy may import (DOC 3 §6).
ALLOWED_MODULE_ROOTS: frozenset[str] = frozenset(
    {
        "__future__",
        "math",
        "statistics",
        "datetime",
        "typing",
        "dataclasses",
        "abc",
        "collections",
        "itertools",
        "functools",
        "decimal",
        "enum",
        "copy",
        "re",
        "numpy",
        "pandas",
        "statsmodels",
        "scipy",
        "ta",
        "ate_smp",
    }
)


class StrategySandboxViolation(Exception):
    """Raised when a strategy module fails static validation."""


def validate_code(source: str) -> None:
    """Parses `source` and raises StrategySandboxViolation listing every
    violation found: forbidden imports, imports outside the allow-list,
    forbidden builtin usage, forbidden dunder-attribute access, or the
    absence of a StrategyBase subclass. Raises on syntax errors too."""

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise StrategySandboxViolation(f"syntax error: {exc}") from exc

    violations: list[str] = []
    found_strategy_subclass = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"forbidden import: {alias.name}")
                elif root not in ALLOWED_MODULE_ROOTS:
                    violations.append(f"import not in allow-list: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0] if module else ""
            if root in FORBIDDEN_MODULES:
                violations.append(f"forbidden import: {module}")
            elif root and root not in ALLOWED_MODULE_ROOTS:
                violations.append(f"import not in allow-list: {module}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
            violations.append(f"forbidden builtin usage: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            violations.append(f"forbidden attribute access: {node.attr}")
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = (
                    base.id
                    if isinstance(base, ast.Name)
                    else base.attr
                    if isinstance(base, ast.Attribute)
                    else None
                )
                if base_name == "StrategyBase":
                    found_strategy_subclass = True

    if not found_strategy_subclass:
        violations.append("no StrategyBase subclass found")

    if violations:
        raise StrategySandboxViolation("; ".join(violations))


def apply_resource_limits(
    memory_bytes: int = 512 * 1024 * 1024,
    cpu_seconds: int = 30,
) -> None:
    """Applies POSIX resource limits (DOC 3 §6: 512MB RLIMIT_AS, 30s cumulative
    CPU, 0 file size, 1 process, 0 new file descriptors). Must be called inside
    the strategy subprocess before importing the strategy module. This is a
    no-op on non-POSIX platforms (native Windows) — production and Docker-based
    dev both run the strategy subprocess inside a Linux container, where these
    limits apply."""

    if sys.platform == "win32":
        return

    import resource

    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
    resource.setrlimit(resource.RLIMIT_NOFILE, (0, 0))
