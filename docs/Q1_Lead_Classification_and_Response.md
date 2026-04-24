# Q1: AI Lead Classification & Intelligent Response

## Design Overview

KeaBuilder processes incoming form submissions through a two-stage AI pipeline:

1. **Classification** — Score and categorize the lead as HOT, WARM, or COLD
2. **Response Generation** — Produce a personalized, human-sounding reply

Both stages use a **dual-engine architecture**: an LLM-powered primary path (Groq / Llama 3.3, free tier) with a deterministic rule-based fallback that requires zero external dependencies.

```
Form Submission
      │
      ▼
┌─────────────┐     ┌──────────────────┐
│  LLM Engine │────▶│  Rule-Based      │  (fallback if LLM unavailable)
│  (Groq)     │     │  Scorer          │
└──────┬──────┘     └────────┬─────────┘
       │                     │
       ▼                     ▼
   Classification (HOT / WARM / COLD)
       │
       ▼
┌─────────────┐     ┌──────────────────┐
│  LLM Writer │────▶│  Template Engine  │  (fallback)
│  (Groq)     │     │                  │
└──────┬──────┘     └────────┬─────────┘
       │                     │
       ▼                     ▼
   Personalized Response + CRM Tags + Next Action
       │
       ▼
   Persist to DB → Return to caller
```

**Implementation:** `backend/services/lead_classifier.py`, `backend/services/response_generator.py`

---

## a) How We Classify Leads into HOT / WARM / COLD

### LLM-Based Classification (Primary)

When a Groq API key is configured, lead data is sent to Llama 3.3 70B with a structured system prompt. The LLM returns a JSON object with classification, confidence score, reasoning, missing signals, and follow-up questions.

- **Temperature**: 0.3 (low creativity for consistent scoring)
- **Response format**: Forced JSON output (`response_format={"type": "json_object"}`)
- **Prompt injection protection**: All lead data is sanitized through `sanitize_for_json_prompt()` before being embedded in the prompt

### Rule-Based Classification (Fallback)

When the LLM is unavailable, a deterministic weighted-score system evaluates five signals:

| Signal | Weight | HOT Trigger | COLD Trigger |
|--------|--------|-------------|--------------|
| **Budget** | 0-30 pts | > $5K/mo (30) | No budget info (0) |
| **Timeline** | 0-20 pts | < 1 month / "ASAP" (20) | > 6 months / "exploring" (4) |
| **Company Size** | 0-15 pts | 50+ employees (15) | Solo/freelancer (4) |
| **Use Case Specificity** | 0-20 pts | 20+ words, detailed ask (20) | Generic / empty (0-4) |
| **Contact Quality** | 0-15 pts | Work email + phone (15) | Free email only (3) |

**Thresholds:**
- **HOT**: score ≥ 70 / 100
- **WARM**: score ≥ 40 / 100
- **COLD**: score < 40 / 100

The rule-based scorer also parses natural language budget ("$5,000-$10,000/month"), timeline ("ASAP", "within 30 days", "3 months"), and company size ("enterprise", "50+", "startup") into normalized categories.

**Implementation:** `classify_lead_rule_based()` in `backend/services/lead_classifier.py`

---

## b) Prompts

### Classification Prompt

```
You are a B2B lead scoring engine for a SaaS platform called KeaBuilder.
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
<sanitized lead JSON>
```

### Response Generation Prompt

```
You are a friendly, knowledgeable sales assistant for KeaBuilder, a funnel and
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
Classification: {classification}
```

### Clarification Prompt (for incomplete submissions)

```
You are a friendly sales assistant for KeaBuilder.
The following lead submission is missing important information: {missing_fields}.
Write a short, warm message asking them to provide more details.
Address them by first name. Keep it under 80 words. Output ONLY the message text.

Lead: {lead_json}
```

---

## c) How Responses Feel Human and Personalized

1. **First-name addressing** — Both LLM and template paths extract and use the lead's first name
2. **Use-case-specific feature matching** — A keyword→feature map links what the lead mentioned to the most relevant KeaBuilder capability (e.g., "funnel" → "drag-and-drop funnel builder with built-in A/B testing")
3. **Temperature-appropriate CTAs** — HOT leads get a demo offer, WARM get a case study, COLD get a free checklist — never an aggressive push
4. **Randomized opener templates** — The fallback engine cycles through multiple opener styles per classification tier so repeated leads don't get identical responses
5. **LLM temperature at 0.75** — High enough for natural variation, low enough for professionalism
6. **120-word cap** — Forces concise, scannable responses that feel like a real person wrote them quickly

---

## d) Handling Incomplete or Unclear Inputs

The system handles missing data at multiple levels:

1. **Missing signal detection** — Both LLM and rule-based classifiers identify which fields are empty (`budget_range`, `timeline`, `company_size`, `use_case`) and return them as `missing_signals`
2. **Confidence reduction** — Missing fields reduce the total score, naturally pulling classifications toward COLD/WARM
3. **Clarification response** — If 3+ fields are missing OR critical fields (name, email) are absent, the response generator switches to a **clarification prompt** that warmly asks the lead to provide more details
4. **Graceful defaults** — The rule-based scorer treats missing values as `"none"` (0 points) rather than erroring
5. **Email validation** — Pydantic's `EmailStr` rejects malformed emails at the API boundary before they reach the classifier

---

## Sample Input → Output

### Input (Form Submission)

```json
{
  "name": "Sarah Chen",
  "email": "sarah@acmecorp.com",
  "company": "Acme Corp",
  "company_size": "85 employees",
  "budget_range": "$5,000-$10,000/month",
  "timeline": "Need this within 2 weeks",
  "use_case": "We need to build automated lead nurturing funnels that send personalized email sequences based on user behavior. Currently losing 40% of trial signups.",
  "phone": "+1-555-0142",
  "industry": "SaaS",
  "source": "Google Ads"
}
```

### Output (API Response)

```json
{
  "lead_id": "lead_20260424_a3f1",
  "classification": "HOT",
  "confidence": 0.95,
  "reasoning": "Enterprise company (85 employees) with high budget ($5K-$10K/mo), urgent 2-week timeline, detailed use case describing specific pain point (40% trial churn), and work email with phone — strong buying signals across all dimensions.",
  "missing_signals": [],
  "follow_up_questions": [
    "What email platform are you currently using?",
    "How many trial signups do you get per month?"
  ],
  "suggested_response": "Hi Sarah, great to hear from you! KeaBuilder's automated nurture sequences that trigger personalised email + SMS flows can help with exactly what you're describing. I'd love to show you a live demo. Does this week work for a 30-minute call?",
  "crm_tags": ["hot_lead", "saas_vertical", "funnel", "email", "automation"],
  "next_action": "SCHEDULE_DEMO",
  "created_at": "2026-04-24T10:30:00Z"
}
```

### Input (Incomplete Submission)

```json
{
  "name": "Alex",
  "email": "alex123@gmail.com"
}
```

### Output (Incomplete)

```json
{
  "lead_id": "lead_20260424_b7c2",
  "classification": "COLD",
  "confidence": 0.03,
  "reasoning": "Score: 3/100 (budget=0, timeline=0, company=0, specificity=0, contact=3)",
  "missing_signals": ["budget_range", "timeline", "company_size", "use_case"],
  "follow_up_questions": [
    "What brings you to KeaBuilder today?",
    "What's the biggest marketing challenge you're facing right now?"
  ],
  "suggested_response": "Hi Alex, thanks for stopping by! I'd love to learn more about what you're looking for so I can point you in the right direction. Could you share a bit about your business and what challenges you're trying to solve? We've got a free marketing audit checklist that might be helpful — want me to send it your way?",
  "crm_tags": ["cold_lead"],
  "next_action": "REQUEST_MORE_INFO",
  "created_at": "2026-04-24T10:32:00Z"
}
```
