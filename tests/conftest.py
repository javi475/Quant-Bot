import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)
# `ate_smp` is distributed as a standalone SDK package rooted at sdk/ (DOC 3 §10);
# add it so `import ate_smp` resolves the same way it will for strategy authors.
sys.path.insert(0, os.path.join(_ROOT, "sdk"))
