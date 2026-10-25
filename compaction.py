import re
import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def normalize_message(msg: Any) -> dict:
    """Ensure message is a standard dictionary (e.g. converting Pydantic ChatCompletionMessage)."""
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "model_dump"):
        return msg.model_dump(exclude_none=True)
    if hasattr(msg, "dict"):
        return msg.dict(exclude_none=True)
    if hasattr(msg, "__dict__"):
        return vars(msg)
    return dict(msg)


def _get_role(msg: Any) -> Optional[str]:
    if isinstance(msg, dict):
        return msg.get("role")
    return getattr(msg, "role", None)


def _get_content(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("content")
    return getattr(msg, "content", None)


def estimate_tokens(messages: List[Any], tools: Optional[List[dict]] = None) -> int:
    """
    Fast and accurate heuristic token estimator for multilingual (Korean + English) messages and tools.
    Byte-Pair Encoding (BPE) uses ~1.8 tokens per Korean syllable and ~0.28 tokens per ASCII character.
    """
    total_tokens = 0

    for msg in messages:
        total_tokens += 4  # Per-message overhead (role, framing)
        content = _get_content(msg) or ""
        if isinstance(content, str):
            korean_chars = len(re.findall(r"[\uac00-\ud7a3]", content))
            other_chars = len(content) - korean_chars
            total_tokens += int(korean_chars * 1.8 + other_chars * 0.28)

        # Handle tool calls in assistant messages
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
        else:
            tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                func = getattr(tc, "function", None)
                if func:
                    fn_name = getattr(func, "name", "")
                    fn_args = getattr(func, "arguments", "")
                elif isinstance(tc, dict):
                    fn_dict = tc.get("function", {})
                    fn_name = fn_dict.get("name", "")
                    fn_args = fn_dict.get("arguments", "")
                else:
                    fn_name, fn_args = "", ""

                total_tokens += int(len(fn_name) * 0.3 + len(str(fn_args)) * 0.3) + 6

    # Estimate tool definitions schema
    if tools:
        try:
            tools_json = json.dumps(tools)
            total_tokens += int(len(tools_json) * 0.28)
        except Exception:
            total_tokens += len(tools) * 150  # rough fallback

    return max(1, total_tokens)


def _slim_search_json(raw_text: str) -> Optional[str]:
    """
    Attempts to parse JSON tool outputs from search tools (like Exa)
    and produce a compact lightweight index retaining titles, URLs, and concise snippets.
    """
    try:
        data = json.loads(raw_text)
    except Exception:
        return None

    results = None
    if isinstance(data, dict):
        results = data.get("results") or data.get("items") or data.get("data")
    elif isinstance(data, list):
        results = data

    if not results or not isinstance(results, list):
        return None

    lines = [f"[검색 결과 요약 인덱스 (총 {len(results)}건 기사 분석 완료)]"]
    for i, item in enumerate(results[:20], start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or "제목 없음"
        url = item.get("url") or item.get("link") or ""
        snippet = item.get("text") or item.get("snippet") or item.get("summary") or ""
        snippet_clean = snippet.strip().replace("\n", " ")[:150]
        line = f"{i}. 제목: {title}"
        if url:
            line += f" | URL: {url}"
        if snippet_clean:
            line += f" | 요약: {snippet_clean}..."
        lines.append(line)

    if len(results) > 20:
        lines.append(f"... (추가 {len(results) - 20}건 기사 원문 생략)")

    return "\n".join(lines)


def prune_past_tool_outputs(messages: List[Any], max_content_chars: int = 1000) -> bool:
    """
    Level 1 Auto-Compaction:
    Finds large 'role: tool' results from PRIOR turns (before the last user message)
    and replaces them with compact summaries/indexes.
    Current turn tool outputs are kept 100% intact so the LLM can synthesize them.
    """
    # Normalize messages in-place so all items become standard mutable dicts
    for idx in range(len(messages)):
        if not isinstance(messages[idx], dict):
            messages[idx] = normalize_message(messages[idx])

    # Locate the index of the latest user message
    last_user_idx = -1
    for idx, msg in enumerate(messages):
        if _get_role(msg) == "user":
            last_user_idx = idx

    if last_user_idx <= 0:
        return False

    pruned_any = False
    for idx in range(last_user_idx):
        msg = messages[idx]
        if _get_role(msg) == "tool":
            content = _get_content(msg)
            if isinstance(content, str) and len(content) > max_content_chars:
                slimmed = _slim_search_json(content)
                if not slimmed:
                    # General text/shell output trimming
                    head = content[:350].strip()
                    tail = content[-250:].strip()
                    slimmed = (
                        f"{head}\n\n"
                        f"... [중략: 총 {len(content):,}자 중 핵심 메타데이터만 보존] ...\n\n"
                        f"{tail}"
                    )
                if isinstance(msg, dict):
                    msg["content"] = slimmed
                else:
                    setattr(msg, "content", slimmed)
                pruned_any = True
                logger.info(f"[Compaction] Pruned past tool message at index {idx} ({len(content)} -> {len(slimmed)} chars)")

    return pruned_any


async def compact_session_history(
    messages: List[Any],
    context_limit: int,
    target_ratio: float = 0.35,
    client: Any = None,
    model: str = "local-model",
) -> bool:
    """
    Level 2 Auto-Compaction:
    Triggered when total token count exceeds compaction threshold ratio.
    Preserves:
      - System prompt (index 0)
      - Recent turns (the latest user message and all subsequent messages)
    Compacts:
      - All intermediate turns into a concise structured summary.
    """
    # Normalize in-place
    for idx in range(len(messages)):
        if not isinstance(messages[idx], dict):
            messages[idx] = normalize_message(messages[idx])

    if len(messages) <= 4:
        return False

    # Find the boundary for recent turns: keep the last 2 user messages and their follow-ups
    user_indices = [i for i, m in enumerate(messages) if _get_role(m) == "user"]
    if len(user_indices) < 2:
        return False

    # Keep from the second-to-last user message onwards
    cutoff_idx = user_indices[-2]
    if cutoff_idx <= 1:
        return False

    system_msg = messages[0]
    older_messages = messages[1:cutoff_idx]
    recent_messages = messages[cutoff_idx:]

    # Build conversation digest for older messages
    text_chunks = []
    for m in older_messages:
        role = _get_role(m)
        content = _get_content(m)
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            text_chunks.append(f"{role.upper()}: {content.strip()[:600]}")

    if not text_chunks:
        return False

    conversation_text = "\n\n".join(text_chunks)
    summary_text = None

    # Try fast LLM summarization
    if client and model:
        try:
            prompt = (
                "아래는 이전 대화 내역입니다. "
                "사용자가 요청한 핵심 요구사항, 주요 결정 사항, 진행된 작업 결과를 3~5문장으로 요약하세요. "
                "반드시 한글로 작성하세요.\n\n"
                f"{conversation_text}"
            )
            import asyncio
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "너는 대화 맥락 요약 전문가이다."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                ),
                timeout=12.0,
            )
            raw_summary = resp.choices[0].message.content or ""
            if raw_summary.strip():
                summary_text = raw_summary.strip()
        except Exception as e:
            logger.warning(f"[Compaction] LLM summarization failed or timed out: {e}")

    # Fallback to structured extractive summary
    if not summary_text:
        summary_lines = []
        for line in text_chunks:
            if line.startswith("USER:"):
                summary_lines.append(f"- 요청: {line[6:150]}")
            elif line.startswith("ASSISTANT:"):
                summary_lines.append(f"- 진행/결과: {line[11:150]}")
        summary_text = "\n".join(summary_lines[:8])

    compacted_user = {
        "role": "user",
        "content": f"[이전 대화 핵심 요약]\n{summary_text}",
    }
    compacted_assistant = {
        "role": "assistant",
        "content": "이전 대화 맥락과 주요 결정 사항을 모두 숙지했습니다. 계속해서 요청하신 작업을 진행합니다.",
    }

    # Reconstruct messages list in-place
    messages.clear()
    messages.append(system_msg)
    messages.append(compacted_user)
    messages.append(compacted_assistant)
    messages.extend(recent_messages)

    logger.info(f"[Compaction] Session history compacted: {len(older_messages)} older messages compressed into summary.")
    return True
