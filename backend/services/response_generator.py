"""Q1: AI-Powered Personalized Response Generation.

Uses Groq (free tier) for natural language generation.
Falls back to template-based responses when LLM is unavailable.
"""

import json
import random
import structlog
from config import get_settings
from utils.monitoring import AI_CALL_COUNT, Timer
from utils.sanitize import sanitize_for_json_prompt

logger = structlog.get_logger()
settings = get_settings()

# =============================================================================
# Template-Based Response Generator (Fallback)
# =============================================================================

HOT_OPENERS = [
    "Hi {name}, great to hear from you!",
    "Hey {name}, thanks for reaching out!",
    "Hi {name}, I love what you're building at {company}!",
]

WARM_OPENERS = [
    "Hi {name}, thanks for your interest in KeaBuilder!",
    "Hey {name}, great to connect with you!",
    "Hi {name}, welcome! I'd love to help you explore what's possible.",
]

COLD_OPENERS = [
    "Hi {name}, thanks for stopping by!",
    "Hey {name}, welcome to KeaBuilder!",
    "Hi {name}, great to have you here!",
]

FEATURE_MAP = {
    "lead nurturing": "automated nurture sequences that trigger personalised email + SMS flows",
    "funnel": "drag-and-drop funnel builder with built-in A/B testing",
    "landing page": "high-converting landing page templates with AI-powered copy suggestions",
    "email": "smart email automation that personalises content based on user behaviour",
    "sms": "SMS marketing automation with intelligent send-time optimisation",
    "trial": "trial-to-paid conversion flows with automated follow-up sequences",
    "conversion": "conversion optimisation tools with real-time analytics",
    "automation": "no-code automation workflows that connect all your marketing tools",
    "default": "all-in-one marketing automation platform",
}

CTA_MAP = {
    "HOT": "I'd love to show you a live demo. Does this week work for a 30-minute call?",
    "WARM": "I've put together a case study from a similar company — would you like me to send it over?",
    "COLD": "We've got a free marketing audit checklist that might be helpful — want me to send it your way?",
}

ACTION_MAP = {
    "HOT": "SCHEDULE_DEMO",
    "WARM": "SEND_CASE_STUDY",
    "COLD": "SEND_CHECKLIST",
}


def _match_feature(use_case: str | None) -> str:
    if not use_case:
        return FEATURE_MAP["default"]
    use_case_lower = use_case.lower()
    for keyword, feature in FEATURE_MAP.items():
        if keyword in use_case_lower:
            return feature
    return FEATURE_MAP["default"]


def generate_response_template(lead_data: dict, classification: str) -> str:
    """Generate a template-based response (no LLM needed)."""
    name = lead_data.get("name", "there").split()[0]
    company = lead_data.get("company", "your company")
    use_case = lead_data.get("use_case", "")
    feature = _match_feature(use_case)

    openers = {"HOT": HOT_OPENERS, "WARM": WARM_OPENERS, "COLD": COLD_OPENERS}
    opener = random.choice(openers.get(classification, WARM_OPENERS))
    opener = opener.format(name=name, company=company)

    cta = CTA_MAP.get(classification, CTA_MAP["WARM"])

    if use_case:
        middle = f"KeaBuilder's {feature} can help with exactly what you're describing."
    else:
        middle = f"KeaBuilder is an {feature} that helps businesses like {company} grow faster."

    return f"{opener} {middle} {cta}"


# =============================================================================
# LLM-Based Response Generator (Groq — free tier)
# =============================================================================

RESPONSE_PROMPT = """You are a friendly, knowledgeable sales assistant for KeaBuilder, a funnel and
automation platform. Your tone is warm, professional, and helpful — never robotic.

Write a personalised first-touch response to the lead below.
- Address them by first name
- Reference their specific use case if provided
- Include exactly one relevant KeaBuilder feature that solves their problem
- End with a soft CTA appropriate for their lead temperature: {classification}
  - HOT: Offer a 30-minute demo slot
  - WARM: Share a relevant case study or resource
  - COLD: Offer a free audit or checklist
- Keep it under 120 words
- Output ONLY the response text, no JSON or markdown

Lead: {lead_json}
Classification: {classification}"""


CLARIFICATION_PROMPT = """You are a friendly sales assistant for KeaBuilder.
The following lead submission is missing important information: {missing_fields}.
Write a short, warm message asking them to provide more details.
Address them by first name. Keep it under 80 words. Output ONLY the message text.

Lead: {lead_json}"""


async def generate_response_llm(
    lead_data: dict,
    classification: str,
    missing_signals: list[str],
) -> str | None:
    """Generate a personalised response using Groq's free LLM API."""
    if not settings.groq_api_key:
        return None

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)

        # Choose prompt based on whether critical info is missing
        critical_missing = {"name", "email"} & set(missing_signals)
        if critical_missing or len(missing_signals) >= 3:
            prompt = CLARIFICATION_PROMPT.format(
                missing_fields=", ".join(missing_signals),
                lead_json=json.dumps(sanitize_for_json_prompt(lead_data), indent=2),
            )
        else:
            prompt = RESPONSE_PROMPT.format(
                classification=classification,
                lead_json=json.dumps(sanitize_for_json_prompt(lead_data), indent=2),
            )

        with Timer("llm_response_generation", {"provider": "groq"}):
            response = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.75,
                max_tokens=300,
            )

        text = response.choices[0].message.content.strip()
        AI_CALL_COUNT.labels(provider="groq", type="response_gen", status="success").inc()
        return text

    except Exception as e:
        AI_CALL_COUNT.labels(provider="groq", type="response_gen", status="error").inc()
        logger.error("LLM response generation failed", error=str(e))
        return None


async def generate_response(
    lead_data: dict,
    classification: str,
    missing_signals: list[str],
) -> str:
    """Generate response: try LLM first, fall back to template."""
    llm_response = await generate_response_llm(lead_data, classification, missing_signals)
    if llm_response:
        return llm_response

    logger.info("Using template-based response fallback")
    return generate_response_template(lead_data, classification)


def determine_crm_tags(lead_data: dict, classification: str) -> list[str]:
    """Generate CRM tags from lead data."""
    tags = [f"{classification.lower()}_lead"]

    if lead_data.get("industry"):
        tags.append(f"{lead_data['industry'].lower().replace(' ', '_')}_vertical")

    use_case = (lead_data.get("use_case") or "").lower()
    for keyword in ["trial", "funnel", "email", "sms", "conversion", "automation"]:
        if keyword in use_case:
            tags.append(keyword)

    return tags


def determine_next_action(classification: str, missing_signals: list[str]) -> str:
    """Determine the next action based on classification."""
    if len(missing_signals) >= 3:
        return "REQUEST_INFORMATION"
    return ACTION_MAP.get(classification, "SEND_CHECKLIST")
