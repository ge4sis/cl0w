"""
Web search tool — DuckDuckGo Instant Answer API (API 키 불필요)
tools/ 디렉터리에 넣으면 cl0w 에 자동 등록됩니다.
"""
import httpx

TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Search the web for current information using DuckDuckGo",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색어"
            }
        },
        "required": ["query"],
    },
}

def run(query: str) -> str:
    r = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
        timeout=10,
        follow_redirects=True,
    )
    d = r.json()

    # AbstractText (Wikipedia 요약) 또는 직접 답변 우선
    result = d.get("AbstractText") or d.get("Answer") or ""

    # 없으면 RelatedTopics 상위 3개
    if not result:
        topics = [
            t.get("Text", "")
            for t in d.get("RelatedTopics", [])[:5]
            if isinstance(t, dict) and t.get("Text")
        ]
        result = "\n".join(topics)

    return result or f"검색 결과를 찾을 수 없습니다: '{query}'"
