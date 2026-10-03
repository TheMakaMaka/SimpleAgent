import ast
import json
import operator as op
import platform
from datetime import datetime

from .registry import register, err


@register(
    name="get_weather",
    description="查询指定城市的天气（占位实现）",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
        # P9：显式封闭（JSON Schema 默认允许任意键 ⇒ 传错键会被静默忽略）。
        "additionalProperties": False,
    },
    profiles=("general",),
)
async def get_weather(city: str) -> str:
    return f"{city} 当前晴朗，温度 22°C"


# ---------- 安全算术 ----------
_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


@register(
    name="calculate",
    description="计算数学表达式（仅支持 + - * / // % ** 和括号、数字）",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式，如 2+3*(4-1)"}
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
    profiles=("general",),
)
async def calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval_node(tree.body))
    except Exception as e:
        return err(f"计算失败: {e}")


@register(
    name="get_system_info",
    description="获取当前系统信息，包括操作系统和当前时间",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
        # 无参工具也必须封闭：否则它接受任意键且被静默忽略。
        "additionalProperties": False,
    },
    profiles=("general", "coding"),
)
async def get_system_info() -> str:
    return json.dumps(
        {
            "操作系统": platform.system(),
            "Python": platform.python_version(),
            "当前时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        ensure_ascii=False,
        indent=2,
    )