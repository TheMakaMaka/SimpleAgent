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

# 工具调用的规范形（P9）：实参归一 + 产出检验 + 产出入信封。
# 必须在工具模块都导入**之后**再导入（它读 TOOLS_MAP 做 audit）。
from .tool_contract import (  # noqa: F401
    ALIASES,
    ENVELOPE_TOOLS,
    NORMALIZATION_RULES,
    ToolArgError,
    audit as tool_contract_audit,
    build_envelope,
    describe_contract,
    envelope_of,
    envelope_policy,
    error_result,
    normalize_args,
    try_normalize,
    unwrap_payload,
    validate_result,
)

__all__ = [
    "TOOLS_MAP",
    "tool_schemas",
    "register",
    "err",
    "truncate",
    "is_error_result",
    "ALIASES",
    "ENVELOPE_TOOLS",
    "NORMALIZATION_RULES",
    "ToolArgError",
    "tool_contract_audit",
    "build_envelope",
    "describe_contract",
    "envelope_of",
    "envelope_policy",
    "error_result",
    "normalize_args",
    "try_normalize",
    "unwrap_payload",
    "validate_result",
]