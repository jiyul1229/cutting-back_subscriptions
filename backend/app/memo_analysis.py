"""이용 기록 메모 분석: 메모가 '잘 안 쓴다 / 돈값을 못 한다'는 신호인지 판단합니다.

해지 추천 여부는 이용 횟수 규칙이 정하고, 메모 분석은 근거를 보태는 보조 역할입니다(문서 R3).
환경 변수 MEMO_ANALYSIS=ai 이면 Claude로 분석하고, 꺼져 있거나 호출에 실패하면 키워드로 판단합니다.
기본은 키워드라서 테스트·발표 중에 의도치 않은 API 호출이나 비용이 생기지 않습니다.
"""
import json
import logging
import os

from app.calculations import NEGATIVE_MEMO_KEYWORDS

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = (
    "너는 구독 관리 앱의 메모 분류기다. 사용자가 구독 서비스를 쓴 날 남긴 짧은 한국어 메모를 읽고, "
    "그 메모가 '이 구독을 잘 안 쓰게 됐거나, 재미나 필요가 없어졌거나, 해지를 고민한다'는 신호인지 판단한다.\n"
    "- 단순한 이용 기록이나 긍정적인 메모는 negative=false.\n"
    "- 애매하면 negative=false. 잘 쓰는 구독에 해지를 권하는 것이 더 큰 손해다.\n"
    "- reason에는 판단 근거를 한국어 한 문장으로 쓴다."
)

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "negative": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["negative", "reason"],
    "additionalProperties": False,
}


def keyword_negative(memo: str) -> bool:
    return any(keyword in memo for keyword in NEGATIVE_MEMO_KEYWORDS)


def ai_enabled() -> bool:
    return os.environ.get("MEMO_ANALYSIS", "keyword").strip().lower() == "ai"


def analyze_memo(memo: str | None) -> tuple[bool | None, str | None]:
    """(부정 신호 여부, 분석 방법). 메모가 없으면 (None, None)."""
    if memo is None or not memo.strip():
        return None, None
    if ai_enabled():
        negative = analyze_with_claude(memo)
        if negative is not None:
            return negative, "ai"
    return keyword_negative(memo), "keyword"


def analyze_with_claude(memo: str) -> bool | None:
    """Claude로 분류합니다. 실패하면 None을 돌려줘 키워드 판단으로 넘어갑니다."""
    try:
        import anthropic
    except ImportError:
        logger.warning("MEMO_ANALYSIS=ai but the anthropic package is not installed; using keywords")
        return None

    client = anthropic.Anthropic(timeout=20.0, max_retries=1)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            # 안전 분류기가 거절하면 서버가 권장 모델로 다시 실행합니다.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
            },
            messages=[{"role": "user", "content": memo}],
        )
    except anthropic.RateLimitError:
        logger.warning("Memo analysis rate limited; using keywords")
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Memo analysis failed (%s, request %s); using keywords",
                       exc.status_code, exc.request_id)
        return None
    except anthropic.APIConnectionError:
        logger.warning("Memo analysis could not reach the API; using keywords")
        return None
    except anthropic.AnthropicError as exc:
        logger.warning("Memo analysis unavailable (%s); using keywords", exc)
        return None
    except TypeError as exc:
        # SDK가 인증 정보(API 키, ant auth login 프로필 등)를 찾지 못하면 요청 전에 TypeError를 냅니다.
        logger.warning("Memo analysis has no Anthropic credentials (%s); using keywords", exc)
        return None

    if response.stop_reason != "end_turn":
        # refusal(대체 모델도 거절) 또는 max_tokens
        logger.warning("Memo analysis stopped with %s; using keywords", response.stop_reason)
        return None
    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        return bool(json.loads(text)["negative"])
    except (TypeError, ValueError, KeyError):
        logger.warning("Memo analysis returned unexpected output; using keywords")
        return None
