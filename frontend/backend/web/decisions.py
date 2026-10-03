"""决策审批页：手机端交互界面。

为什么用网页而不是 IM 内回复
----------------------------
各平台 bot 的双向能力差异极大（钉钉群机器人 webhook 只能发不能收；
个人微信官方无 API）。把交互放在网页，投递层就只需「发一条带链接的消息」，
任何 IM 都能用，且审批页能直接渲染**结构化上下文**（计划声明、验证失败细节、
涉及文件、历史失败），这是聊天消息做不到的。

安全
----
默认无鉴权，适合局域网自用。设 `AGENT_APPROVAL_TOKEN` 后，
所有决策接口都要求 `?t=<token>`——手机端把带 token 的链接收藏为书签即可。
token 是唯一凭据，**不要提交进仓库**（已加入 .gitignore）。
"""

import html
import os

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from core.decisions import DecisionManager

router = APIRouter(tags=["decisions"])

_manager: DecisionManager | None = None


def manager() -> DecisionManager:
    global _manager
    if _manager is None:
        _manager = DecisionManager()
    return _manager


def _token_required() -> str:
    return (os.getenv("AGENT_APPROVAL_TOKEN") or "").strip()


def _check_token(t: str | None) -> None:
    want = _token_required()
    if want and t != want:
        raise HTTPException(403, "缺少或错误的访问令牌")


def _page(title: str, body: str) -> str:
    """极简移动端页面：无外部依赖（局域网可能没有外网），viewport 适配手机。"""
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 12px; line-height: 1.6; }}
  h1 {{ font-size: 1.15rem; margin: 8px 0 12px; }}
  h2 {{ font-size: 1rem; margin: 16px 0 6px; }}
  .card {{ border: 1px solid #8884; border-radius: 10px; padding: 12px;
           margin-bottom: 12px; }}
  .muted {{ opacity: .65; font-size: .85rem; }}
  .kv {{ margin: 4px 0; font-size: .9rem; word-break: break-all; }}
  pre {{ background: #8881; padding: 8px; border-radius: 6px; overflow-x: auto;
         font-size: .8rem; white-space: pre-wrap; word-break: break-all; }}
  .btns {{ display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }}
  button {{ font-size: 1rem; padding: 14px; border-radius: 10px;
            border: 1px solid #8886; background: #8881; cursor: pointer; }}
  button.danger {{ border-color: #d33; color: #d33; }}
  button.primary {{ background: #2b7; color: #fff; border-color: #2b7; }}
  a {{ color: #2b7; }}
  .empty {{ text-align: center; padding: 40px 0; opacity: .6; }}
  .pill {{ display:inline-block; padding:1px 8px; border-radius:999px;
           background:#8882; font-size:.75rem; margin-left:6px; }}
</style></head>
<body>{body}</body></html>"""


@router.get("/decisions", response_class=HTMLResponse)
async def list_decisions(t: str | None = None, all: int = 0):
    _check_token(t)
    mgr = manager()
    pending = mgr.pending()
    items = mgr.store.list() if all else pending

    parts = [f"<h1>待决策 {len(pending)} 项</h1>"]
    if not items:
        parts.append('<div class="empty">没有待处理的决策</div>')
    for d in items:
        badge = f'<span class="pill">{html.escape(d.status)}</span>'
        parts.append(
            f'<div class="card">'
            f'<div><a href="/decisions/{html.escape(d.id)}'
            f'{("?t=" + html.escape(t)) if t else ""}">'
            f'{html.escape(d.question)}</a>{badge}</div>'
            f'<div class="muted">{html.escape(d.created_at)} · '
            f'{html.escape(d.kind)} · cycle {html.escape(d.cycle_id[:16])}</div>'
            f'</div>'
        )
    if not all:
        link = f"/decisions?all=1" + (f"&t={html.escape(t)}" if t else "")
        parts.append(f'<div class="muted"><a href="{link}">查看全部（含已处理）</a></div>')
    return _page("待决策", "".join(parts))


@router.get("/decisions/{decision_id}", response_class=HTMLResponse)
async def show_decision(decision_id: str, t: str | None = None):
    _check_token(t)
    d = manager().get(decision_id)
    if d is None:
        return HTMLResponse(_page("未找到", "<h1>决策不存在</h1>"), status_code=404)

    ctx = d.context or {}
    body = [f"<h1>{html.escape(d.question)}</h1>"]
    body.append(
        f'<div class="muted">cycle {html.escape(d.cycle_id)} · 第 {ctx.get("attempt", "?")} 次尝试'
        f' · 状态 {html.escape(d.status)}</div>'
    )

    # ---- 结构化上下文：这是我们比聊天消息强的地方 ----
    body.append('<div class="card"><h2>目标</h2>'
                f'<div class="kv">{html.escape(str(ctx.get("goal", "")))}</div>')
    if ctx.get("error"):
        body.append('<h2>失败原因</h2>'
                    f'<div class="kv">{html.escape(str(ctx["error"])[:400])}</div>')
    if ctx.get("touched"):
        body.append('<h2>涉及文件</h2><div class="kv">'
                    + html.escape(", ".join(ctx["touched"]))
                    + "</div>")
    if ctx.get("declared"):
        body.append('<h2>计划声明产出</h2><div class="kv">'
                    + html.escape(", ".join(str(x) for x in ctx["declared"]))
                    + "</div>")
    if ctx.get("violations"):
        rows = "".join(
            f'<div class="kv">· [{html.escape(str(v.get("kind")))}] '
            f'{html.escape(str(v.get("path") or ""))} — '
            f'{html.escape(str(v.get("message") or "")[:160])}</div>'
            for v in ctx["violations"]
        )
        body.append(f"<h2>清单校验问题</h2>{rows}")
    if ctx.get("verify"):
        v = ctx["verify"]
        body.append("<h2>验证</h2>"
                    f'<div class="kv">通过: {html.escape(str(v.get("passed")))}</div>'
                    f'<div class="kv">{html.escape(str(v.get("detail") or "")[:300])}</div>')
    if ctx.get("rollback_to"):
        body.append('<h2>回退目标</h2>'
                    f'<div class="kv">{html.escape(str(ctx["rollback_to"]))}</div>')
    body.append('<div class="muted">超时（{}</div>'.format(
        html.escape(d.expires_at or "无") + "）后默认动作: " + html.escape(d.default)))
    body.append("</div>")

    # ---- 作答 ----
    if d.status == "pending":
        forms = ['<div class="btns">']
        for o in d.options:
            cls = "danger" if o.danger else ("primary" if not o.danger and o.value in ("retry", "allow") else "")
            forms.append(
                f'<form method="post" action="/decisions/{html.escape(d.id)}/answer">'
                f'<input type="hidden" name="value" value="{html.escape(o.value)}">'
                + (f'<input type="hidden" name="t" value="{html.escape(t)}">' if t else "")
                + f'<button class="{cls}" type="submit">{html.escape(o.label)}'
                + (f'<div class="muted">{html.escape(o.hint)}</div>' if o.hint else "")
                + "</button></form>"
            )
        forms.append("</div>")
        body.append("".join(forms))
    else:
        body.append(f'<div class="card"><h2>已处理</h2>'
                    f'<div class="kv">结果: {html.escape(d.answer or "(无)")}</div>'
                    f'<div class="kv muted">{html.escape(d.answered_at)} '
                    f'{html.escape(d.answered_by)}</div></div>')

    back = "/decisions" + (f"?t={html.escape(t)}" if t else "")
    body.append(f'<div class="muted"><a href="{back}">← 返回列表</a></div>')
    return _page("决策", "".join(body))


@router.post("/decisions/{decision_id}/answer")
async def answer_decision(decision_id: str, value: str = Form(...), t: str | None = Form(None)):
    _check_token(t)
    ok, msg = manager().answer(decision_id, value, by="mobile")
    if not ok:
        return HTMLResponse(
            _page("失败", f"<h1>作答失败</h1><div class='kv'>{html.escape(msg)}</div>"
                          f"<div class='muted'><a href='/decisions'>返回</a></div>"),
            status_code=400,
        )
    # 作完答回列表，手机上少点一次
    return RedirectResponse(
        url="/decisions" + (f"?t={t}" if t else ""), status_code=303
    )
