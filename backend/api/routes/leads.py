"""Q1: Lead classification and response API routes."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.schemas import LeadInput, LeadClassificationResult
from models.database import get_db, LeadRecord
from services.lead_classifier import classify_lead
from api.middleware.auth import require_api_key
from services.response_generator import (
    generate_response,
    determine_crm_tags,
    determine_next_action,
)

router = APIRouter()


@router.post("/classify", response_model=LeadClassificationResult)
async def classify_and_respond(lead: LeadInput, db: Session = Depends(get_db), _key: str = Depends(require_api_key)):
    """Classify a lead submission and generate a personalized response."""
    lead_data = lead.model_dump(exclude_none=True)

    # Step 1: Classify the lead
    classification_result = await classify_lead(lead_data)

    classification = classification_result["classification"]
    confidence = classification_result["confidence"]
    reasoning = classification_result["reasoning"]
    missing_signals = classification_result.get("missing_signals", [])
    follow_up_questions = classification_result.get("follow_up_questions", [])

    # Step 2: Generate personalized response
    suggested_response = await generate_response(lead_data, classification, missing_signals)

    # Step 3: Determine CRM tags and next action
    crm_tags = determine_crm_tags(lead_data, classification)
    next_action = determine_next_action(classification, missing_signals)

    # Step 4: Generate lead ID and persist
    lead_id = f"lead_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:4]}"

    db_record = LeadRecord(
        id=lead_id,
        name=lead.name,
        email=lead.email,
        company=lead.company,
        company_size=lead.company_size,
        budget_range=lead.budget_range,
        timeline=lead.timeline,
        use_case=lead.use_case,
        phone=lead.phone,
        industry=lead.industry,
        source=lead.source,
        classification=classification,
        confidence=confidence,
        reasoning=reasoning,
        suggested_response=suggested_response,
        crm_tags=crm_tags,
        assigned_to=None,
        next_action=next_action,
        raw_input=lead_data,
    )
    db.add(db_record)
    db.commit()

    return LeadClassificationResult(
        lead_id=lead_id,
        classification=classification,
        confidence=confidence,
        reasoning=reasoning,
        missing_signals=missing_signals,
        follow_up_questions=follow_up_questions,
        suggested_response=suggested_response,
        crm_tags=crm_tags,
        next_action=next_action,
    )


@router.get("/")
async def list_leads(
    classification: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """List classified leads with optional filtering."""
    query = db.query(LeadRecord)
    if classification:
        query = query.filter(LeadRecord.classification == classification.upper())
    leads = query.order_by(LeadRecord.created_at.desc()).limit(limit).all()

    return [
        {
            "lead_id": l.id,
            "name": l.name,
            "email": l.email,
            "company": l.company,
            "classification": l.classification,
            "confidence": l.confidence,
            "next_action": l.next_action,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in leads
    ]
