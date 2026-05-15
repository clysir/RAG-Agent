"""状态机路由函数单测 —— 纯函数,无外部依赖,跑得飞快。"""

from agent.context import AgentContext, IntentType
from agent.state_machine import _route_after_intent, _route_after_retrieve


def _make_ctx(**kw) -> AgentContext:
    base = {"trace_id": "t", "session_id": "s", "user_query": "q"}
    base.update(kw)
    return AgentContext(**base)


def test_route_after_intent_chitchat_goes_to_respond():
    ctx = _make_ctx()
    ctx.intent = IntentType.CHITCHAT
    assert _route_after_intent(ctx).value == "respond"


def test_route_after_intent_with_image_goes_to_image_understand():
    ctx = _make_ctx(image_bytes=b"fake")
    ctx.intent = IntentType.SEARCH
    assert _route_after_intent(ctx).value == "image_understand"


def test_route_after_intent_no_image_goes_to_query_rewrite():
    ctx = _make_ctx()
    ctx.intent = IntentType.SEARCH
    assert _route_after_intent(ctx).value == "query_rewrite"


def test_route_after_retrieve_empty_goes_to_clarify():
    ctx = _make_ctx()
    assert _route_after_retrieve(ctx).value == "need_clarify"
