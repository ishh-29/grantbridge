"""Routes replies between specialists through Switch's addressed-message operation."""
import json
import logging
import re
import asyncio
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Application, Organization, Grant, Document, BudgetItem, Section, ComplianceIssue, WorkflowEvent, EligibilityAssessment
from app.settings import settings

log = logging.getLogger(__name__)
route_lock = asyncio.Lock()


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def role_for_sender(sender: str) -> str | None:
    mapping = {
        settings.switch_scout_name: "Grant Scout",
        settings.switch_eligibility_name: "Eligibility Analyst",
        settings.switch_budget_name: "Budget Analyst",
        settings.switch_writer_name: "Grant Writer",
        settings.switch_compliance_name: "Compliance Reviewer",
        "reporting-agent": "Reporting Agent",
    }
    return next((role for name, role in mapping.items() if normalized(sender) == normalized(name)), None)


def parse_json(body: str):
    candidate = body.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None


async def route_agent_reply(application_id: int, sender: str, body: str) -> None:
    async with route_lock:
        await _route_agent_reply(application_id, sender, body)


async def _route_agent_reply(application_id: int, sender: str, body: str) -> None:
    role = role_for_sender(sender)
    if not role:
        return
    from app.switch_adapter import SwitchAdapter

    with SessionLocal() as db:
        app = db.get(Application, application_id)
        if not app or app.switch_status != "connected":
            return
        org = db.get(Organization, app.organization_id)
        grant = db.get(Grant, app.grant_id)
        stage = app.current_stage
        docs = db.scalars(select(Document).where(Document.organization_id == org.id)).all()
        sections = db.scalars(select(Section).where(Section.application_id == app.id)).all()
        room_id = app.switch_room_id

    recipient = None
    next_stage = None
    prompt = ""
    if role == "Grant Scout" and stage == "scout":
        recipient, next_stage = "Eligibility Analyst", "eligibility"
        prompt = (f"Assume the Eligibility Analyst role. Compare these Scout findings with the organization's verified profile and evidence. Return JSON fields status, matching_requirements, missing_requirements, disqualifying_conditions, evidence, and required_documents. Scout findings: {body}\nOrganization: {org.name}; type={org.org_type}; country={org.country}; mission={org.mission}; registration number={org.registration_number or 'not provided'}.")
    elif role == "Eligibility Analyst" and stage == "eligibility":
        parsed = parse_json(body)
        status = parsed.get("status") if isinstance(parsed, dict) else None
        if isinstance(status, str):
            status = normalized(status).casefold()
            status = {"eligible": "eligible", "potentiallyeligible": "potentially_eligible",
                "ineligible": "ineligible", "needshumanverification": "needs_human_verification"}.get(status)
        if status not in {"eligible", "potentially_eligible", "ineligible", "needs_human_verification"}:
            status = "needs_human_verification"
        with SessionLocal() as db:
            db.add(EligibilityAssessment(application_id=application_id, status=status,
                matching_requirements=parsed.get("matching_requirements", []) if isinstance(parsed, dict) else [],
                missing_requirements=parsed.get("missing_requirements", []) if isinstance(parsed, dict) else [],
                disqualifying_conditions=parsed.get("disqualifying_conditions", []) if isinstance(parsed, dict) else [],
                evidence=parsed.get("evidence", []) if isinstance(parsed, dict) else [],
                required_documents=parsed.get("required_documents", []) if isinstance(parsed, dict) else [],
                provenance="ai_generated_switch"))
            db.commit()
        has_registration = any(d.category == "registration_certificate" for d in docs)
        if not has_registration:
            with SessionLocal() as db:
                app = db.get(Application, application_id)
                app.current_stage = "awaiting_document"
                db.add(WorkflowEvent(application_id=app.id, actor="Eligibility Analyst", event_type="human_document_needed",
                    detail="Provide the organization's registration certificate or add a verified registration number before this assessment can proceed.", source="switch"))
                db.commit()
            return
        recipient, next_stage = "Budget Analyst", "budget"
        prompt = f"Assume the Budget Analyst role. Review grant funding limits and allowed expense categories. Do not invent cost amounts. Return eligible categories, restrictions, and questions. Eligibility findings: {body}; grant requirements: {grant.requirements}; maximum: {grant.amount}."
    elif role == "Budget Analyst" and stage == "budget":
        parsed = parse_json(body)
        categories = parsed.get("eligible_categories") if isinstance(parsed, dict) else None
        if not isinstance(categories, list) or not categories:
            recipient, next_stage = "Budget Analyst", "budget"
            prompt = "Return only valid JSON with eligible_categories: [{category, description, constraints}]. Do not provide cost amounts; each amount must be entered and approved by the human."
        else:
            with SessionLocal() as db:
                existing = db.scalars(select(BudgetItem).where(BudgetItem.application_id == application_id)).all()
                if not existing:
                    for item in categories:
                        if not isinstance(item, dict) or not item.get("category"):
                            continue
                        db.add(BudgetItem(application_id=application_id, category=str(item["category"])[:100],
                            description=str(item.get("description", item.get("constraints", "")))[:4000],
                            provenance="ai_generated_switch", approval_status="awaiting_human"))
                app = db.get(Application, application_id)
                app.current_stage = "awaiting_budget"
                db.add(WorkflowEvent(application_id=app.id, actor="Budget Analyst", event_type="human_budget_needed",
                    detail="Budget categories and constraints received. Enter and approve each amount before drafting can continue.", source="switch"))
                db.commit()
            return
    elif role == "Grant Writer" and stage in {"writing", "revision"}:
        parsed = parse_json(body)
        if isinstance(parsed, dict) and isinstance(parsed.get("sections"), list):
            with SessionLocal() as db:
                for draft in parsed["sections"]:
                    if not isinstance(draft, dict) or not draft.get("title") or not isinstance(draft.get("content"), str):
                        continue
                    section = db.scalar(select(Section).where(Section.application_id == application_id, Section.title == draft["title"]))
                    if section:
                        section.content = draft["content"][:12000]
                        section.provenance = "ai_generated_switch"
                db.commit()
        recipient, next_stage = "Compliance Reviewer", "compliance"
        prompt = f"Assume the Compliance Reviewer role. Independently check requirements, evidence, unsupported claims, contradictions, documents and budget consistency. Return JSON with overall_readiness and issues[] containing issue, severity, requirement, evidence, suggested_correction, assigned_to. Draft from Grant Writer: {body}"
    elif role == "Compliance Reviewer" and stage == "compliance":
        parsed = parse_json(body)
        if isinstance(parsed, dict) and isinstance(parsed.get("issues"), list):
            with SessionLocal() as db:
                for item in parsed["issues"]:
                    if not isinstance(item, dict) or not item.get("issue"):
                        continue
                    duplicate = db.scalar(select(ComplianceIssue).where(
                        ComplianceIssue.application_id == application_id, ComplianceIssue.issue == str(item["issue"])))
                    if duplicate:
                        continue
                    assigned = item.get("assigned_to")
                    if not isinstance(assigned, str) or assigned not in {"Grant Scout", "Eligibility Analyst", "Budget Analyst", "Grant Writer", "Compliance Reviewer", "Reporting Agent"}:
                        assigned = "Grant Writer"
                    db.add(ComplianceIssue(application_id=application_id,
                        issue=str(item["issue"])[:4000], severity=str(item.get("severity", "medium"))[:20],
                        requirement=str(item.get("requirement", ""))[:4000], evidence=str(item.get("evidence", ""))[:4000],
                        suggested_correction=str(item.get("suggested_correction", ""))[:4000],
                        assigned_to=str(assigned)[:100]))
                db.commit()
        return
    else:
        return

    try:
        result = await SwitchAdapter().handoff(room_id, recipient, prompt)
        with SessionLocal() as db:
            app = db.get(Application, application_id)
            app.current_stage = next_stage
            db.add(WorkflowEvent(application_id=app.id, actor=sender, event_type="agent_handoff",
                detail=f"Routed reply to {recipient}. Switch result: {result}.", source="switch"))
            db.commit()
    except Exception:
        log.exception("Unable to route agent reply for application %s", application_id)


async def begin_drafting(application_id: int) -> bool:
    from app.switch_adapter import SwitchAdapter
    with SessionLocal() as db:
        app = db.get(Application, application_id)
        if not app or app.switch_status != "connected" or app.current_stage != "awaiting_budget":
            return False
        items = db.scalars(select(BudgetItem).where(BudgetItem.application_id == app.id)).all()
        if not items or any(i.amount_cents is None or i.approval_status != "human_approved" for i in items):
            return False
        org = db.get(Organization, app.organization_id)
        grant = db.get(Grant, app.grant_id)
        room_id = app.switch_room_id
        budget = [{"category": i.category, "amount": f"{i.currency} {i.amount_cents / 100:.2f}"} for i in items]
        section_titles = [s.title for s in db.scalars(select(Section).where(Section.application_id == app.id)).all()]
    try:
        result = await SwitchAdapter().handoff(room_id, "Grant Writer",
            f"Assume the Grant Writer role. Draft the application in JSON: {{sections:[{{title,content}}]}} with these exact section titles: {section_titles}. Use only verified organization information, grant requirements, registration evidence and the human-approved budget. Never invent impact data or credentials. Organization: {org.name}; mission: {org.mission}; registration: {org.registration_number}; grant requirements: {grant.requirements}; approved budget: {budget}.")
        with SessionLocal() as db:
            app = db.get(Application, application_id)
            app.current_stage = "writing"
            db.add(WorkflowEvent(application_id=app.id, actor="Human", event_type="budget_approved",
                detail=f"Human-approved budget handed to Grant Writer. Switch result: {result}.", source="switch"))
            db.commit()
        return True
    except Exception:
        log.exception("Unable to start Grant Writer handoff for application %s", application_id)
        return False
