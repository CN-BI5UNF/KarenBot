"""Shared helpers for generated persona files."""

from __future__ import annotations

from typing import Any

from agents.persona_gen_agent import PersonaBrief


def admin_entries(admin_qq: str, admin_name: str) -> list[dict[str, object]]:
    if not admin_qq:
        return []
    entry: dict[str, object] = {"qq": int(admin_qq), "role": "owner"}
    if admin_name:
        entry["name"] = admin_name
    return [entry]


def admin_entries_from_brief(brief: PersonaBrief | None) -> list[dict[str, object]]:
    if brief is None:
        return []
    entries: list[dict[str, object]] = []
    for item in brief.admins:
        qq = str(item.get("qq", "")).strip()
        name = str(item.get("name", "")).strip()
        relation = str(item.get("relation", "")).strip()
        if not qq:
            continue
        entry: dict[str, object] = {"qq": int(qq), "role": "owner"}
        if name:
            entry["name"] = name
        if relation:
            entry["relation"] = relation
        entries.append(entry)
    if entries:
        return entries
    return admin_entries(brief.admin_qq, brief.admin_name)


def render_prompt_literal(text: str) -> str:
    """Render a readable Python string literal while preserving the exact text.

    Triple quotes keep real newlines in the saved persona file, so the WebUI
    preview no longer shows a wall of ``\\n`` escapes. Backslashes still need
    escaping; a delimiter that occurs in the prompt falls back to the other
    triple-quote style, and the pathological both-delimiter case escapes only
    the triple quotes instead of returning to ``repr``.
    """
    value = str(text or "")
    escaped = value.replace("\\", "\\\\")
    if '"""' not in value and not value.endswith('"'):
        return f'"""{escaped}"""'
    if "'''" not in value and not value.endswith("'"):
        return "'''" + escaped + "'''"
    escaped = escaped.replace('"""', '\\"\\"\\"')
    if value.endswith('"') and not escaped.endswith('\\"'):
        escaped = escaped[:-1] + '\\"'
    return f'"""{escaped}"""'


def render_persona_file(
    name: str,
    xml: str,
    *,
    display_name: str = "",
    admins: list[dict[str, object]] | None = None,
    gender: str = "",
    age: int | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> str:
    """Render a persona file with readable, lossless prompt serialization.

    Triple-quoted literals keep the saved prompt readable in the WebUI source
    preview while newlines, backslashes and quotes still round-trip through the
    loader. ``PERSONA_VARS`` stays a normal Python dict.
    """
    persona_vars: dict[str, Any] = dict(extra_vars or {})
    persona_vars["name"] = (display_name or "").strip() or name
    persona_vars["admins"] = list(admins or [])
    if gender.strip():
        persona_vars["gender"] = gender.strip()
    if age is not None:
        persona_vars["age"] = int(age)
    return (
        '"""人格档案（支持直接编写的长提示词）。"""\n\n'
        f"PERSONA_PROMPT = {render_prompt_literal(xml)}\n\n"
        f"PERSONA_VARS = {format_python_literal(persona_vars)}\n"
    )


def render_minimal_persona(
    name: str,
    xml: str,
    admins: list[dict[str, object]] | None = None,
    gender: str = "",
    *,
    display_name: str = "",
    age: int | None = None,
) -> str:
    """Backward-compatible wrapper used by the AI-draft save path."""
    return render_persona_file(
        name,
        xml,
        display_name=display_name,
        admins=admins,
        gender=gender,
        age=age,
    )


def format_python_literal(value: Any) -> str:
    import pprint

    return pprint.pformat(value, width=96, sort_dicts=False)


__all__ = [
    "admin_entries",
    "admin_entries_from_brief",
    "format_python_literal",
    "render_minimal_persona",
    "render_persona_file",
    "render_prompt_literal",
]
