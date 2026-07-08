"""
Real LLM integration for the AI features, powered by the Anthropic Claude API.

The dashboard's "AI Assistant" surfaces (audience insight, content ideas, smart
hashtags) previously returned hardcoded text. This module calls Claude
(`claude-opus-4-8` by default) to generate genuinely tailored output from each
account's real metrics.

Design goals:
  * **Optional** — if `anthropic` isn't installed or `ANTHROPIC_API_KEY` isn't
    set, `is_enabled()` returns False and every helper returns ``None`` so the
    caller cleanly falls back to the existing heuristic logic. The app never
    breaks just because no key is configured.
  * **Robust** — any API error (network, rate limit, refusal, bad JSON) is
    swallowed and surfaces as ``None``; callers treat that as "use the
    fallback".
  * **Structured** — content ideas and hashtags use structured outputs
    (`output_config.format`) so the JSON is guaranteed parseable.
"""

import json
import os

try:
    import anthropic
except ImportError:  # SDK not installed — feature simply stays off.
    anthropic = None

_DEFAULT_MODEL = "claude-opus-4-8"
_client = None


def _model():
    return os.environ.get("ANTHROPIC_MODEL") or _DEFAULT_MODEL


def is_enabled():
    """True only when the SDK is importable and an API key is configured."""
    return anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if not is_enabled():
        return None
    if _client is None:
        # The SDK reads ANTHROPIC_API_KEY from the environment automatically.
        _client = anthropic.Anthropic()
    return _client


def _create(messages, system=None, max_tokens=1500, output_schema=None):
    """Thin wrapper around messages.create with shared error handling."""
    client = _get_client()
    if client is None:
        return None
    try:
        kwargs = {
            "model": _model(),
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if output_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": output_schema}
            }
        resp = client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            return None
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as exc:  # noqa: BLE001 — any failure → graceful fallback
        print(f"[LLMService] Claude request failed: {exc}")
        return None


# ── Audience insight (free-text) ────────────────────────────────────────────

def generate_audience_insight(context):
    """
    Produce a short, data-grounded audience analysis paragraph.
    `context` is a dict of demographic / engagement stats. Returns text or None.
    """
    system = (
        "You are an expert Instagram growth strategist. Given an account's "
        "analytics, write a concise (2-4 sentence) audience insight that is "
        "specific to the numbers provided and gives one concrete, actionable "
        "recommendation. No preamble, no markdown, plain text only."
    )
    user = "Account analytics:\n" + json.dumps(context, ensure_ascii=False, indent=2)
    return _create([{"role": "user", "content": user}], system=system, max_tokens=400)


# ── Content ideas (structured) ──────────────────────────────────────────────

_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "caption": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["type", "caption", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


def generate_content_ideas(context):
    """
    Return a list of {type, caption, reason} content ideas tailored to the
    account, or None on failure. `context` carries niche + top-performer stats.
    """
    system = (
        "You are an Instagram content strategist. Propose exactly 3 post ideas "
        "tailored to the account described. Each idea needs a short `type` "
        "label, a ready-to-post `caption` (include 3-5 relevant hashtags and an "
        "emoji or two), and a one-line `reason` grounded in the account's data. "
        "Match the language of the account's existing captions."
    )
    user = "Account context:\n" + json.dumps(context, ensure_ascii=False, indent=2)
    raw = _create(
        [{"role": "user", "content": user}],
        system=system,
        max_tokens=1500,
        output_schema=_CONTENT_SCHEMA,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        suggestions = data.get("suggestions", [])
        return suggestions if suggestions else None
    except (json.JSONDecodeError, AttributeError):
        return None


# ── Hashtags (structured) ───────────────────────────────────────────────────

_HASHTAG_SCHEMA = {
    "type": "object",
    "properties": {
        "hashtags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hashtag": {"type": "string"},
                    "relevance": {"type": "integer"},
                    "reach_volume": {"type": "string"},
                    "engagement_potential": {"type": "integer"},
                },
                "required": [
                    "hashtag",
                    "relevance",
                    "reach_volume",
                    "engagement_potential",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hashtags"],
    "additionalProperties": False,
}


def generate_hashtags(keyword, niche=None):
    """
    Return a list of hashtag dicts (hashtag, relevance, reach_volume,
    engagement_potential) for `keyword`, or None on failure.
    """
    system = (
        "You are an Instagram SEO expert. Generate exactly 10 relevant, "
        "currently-effective hashtags for the given topic. For each: `hashtag` "
        "(with leading #), `relevance` (0-100), `reach_volume` (one of "
        "'High Volume', 'Medium Volume', 'Niche Peak'), and "
        "`engagement_potential` (0-100). Mix broad and niche tags."
    )
    payload = {"topic": keyword}
    if niche:
        payload["account_niche"] = niche
    user = json.dumps(payload, ensure_ascii=False)
    raw = _create(
        [{"role": "user", "content": user}],
        system=system,
        max_tokens=1000,
        output_schema=_HASHTAG_SCHEMA,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        tags = data.get("hashtags", [])
        return tags if tags else None
    except (json.JSONDecodeError, AttributeError):
        return None
