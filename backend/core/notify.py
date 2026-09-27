"""通知投递：把待决策项推到你的手机上。

设计要点
--------
**任何 IM 都只需要「发一条带链接的消息」。** 交互式审批放在网页里，
所以不受各平台 bot 能力差异影响——钉钉群机器人、企业微信机器人、Slack
Incoming Webhook、Telegram、甚至邮件，都只是 POST 一个 JSON 的差别。

各平台现实情况（2026-09 核实）：
  - 钉钉群自定义机器人：个人可用、免费、webhook 即可发消息  → 最实际
  - 企业微信机器人：正规 API，但需要企业/组织
  - 个人微信：官方无 API，第三方方案违反用户协议，**不建议**
  - 个人 QQ：官方 bot 需企业资质审核
  - Telegram：个人可用，但国内网络需自行解决可达性

所以本模块把「发消息」抽象成 Notifier，具体平台是可选适配器。
默认 ConsoleNotifier 永远可用（不影响流程，只是把消息打到日志）。
"""

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .decisions import PendingDecision


@dataclass
class NotifyResult:
    ok: bool
    channel: str
    detail: str = ""


class Notifier(Protocol):
    name: str
    def send(self, decision: PendingDecision, link: str) -> NotifyResult: ...


# ============================================================
# 默认：控制台（永远可用，不发任何网络请求）
# ============================================================
class ConsoleNotifier:
    """把决策打到 stdout。不依赖任何外部服务，测试与本地开发用。"""

    name = "console"

    def send(self, decision: PendingDecision, link: str) -> NotifyResult:
        print("\n" + "=" * 70)
        print("[需要你决策]")
        print(decision.to_markdown())
        print(f"审批链接: {link}")
        print("=" * 70, flush=True)
        return NotifyResult(ok=True, channel=self.name)


# ============================================================
# 钉钉群自定义机器人
# ============================================================
class DingTalkNotifier:
    """钉钉群自定义机器人 webhook。

    个人可用、免费。在钉钉群里「群设置 → 智能群助手 → 添加机器人 → 自定义」
    拿到 webhook 地址；若开启了加签，再填 secret。

    安全提醒：webhook 里含 access_token，等同于密码，**不要提交进仓库**。
    本模块只从环境变量读取。
    """

    name = "dingtalk"

    def __init__(self, webhook: str, secret: str = "", timeout: float = 8.0):
        self.webhook = webhook
        self.secret = secret
        self.timeout = timeout

    def _signed_url(self) -> str:
        if not self.secret:
            return self.webhook
        # 加签：HmacSHA256(secret, "{timestamp}\n{secret}") → base64 → urlencode
        import base64
        import hashlib
        import hmac
        import time
        import urllib.parse

        ts = str(round(time.time() * 1000))
        string_to_sign = f"{ts}\n{self.secret}"
        digest = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest).decode("utf-8"))
        sep = "&" if "?" in self.webhook else "?"
        return f"{self.webhook}{sep}timestamp={ts}&sign={sign}"

    def send(self, decision: PendingDecision, link: str) -> NotifyResult:
        text = (
            f"### ⚠ 需要你决策\n\n"
            f"**{decision.question}**\n\n"
            f"{decision.to_markdown()}\n\n"
            f"[👉 点击查看并决策]({link})\n\n"
            f"> 决策 ID: `{decision.id}`"
        )
        payload = {"msgtype": "markdown", "markdown": {"title": "需要你决策", "text": text}}

        try:
            req = urllib.request.Request(
                self._signed_url(),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            if data.get("errcode") == 0:
                return NotifyResult(ok=True, channel=self.name)
            return NotifyResult(ok=False, channel=self.name,
                                detail=f"{data.get('errcode')}: {data.get('errmsg')}")
        except Exception as e:
            return NotifyResult(ok=False, channel=self.name, detail=str(e)[:200])


# ============================================================
# 通用 webhook（企业微信 / Slack / 自建中转都可用）
# ============================================================
class WebhookNotifier:
    """POST 一段 JSON 到任意 webhook。

    企业微信机器人: {"msgtype":"markdown","markdown":{"content": ...}}
    Slack:         {"text": ...}
    用 `template` 指定格式；默认按企业微信。
    """

    name = "webhook"

    def __init__(self, url: str, template: str = "wecom", timeout: float = 8.0):
        self.url = url
        self.template = template
        self.timeout = timeout

    def _payload(self, text: str) -> dict:
        if self.template == "slack":
            return {"text": text}
        if self.template == "plain":
            return {"text": text}
        # wecom / 默认
        return {"msgtype": "markdown", "markdown": {"content": text}}

    def send(self, decision: PendingDecision, link: str) -> NotifyResult:
        text = f"⚠ 需要你决策：{decision.question}\n\n{decision.to_markdown()}\n\n{link}"
        try:
            req = urllib.request.Request(
                self.url,
                data=json.dumps(self._payload(text)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            # 企业微信成功返回 errcode=0；Slack 返回 "ok"
            ok = data.get("errcode") == 0 or data.get("ok") is True or body.strip() == "ok"
            return NotifyResult(ok=bool(ok), channel=self.name, detail=body[:120])
        except Exception as e:
            return NotifyResult(ok=False, channel=self.name, detail=str(e)[:200])


# ============================================================
# 工厂
# ============================================================
def build_notifier(channel: str | None = None) -> Notifier:
    """按配置选择投递通道。**未配置时退化为控制台，绝不阻塞流程。**

    环境变量：
      AGENT_NOTIFY_CHANNEL = console | dingtalk | webhook | none
      AGENT_DINGTALK_WEBHOOK / AGENT_DINGTALK_SECRET
      AGENT_WEBHOOK_URL / AGENT_WEBHOOK_TEMPLATE (wecom|slack|plain)
    """
    ch = (channel or os.getenv("AGENT_NOTIFY_CHANNEL") or "console").strip().lower()

    if ch in ("none", "off", "disabled"):
        return ConsoleNotifier()      # 仍然打到日志，只是不发网络请求

    if ch == "dingtalk":
        hook = os.getenv("AGENT_DINGTALK_WEBHOOK", "").strip()
        if not hook:
            print("[notify] 未配置 AGENT_DINGTALK_WEBHOOK，退化为控制台输出")
            return ConsoleNotifier()
        return DingTalkNotifier(hook, os.getenv("AGENT_DINGTALK_SECRET", "").strip())

    if ch == "webhook":
        url = os.getenv("AGENT_WEBHOOK_URL", "").strip()
        if not url:
            print("[notify] 未配置 AGENT_WEBHOOK_URL，退化为控制台输出")
            return ConsoleNotifier()
        return WebhookNotifier(url, os.getenv("AGENT_WEBHOOK_TEMPLATE", "wecom").strip())

    return ConsoleNotifier()


def channel_status() -> dict:
    """诊断用：当前配置下会走哪个通道、是否具备必要条件。"""
    ch = (os.getenv("AGENT_NOTIFY_CHANNEL") or "console").strip().lower()
    ready = True
    missing: list[str] = []
    if ch == "dingtalk" and not os.getenv("AGENT_DINGTALK_WEBHOOK", "").strip():
        ready, _ = False, missing.append("AGENT_DINGTALK_WEBHOOK")
    if ch == "webhook" and not os.getenv("AGENT_WEBHOOK_URL", "").strip():
        ready, _ = False, missing.append("AGENT_WEBHOOK_URL")
    return {
        "channel": ch or "console",
        "ready": ready,
        "missing": missing,
        "note": "未配置时退化为控制台输出，不会阻塞流程",
    }
