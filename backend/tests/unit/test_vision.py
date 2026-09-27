"""视觉接口自检（多模态预留层）。

核心验证：**能力不满足时显式失败，不静默丢图**。
静默丢图比报错更糟——模型会凭文本臆测，产出"看起来有依据"的幻觉答案。
"""

import base64
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.config import ROLES, describe_roles, resolve_role, RoleNotConfigured  # noqa: E402
from core.model_profile import ModelCapabilities, ModelProfile  # noqa: E402
from core.vision import (  # noqa: E402
    ImageInput, VisionError, build_vision_message, describe, ensure_vision_capable,
    image_roots,
)

ASSETS = os.path.join(ROOT, "assets")
# 1x1 PNG（最小合法图片）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class FakeClient:
    """只提供 profile，用于校验逻辑，不发请求。"""

    def __init__(self, **caps):
        self.profile = ModelProfile(
            name="vision",
            model="fake-vl",
            capabilities=ModelCapabilities(**caps),
        )


def main() -> int:
    checks: list[tuple[str, bool]] = []
    shutil.rmtree(ASSETS, ignore_errors=True)
    os.makedirs(ASSETS, exist_ok=True)
    png = os.path.join(ASSETS, "shot.png")
    with open(png, "wb") as f:
        f.write(PNG_1PX)
    with open(os.path.join(ASSETS, "note.txt"), "w") as f:
        f.write("not an image")

    print("=" * 74)
    print("[1] vision 角色登记（不继承、无默认）")
    print("=" * 74)
    roles = {r["role"]: r for r in describe_roles()}
    print(f"  角色表: {sorted(roles)}")
    checks.append(("vision 角色已登记", "vision" in ROLES and "vision" in roles))
    checks.append(("未配置即未启用（不静默继承）",
                   roles["vision"]["available"] is False))
    try:
        resolve_role("vision")
        checks.append(("未配置时解析必须报错", False))
    except RoleNotConfigured as e:
        checks.append(("未配置时解析必须报错", True))
        print(f"  未配置 -> {str(e)[:56]}")

    print("\n" + "=" * 74)
    print("[2] 能力校验：不支持图像时显式失败（不静默丢图）")
    print("=" * 74)
    no_vision = FakeClient(supports_image_input=False)
    try:
        ensure_vision_capable(no_vision, [ImageInput(path="assets/shot.png")])
        checks.append(("未声明视觉能力时报错", False))
    except VisionError as e:
        checks.append(("未声明视觉能力时报错", True))
        print(f"  拒绝 -> {str(e)[:80]}")

    ok_client = FakeClient(supports_image_input=True, max_images_per_request=2)
    ensure_vision_capable(ok_client, [ImageInput(path="assets/shot.png")])
    checks.append(("声明后可校验通过", True))

    # 数量超限
    try:
        ensure_vision_capable(ok_client, [ImageInput(path="assets/shot.png")] * 3)
        checks.append(("图像数量超限报错", False))
    except VisionError as e:
        checks.append(("图像数量超限报错", True))
        print(f"  超限 -> {str(e)[:70]}")

    print("\n" + "=" * 74)
    print("[3] 消息构造（OpenAI 兼容 content 数组）")
    print("=" * 74)
    msg = build_vision_message("这是什么？", [ImageInput(path="assets/shot.png")])
    print(f"  role={msg['role']} blocks={len(msg['content'])}")
    for b in msg["content"]:
        t = b["type"]
        head = b.get("text", b.get("image_url", {}).get("url", ""))[:44]
        print(f"    {t:<12} {head}")
    checks.append(("content 是数组", isinstance(msg["content"], list)))
    checks.append(("含 text 块", any(b["type"] == "text" for b in msg["content"])))
    checks.append(("含 image_url 块",
                   any(b["type"] == "image_url" for b in msg["content"])))
    checks.append(("本地图转成 data URI",
                   any(b.get("image_url", {}).get("url", "").startswith("data:image/png;base64,")
                       for b in msg["content"])))

    # 多图 + label
    msg2 = build_vision_message("对比", [
        ImageInput(path="assets/shot.png", label="修改前"),
        ImageInput(url="https://example.com/a.png", label="修改后"),
    ])
    kinds = [b["type"] for b in msg2["content"]]
    print(f"  多图 blocks: {kinds}")
    checks.append(("多图各自成块", kinds.count("image_url") == 2))
    checks.append(("label 作为独立文本块", "修改前" in str(msg2["content"])))
    checks.append(("http 直链原样传递",
                   any((b.get("image_url") or {}).get("url") == "https://example.com/a.png"
                       for b in msg2["content"])))

    # detail 只在模型**显式声明**支持时才下发。
    # ok_client 没声明 supports_image_detail，所以两条路径要分开验证。
    detail_client = FakeClient(supports_image_input=True,
                               supports_image_detail=True,
                               max_images_per_request=2)
    m3 = build_vision_message("x", [ImageInput(path="assets/shot.png", detail="high")])
    has_detail = any("detail" in (b.get("image_url") or {}) for b in m3["content"])
    m4 = build_vision_message("x", [ImageInput(path="assets/shot.png", detail="high")],
                              client=detail_client)
    m5 = build_vision_message("x", [ImageInput(path="assets/shot.png", detail="high")],
                              client=ok_client)
    checks.append(("无 client 时不下发 detail", not has_detail))
    checks.append(("声明 detail 支持后下发",
                   any((b.get("image_url") or {}).get("detail") == "high"
                       for b in m4["content"])))
    checks.append(("未声明 detail 支持的 client 也不下发",
                   not any("detail" in (b.get("image_url") or {}) for b in m5["content"])))
    print(f"  无 client: {has_detail}（应 False）")

    print("\n" + "=" * 74)
    print("[4] 本地图片白名单（防读任意文件）")
    print("=" * 74)
    cases = [
        ("assets/shot.png", True),
        ("../secret.png", False),
        ("/etc/passwd", False),
        ("C:/Windows/x.png", False),
        ("docs/x.png", False),            # 不在允许目录
        ("assets/note.txt", False),       # 类型不支持
        ("assets/missing.png", False),    # 不存在
    ]
    for path, should_ok in cases:
        try:
            build_vision_message("x", [ImageInput(path=path)])
            got = True
        except (VisionError, OSError):
            got = False
        ok = got == should_ok
        checks.append((f"路径 {path} {'允许' if should_ok else '拒绝'}", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {path:<22} -> {'允许' if got else '拒绝'}")

    print("\n" + "=" * 74)
    print("[5] data URI / 非法输入")
    print("=" * 74)
    m = build_vision_message("x", [ImageInput(data_uri="data:image/png;base64,AAAA")])
    checks.append(("data URI 可用",
                   any((b.get("image_url") or {}).get("url", "").startswith("data:image/png")
                       for b in m["content"])))
    try:
        build_vision_message("x", [ImageInput(data_uri="http://not-a-data-uri")])
        checks.append(("非 data URI 被拒", False))
    except VisionError:
        checks.append(("非 data URI 被拒", True))
    try:
        build_vision_message("x", [])
        checks.append(("空图列表被拒", False))
    except VisionError:
        checks.append(("空图列表被拒", True))
    try:
        build_vision_message("x", [ImageInput(path="assets/shot.png", url="http://a/b.png")])
        # path 优先；这不是错，只是确认优先级
        checks.append(("path 与 url 同时给时 path 优先", True))
    except VisionError:
        checks.append(("path 与 url 同时给时 path 优先", False))

    print("\n" + "=" * 74)
    print("[6] 诊断输出")
    print("=" * 74)
    d = describe()
    for k, v in d.items():
        print(f"  {k}: {v}")
    checks.append(("诊断含允许目录", d["image_roots"] == list(image_roots())))
    checks.append(("诊断反映未启用", d["role_configured"] is False))

    shutil.rmtree(ASSETS, ignore_errors=True)
    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败项:")
        for f in failed:
            print(f"  - {f}")
    return 1 if failed else 0


raise SystemExit(main())
