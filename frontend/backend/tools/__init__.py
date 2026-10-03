from .registry import (
    TOOLS_MAP,
    tool_schemas,
    register,
    err,
    truncate,
    is_error_result,
)

# 显式导入所有含 @register 的模块
from . import basic          # noqa: F401
from . import files          # noqa: F401
from . import net            # noqa: F401
from . import parse          # noqa: F401
from . import code_checks    # noqa: F401
from . import python_exec    # noqa: F401
from . import verify         # noqa: F401
from . import quality        # noqa: F401
from . import arch           # noqa: F401
from . import reflect        # noqa: F401
from . import docs           # noqa: F401

__all__ = [
    "TOOLS_MAP",
    "tool_schemas",
    "register",
    "err",
    "truncate",
    "is_error_result",
]