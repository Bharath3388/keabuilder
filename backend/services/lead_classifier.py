"""Q1: AI-Powered Lead Classification Service.

Uses Groq (free tier, Llama 3.3) for LLM classification.
Falls back to rule-based scoring when LLM is unavailable.
"""

import json
import re
import structlog
from config import get_settings
from utils.monitoring import AI_CALL_COUNT, Timer
from utils.sanitize import sanitize_for_json_prompt

logger = structlog.get_logger()
settings = get_settings()

# =============================================================================
# Rule-Based Scorer (Fallback — no LLM dependency)
# =============================================================================

BUDGET_SCORES = {
    "high": 30,    # > $5K/mo
    "medium": 18,  # $1K-$5K
    "low": 5,      # < $1K
    "none": 0,
}

TIMELINE_SCORES = {
    "urgent": 20,    # < 1 month
    "medium": 12,    # 1-3 months
    "long": 4,       # > 3 months
    "none": 0,
}

COMPANY_SIZE_SCORES = {
    "enterprise": 15,  # 50+
    "mid": 10,         # 10-49
    "small": 4,        # < 10
    "none": 0,
}


def _parse_budget(budget_str: str | None) -> str:
    if not budget_str:
        return "none"
    budget_str = budget_str.lower().replace(",", "").replace("$", "")
    # Extract numbers
    numbers = re.findall(r"[\d]+", budget_str)
    if numbers:
        max_val = max(int(n) for n in numbers)
        if max_val >= 5000:
            return "high"
        elif max_val >= 1000:
            return "medium"
        return "low"
    return "none"


def _parse_timeline(timeline_str: str | None) -> str:
    if not timeline_str:
        return "none"
    timeline_str = timeline_str.lower()
    if any(w in timeline_str for w in ["asap", "immediately", "urgent", "within 30", "this week", "this month"]):
        return "urgent"
    if any(w in timeline_str for w in ["1-3 month", "1 to 3", "next quarter", "few months"]):
        return "medium"
    if any(w in timeline_str for w in ["6 month", "next year", "no rush", "exploring"]):
        return "long"
    # Try to parse numbers
    numbers = re.findall(r"(\d+)", timeline_str)
    if numbers:
        val = int(numbers[0])
        if "day" in timeline_str and val <= 30:
            return "urgent"
        if "month" in timeline_str:
            if val <= 1:
                return "urgent"
            elif val <= 3:
                return "medium"
            return "long"
    return "none"


def _parse_company_size(size_str: str | None) -> str:
    if not size_str:
        return "none"
    numbers = re.findall(r"(\d+)", str(size_str))
    if numbers:
        val = int(numbers[0])
        if val >= 50:
            return "enterprise"
        elif val >= 10:
            return "mid"
        return "small"
    size_str = size_str.lower()
    if any(w in size_str for w in ["enterprise", "large", "big"]):
        return "enterprise"
    if any(w in size_str for w in ["freelanc", "solo", "individual", "startup"]):
        return "small"
    return "none"


def _score_specificity(use_case: str | None) -> int:
    if not use_case:
        return 0
    word_count = len(use_case.split())
    if word_count >= 20:
        return 20  # Detailed ask
    elif word_count >= 8:
        return 12  # Vague interest
    return 4  # Generic enquiry


def _score_contact_quality(email: str | None, phone: str | None) -> int:
    score = 0
    if email:
        free_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"]
        domain = email.split("@")[-1].lower() if "@" in email else ""
        if domain and domain not in free_domains:
            score += 10  # Work email
        else:
            score += 3   # Personal email
    if phone:
        score += 5  # Has phone number
    return score


def classify_lead_rule_based(lead_data: dict) -> dict:
    """Rule-based lead classification (no LLM needed)."""
    budget_score = BUDGET_SCORES[_parse_budget(lead_data.get("budget_range"))]
    timeline_score = TIMELINE_SCORES[_parse_timeline(lead_data.get("timeline"))]
    company_score = COMPANY_SIZE_SCORES[_parse_company_size(lead_data.get("company_size"))]
    specificity_score = _score_specificity(lead_data.get("use_case"))
    contact_score = _score_contact_quality(lead_data.get("email"), lead_data.get("phone"))

    total_score = budget_score + timeline_score + company_score + specificity_score + contact_score

    if total_score >= 70:
        classification = "HOT"
    elif total_score >= 40:
        classification = "WARM"
    else:
        classification = "COLD"

    # Identify missing signals
    missing = []
    if not lead_data.get("budget_range"):
        missing.append("budget_range")
    if not lead_data.get("timeline"):
        missing.append("timeline")
    if not lead_data.get("company_size"):
        missing.append("company_size")
    if not lead_data.get("use_case"):
        missing.append("use_case")

    confidence = min(total_score / 100.0, 1.0)

    return {
        "classification": classification,
        "confidence": round(confidence, 2),
        "reasoning": f"Score: {total_score}/100 (budget={budget_score}, timeline={timeline_score}, company={company_score}, specificity={specificity_score}, contact={contact_score})",
        "missing_signals": missing,
        "score_breakdown": {
            "budget": budget_score,
            "timeline": timeline_score,
            "company_size": company_score,
            "specificity": specificity_score,
            "contact_quality": contact_score,
            "total": total_score,
        },
    }


# =============================================================================
# LLM-Based Classification (Groq — free tier)
# =============================================================================

CLASSIFICATION_PROMPT = """You are a B2B lead scoring engine for a SaaS platform called KeaBuilder.
Analyze the following form submission JSON and classify the lead as HOT, WARM, or COLD.

Scoring rules:
- HOT: High intent, real budget, short timeline, detailed requirements
- WARM: Some intent, possible budget, medium timeline
- COLD: Vague, no budget signals, long timeline or unclear need

Respond ONLY with valid JSON in this exact shape:
{
  "classification": "HOT or WARM or COLD",
  "confidence": 0.0 to 1.0,
  "reasoning": "One sentence explaining the decision",
  "missing_signals": ["field1", "field2"],
  "follow_up_questions": ["Q1", "Q2"]
}

Lead data:
"""


async def classify_lead_llm(lead_data: dict) -> dict | None:
    """Classify a lead using Groq's free LLM API."""
    if not settings.groq_api_key:
        logger.warning("No Groq API key configured, skipping LLM classification")
        return None

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)

        with Timer("llm_classification", {"provider": "groq"}):
            response = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {
                        "role": "system",
                        "content": CLASSIFICATION_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(sanitize_for_json_prompt(lead_data), indent=2),
                    },
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

        raw = response.choices[0].message.content
        result = json.loads(raw)

        AI_CALL_COUNT.labels(provider="groq", type="classification", status="success").inc()

        # Validate required fields
        required = ["classification", "confidence", "reasoning"]
        if all(k in result for k in required):
            result["classification"] = result["classification"].upper()
            if result["classification"] not in ("HOT", "WARM", "COLD"):
                result["classification"] = "WARM"
            return result

        logger.warning("LLM returned incomplete response", raw=raw)
        return None

    except Exception as e:
        AI_CALL_COUNT.labels(provider="groq", type="classification", status="error").inc()
        logger.error("LLM classification failed", error=str(e))
        return None


async def classify_lead(lead_data: dict) -> dict:
    """Classify lead: try LLM first, fall back to rule-based."""
    # Try LLM classification
    llm_result = await classify_lead_llm(lead_data)
    if llm_result:
        return llm_result

    # Fallback to rule-based
    logger.info("Using rule-based classification fallback")
    return classify_lead_rule_based(lead_data)
