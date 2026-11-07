from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Organization, Grant, Application, Section, WorkflowEvent, Document, ComplianceIssue, BudgetItem, User, OrganizationMember, TeamMessage, RevokedToken, EligibilityAssessment, HumanApproval, Notification
from app.schemas import OrganizationIn, OrganizationMemberIn, OrganizationMemberRoleIn, GrantImportIn, TrackingUpdate, ReminderIn, SectionEdit, ApprovalIn, HumanMessage, BudgetItemEdit, RegisterIn, LoginIn, ProfileUpdate, TeamMessageIn
from app.security import require_user, hash_password, verify_password, create_access_token, decode_token
from app.settings import settings
from app.workflow import start_application, upload_document_handoff, seed_demo_content, record
from app.switch_events import run_switch_event_listener
from app.workflow_router import begin_drafting
from app.document_processing import extract_text

@asynccontextmanager
async def lifespan(application):
    stop = asyncio.Event()
    listener = asyncio.create_task(run_switch_event_listener(stop))
    try:
        yield
    finally:
        stop.set()
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass


app = FastAPI(title="GRANTBRIDGE API", version="0.1.0", lifespan=lifespan)


def grant_json(g: Grant):
    return {"id": g.id, "title": g.title, "funder": g.funder, "amount": g.amount,
            "deadline": g.deadline, "sector": g.sector, "source_url": g.source_url,
            "is_sample": g.is_sample, "source_status": g.source_status, "requirements": g.requirements}


def organization_json(o: Organization):
    fields = [o.name, o.org_type, o.country, o.mission, o.registration_number, o.operating_regions,
              bool(o.areas_of_operation), o.beneficiaries, o.previous_projects, o.previous_funding,
              o.contact_email, o.contact_phone]
    completed = sum(1 for value in fields if value and value.strip())
    return {"id": o.id, "name": o.name, "org_type": o.org_type, "country": o.country,
            "mission": o.mission, "registration_number": o.registration_number,
            "operating_regions": o.operating_regions, "areas_of_operation": o.areas_of_operation,
            "beneficiaries": o.beneficiaries, "previous_projects": o.previous_projects,
            "previous_funding": o.previous_funding, "contact_email": o.contact_email,
            "contact_phone": o.contact_phone,
            "completion": round(completed * 100 / len(fields))}


def application_json(a: Application):
    return {"id": a.id, "organization_id": a.organization_id, "grant_id": a.grant_id,
            "status": a.status, "current_stage": a.current_stage,
            "switch_status": a.switch_status, "switch_room_id": a.switch_room_id,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "award_amount_cents": a.award_amount_cents, "reporting_requirements": a.reporting_requirements,
            "created_at": a.created_at.isoformat()}


def owned_org(db: Session, org_id: int, user: str):
    org = db.scalar(select(Organization).join(OrganizationMember).where(
        Organization.id == org_id, OrganizationMember.user_id == user))
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


def owned_app(db: Session, application_id: int, user: str):
    record = db.get(Application, application_id)
    if not record or not record.organization or not db.scalar(select(OrganizationMember.id).where(
        OrganizationMember.organization_id == record.organization_id, OrganizationMember.user_id == user)):
        raise HTTPException(404, "Application not found")
    return record


@app.get("/health")
def health():
    return {"status": "ok", "service": "grantbridge-api"}


@app.get("/v1/session")
def session(user: str = Depends(require_user)):
    return {"user_id": user, "auth_mode": "password_jwt"}


@app.post("/v1/auth/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(id=str(uuid4()), email=payload.email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password))
    db.add(user); db.commit()
    token, expires = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(),
            "user": {"id": user.id, "email": user.email, "display_name": user.display_name}}


@app.post("/v1/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect", headers={"WWW-Authenticate": "Bearer"})
    token, expires = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(),
            "user": {"id": user.id, "email": user.email, "display_name": user.display_name}}


@app.post("/v1/auth/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db), user: str = Depends(require_user)):
    token = (authorization or "")[7:]
    claims = decode_token(token)
    expires = datetime.fromtimestamp(claims["exp"], timezone.utc)
    db.merge(RevokedToken(jti=str(claims["jti"]), expires_at=expires)); db.commit()
    return {"logged_out": True}


@app.get("/v1/profile")
def get_profile(db: Session = Depends(get_db), user: str = Depends(require_user)):
    account = db.get(User, user)
    return {"id": account.id, "email": account.email, "display_name": account.display_name,
            "created_at": account.created_at.isoformat()}


@app.patch("/v1/profile")
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db), user: str = Depends(require_user)):
    account = db.get(User, user)
    account.display_name = payload.display_name
    db.commit(); db.refresh(account)
    return {"id": account.id, "email": account.email, "display_name": account.display_name,
            "created_at": account.created_at.isoformat()}


@app.post("/v1/organizations")
def create_organization(payload: OrganizationIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    org = Organization(**payload.model_dump(), owner_subject=user)
    db.add(org); db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user, role="owner"))
    db.commit(); db.refresh(org)
    return organization_json(org)


@app.get("/v1/organizations")
def organizations(db: Session = Depends(get_db), user: str = Depends(require_user)):
    return [organization_json(o)
            for o in db.scalars(select(Organization).join(OrganizationMember).where(OrganizationMember.user_id == user).order_by(Organization.id.desc())).all()]


def require_org_admin(db: Session, org_id: int, user: str):
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user))
    if not member:
        raise HTTPException(404, "Organization not found")
    if member.role not in {"owner", "admin"}:
        raise HTTPException(403, "Organization administrator access required")
    return member


def require_org_editor(db: Session, org_id: int, user: str):
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user))
    if not member:
        raise HTTPException(404, "Organization not found")
    if member.role == "viewer":
        raise HTTPException(403, "Organization editor access required")
    return member


def application_digest(a: Application) -> str:
    snapshot = {
        "grant_id": a.grant_id,
        "sections": sorted((s.title, s.content) for s in a.sections),
        "budget": sorted((b.category, b.description, b.amount_cents, b.currency, b.approval_status) for b in a.budget_items),
        "issues": sorted((i.issue, i.resolved) for i in a.issues),
    }
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def invalidate_approval(db: Session, a: Application, reason: str):
    active = [approval for approval in a.approvals if approval.superseded_at is None and approval.decision == "approved"]
    if not active:
        return
    now = datetime.now(timezone.utc)
    for approval in active:
        approval.superseded_at = now
    a.status = "under_review"
    a.current_stage = "human_review"
    record(db, a, "GRANTBRIDGE", "approval_superseded", reason)


@app.put("/v1/organizations/{org_id}")
def update_organization(org_id: int, payload: OrganizationIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    org = owned_org(db, org_id, user)
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user))
    if member.role == "viewer":
        raise HTTPException(403, "You do not have permission to edit this organization")
    for key, value in payload.model_dump().items():
        setattr(org, key, value)
    db.commit(); db.refresh(org)
    return organization_json(org)


@app.get("/v1/organizations/{org_id}/members")
def list_members(org_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    owned_org(db, org_id, user)
    rows = db.scalars(select(OrganizationMember).where(OrganizationMember.organization_id == org_id).order_by(OrganizationMember.id)).all()
    return [{"id": m.id, "user_id": m.user_id, "email": m.user.email, "display_name": m.user.display_name,
             "role": m.role, "joined_at": m.joined_at.isoformat()} for m in rows]


@app.get("/v1/organizations/{org_id}/team-messages")
def list_team_messages(org_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    owned_org(db, org_id, user)
    rows = db.scalars(select(TeamMessage).where(TeamMessage.organization_id == org_id)
        .order_by(TeamMessage.created_at.desc(), TeamMessage.id.desc()).limit(200)).all()
    return [{"id": m.id, "sender_id": m.sender_id, "sender_name": m.sender.display_name,
             "content": m.content, "created_at": m.created_at.isoformat()} for m in reversed(rows)]


@app.post("/v1/organizations/{org_id}/team-messages")
def send_team_message(org_id: int, payload: TeamMessageIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    owned_org(db, org_id, user)
    require_org_editor(db, org_id, user)
    message = TeamMessage(organization_id=org_id, sender_id=user, content=payload.content)
    db.add(message); db.commit(); db.refresh(message)
    db.refresh(message, attribute_names=["sender"])
    return {"id": message.id, "sender_id": message.sender_id, "sender_name": message.sender.display_name,
            "content": message.content, "created_at": message.created_at.isoformat()}


@app.post("/v1/organizations/{org_id}/members")
def add_member(org_id: int, payload: OrganizationMemberIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    require_org_admin(db, org_id, user)
    invited = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    if not invited:
        raise HTTPException(404, "Create an account for this teammate before adding them")
    if db.scalar(select(OrganizationMember.id).where(OrganizationMember.organization_id == org_id, OrganizationMember.user_id == invited.id)):
        raise HTTPException(409, "This teammate is already in the organization")
    member = OrganizationMember(organization_id=org_id, user_id=invited.id, role=payload.role)
    db.add(member); db.commit(); db.refresh(member)
    return {"id": member.id, "user_id": invited.id, "email": invited.email, "display_name": invited.display_name, "role": member.role}


@app.patch("/v1/organizations/{org_id}/members/{member_id}")
def change_member_role(org_id: int, member_id: int, payload: OrganizationMemberRoleIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    require_org_admin(db, org_id, user)
    member = db.get(OrganizationMember, member_id)
    if not member or member.organization_id != org_id or member.role == "owner":
        raise HTTPException(404, "Member not found")
    member.role = payload.role
    db.commit()
    return {"id": member.id, "role": member.role}


@app.delete("/v1/organizations/{org_id}/members/{member_id}")
def remove_member(org_id: int, member_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    require_org_admin(db, org_id, user)
    member = db.get(OrganizationMember, member_id)
    if not member or member.organization_id != org_id or member.role == "owner":
        raise HTTPException(404, "Member not found")
    db.delete(member); db.commit()
    return {"removed": True}


@app.get("/v1/grants")
def grants(q: str = "", sector: str = "", country: str = "", org_type: str = "", db: Session = Depends(get_db), user: str = Depends(require_user)):
    statement = select(Grant)
    if q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where((Grant.title.ilike(term)) | (Grant.funder.ilike(term)) | (Grant.sector.ilike(term)))
    if sector.strip():
        statement = statement.where(Grant.sector.ilike(f"%{sector.strip()}%"))
    results = db.scalars(statement.order_by(Grant.id.desc())).all()
    if country.strip():
        results = [g for g in results if not g.requirements or any(country.casefold() in str(r).casefold() for r in g.requirements)]
    if org_type.strip():
        results = [g for g in results if not g.requirements or any(org_type.casefold() in str(r).casefold() for r in g.requirements)]
    return [grant_json(g) for g in results]


@app.get("/v1/grants/{grant_id}")
def grant_detail(grant_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    grant = db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    return grant_json(grant)


@app.post("/v1/grants/import")
def import_grant(payload: GrantImportIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    grant = Grant(title=payload.title, funder=payload.funder, amount=payload.amount,
        deadline=payload.deadline.date().isoformat() if payload.deadline else "Not provided",
        sector=payload.sector, source_url=payload.source_url, is_sample=False,
        source_status="user_provided_unverified", requirements=payload.requirements)
    db.add(grant); db.commit(); db.refresh(grant)
    return grant_json(grant)


@app.post("/v1/demo/seed")
def seed_demo(db: Session = Depends(get_db), user: str = Depends(require_user)):
    found = db.scalar(select(Grant).where(Grant.title == "Rural Digital Learning Access (Sample)"))
    if not found:
        found = Grant(title="Rural Digital Learning Access (Sample)", funder="GRANTBRIDGE Demonstration Fund",
            amount="Up to $75,000 (sample)", deadline="2027-03-31 (sample)", sector="Education",
            source_url="https://example.org/grants/digital-learning-sample", is_sample=True, source_status="sample",
            requirements=["Registered nonprofit", "Education project", "Organizational registration certificate", "Itemized budget"])
        db.add(found); db.commit(); db.refresh(found)
    return grant_json(found)


@app.post("/v1/organizations/{org_id}/applications")
async def create_application(org_id: int, grant_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    org = owned_org(db, org_id, user)
    grant = db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    application = Application(organization_id=org.id, grant_id=grant.id)
    db.add(application); db.commit(); db.refresh(application)
    await start_application(db, application, org, grant)
    seed_demo_content(db, application, org.name)
    members = db.scalars(select(OrganizationMember).where(OrganizationMember.organization_id == org.id)).all()
    try:
        due = datetime.fromisoformat(grant.deadline[:10]).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        due = None
    for member in members:
        db.add(Notification(organization_id=org.id, application_id=application.id, user_id=member.user_id,
            title="Grant application started", body=f"{grant.title} is ready for your review.", notification_type="workflow"))
        if due:
            db.add(Notification(organization_id=org.id, application_id=application.id, user_id=member.user_id,
                title="Grant deadline", body=f"Deadline for {grant.title} is {due.date().isoformat()}.",
                notification_type="deadline", due_at=due))
    db.commit()
    return application_json(application)


@app.get("/v1/organizations/{org_id}/applications")
def list_applications(org_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    owned_org(db, org_id, user)
    return [application_json(a) for a in db.scalars(select(Application).where(Application.organization_id == org_id).order_by(Application.id.desc())).all()]


@app.get("/v1/applications/{application_id}")
def application_detail(application_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    org = owned_org(db, a.organization_id, user)
    grant = db.get(Grant, a.grant_id)
    return {**application_json(a), "organization": {"id": org.id, "name": org.name},
        "grant": grant_json(grant),
        "eligibility_assessments": [{"id": e.id, "status": e.status, "matching_requirements": e.matching_requirements,
            "missing_requirements": e.missing_requirements, "disqualifying_conditions": e.disqualifying_conditions,
            "evidence": e.evidence, "required_documents": e.required_documents,
            "provenance": e.provenance, "created_at": e.created_at.isoformat()} for e in a.eligibility_assessments],
        "documents": [{"id": d.id, "filename": d.filename, "category": d.category, "text_extracted": bool(d.extracted_text)}
            for d in db.scalars(select(Document).where(Document.application_id == a.id)).all()],
        "approvals": [{"id": h.id, "decision": h.decision, "note": h.note, "content_digest": h.content_digest,
            "created_at": h.created_at.isoformat(), "superseded_at": h.superseded_at.isoformat() if h.superseded_at else None}
            for h in a.approvals],
        "sections": [{"id": s.id, "title": s.title, "content": s.content, "provenance": s.provenance} for s in a.sections],
        "budget_items": [{"id": b.id, "category": b.category, "description": b.description,
                          "amount_cents": b.amount_cents, "currency": b.currency,
                          "provenance": b.provenance, "approval_status": b.approval_status} for b in a.budget_items],
        "issues": [{"id": i.id, "issue": i.issue, "severity": i.severity, "requirement": i.requirement,
                    "evidence": i.evidence, "suggested_correction": i.suggested_correction,
                    "assigned_to": i.assigned_to, "revision_requested": i.revision_requested,
                    "resolved": i.resolved} for i in a.issues],
        "events": [{"id": e.id, "actor": e.actor, "event_type": e.event_type, "detail": e.detail,
                    "source": e.source, "created_at": e.created_at.isoformat()} for e in a.events]}


@app.put("/v1/applications/{application_id}/sections/{section_id}")
def edit_section(application_id: int, section_id: int, payload: SectionEdit, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    require_org_editor(db, a.organization_id, user)
    section = db.get(Section, section_id)
    if not section or section.application_id != a.id:
        raise HTTPException(404, "Section not found")
    invalidate_approval(db, a, f"Approved content changed: section {section.title} was edited.")
    section.content = payload.content
    section.provenance = "human_edited"
    record(db, a, "Human", "section_edited", section.title, "human")
    db.commit()
    return {"id": section.id, "title": section.title, "content": section.content, "provenance": section.provenance}


@app.put("/v1/applications/{application_id}/budget-items/{item_id}")
async def edit_budget_item(application_id: int, item_id: int, payload: BudgetItemEdit, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    require_org_editor(db, a.organization_id, user)
    item = db.get(BudgetItem, item_id)
    if not item or item.application_id != a.id:
        raise HTTPException(404, "Budget item not found")
    invalidate_approval(db, a, f"Approved content changed: budget category {item.category} was edited.")
    item.amount_cents = payload.amount_cents
    item.currency = payload.currency
    item.provenance = "human_provided"
    item.approval_status = "human_approved" if payload.approved else "awaiting_human"
    record(db, a, "Human", "budget_item_reviewed", f"{item.category}: {item.currency} {item.amount_cents / 100:.2f}; approved={payload.approved}", "human")
    db.commit()
    drafting_started = await begin_drafting(a.id)
    return {"id": item.id, "amount_cents": item.amount_cents, "currency": item.currency, "provenance": item.provenance,
            "approval_status": item.approval_status, "drafting_started": drafting_started}


@app.post("/v1/applications/{application_id}/documents")
async def upload_document(application_id: int, file: UploadFile = File(...), category: str = Form(default="supporting_evidence"), db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    owned_org(db, a.organization_id, user)
    require_org_editor(db, a.organization_id, user)
    allowed = {"application/pdf", "image/png", "image/jpeg", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Upload a PDF, DOCX, PNG, JPG, or text file")
    allowed_categories = {"registration_certificate", "financial_statement", "annual_report", "project_proposal", "audited_accounts", "organizational_policy", "supporting_evidence"}
    if category not in allowed_categories:
        raise HTTPException(422, "Unknown document category")
    blob = await file.read(10 * 1024 * 1024 + 1)
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds the 10 MB limit")
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    key = uuid4().hex
    Path(settings.upload_dir, key).write_bytes(blob)
    extracted = extract_text(file.filename or "document", file.content_type, blob)
    doc = Document(organization_id=a.organization_id, application_id=a.id, owner_subject=user, category=category, filename=Path(file.filename or "document").name,
                   content_type=file.content_type, storage_key=key, byte_size=len(blob), extracted_text=extracted)
    db.add(doc); db.commit(); db.refresh(doc)
    await upload_document_handoff(db, a, doc.filename, doc.category, extracted)
    return {"id": doc.id, "filename": doc.filename, "category": doc.category, "content_type": doc.content_type, "byte_size": doc.byte_size,
            "text_extracted": bool(extracted),
            "provenance": "human_provided", "switch_handoff": a.switch_status == "connected"}


@app.get("/v1/organizations/{org_id}/documents")
def list_documents(org_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    owned_org(db, org_id, user)
    docs = db.scalars(select(Document).where(Document.organization_id == org_id).order_by(Document.created_at.desc())).all()
    return [{"id": d.id, "filename": d.filename, "category": d.category, "content_type": d.content_type,
             "byte_size": d.byte_size, "text_extracted": bool(d.extracted_text), "created_at": d.created_at.isoformat()}
            for d in docs]


@app.get("/v1/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    owned_org(db, doc.organization_id, user)
    path = Path(settings.upload_dir, doc.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Document content is unavailable")
    return FileResponse(path, media_type=doc.content_type, filename=doc.filename)


@app.post("/v1/applications/{application_id}/messages")
async def human_message(application_id: int, payload: HumanMessage, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    owned_org(db, a.organization_id, user)
    require_org_editor(db, a.organization_id, user)
    record(db, a, "Human", "message", payload.content, "human")
    sent = False
    if a.switch_status == "connected":
        try:
            from app.switch_adapter import SwitchAdapter
            if payload.recipient:
                result = await SwitchAdapter().handoff(a.switch_room_id, payload.recipient, f"[Human input via GRANTBRIDGE] {payload.content}")
            else:
                result = await SwitchAdapter().post_human_note(a.switch_room_id, payload.content)
            sent = True
            record(db, a, "GRANTBRIDGE", "switch_message", f"Human input shared to the application room. Switch result: {result}.", "switch")
        except Exception as exc:
            record(db, a, "GRANTBRIDGE", "switch_message_failed", str(exc))
    db.commit()
    return {"saved": True, "shared_to_switch": sent}


@app.post("/v1/applications/{application_id}/issues/{issue_id}/handoff")
async def handoff_issue(application_id: int, issue_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    require_org_editor(db, a.organization_id, user)
    issue = db.get(ComplianceIssue, issue_id)
    if not issue or issue.application_id != a.id:
        raise HTTPException(404, "Issue not found")
    detail = f"Compliance finding sent for revision: {issue.issue} Suggested correction: {issue.suggested_correction}"
    invalidate_approval(db, a, f"Approved content returned for revision: {issue.issue}")
    issue.revision_requested = True
    handed_off = False
    if a.switch_status == "connected":
        try:
            result = await __import__("app.switch_adapter", fromlist=["SwitchAdapter"]).SwitchAdapter().handoff(a.switch_room_id, issue.assigned_to, detail)
            handed_off = True
            record(db, a, "Compliance Reviewer", "handoff", f"{detail} Switch result: {result}.", "switch")
        except Exception as exc:
            record(db, a, "GRANTBRIDGE", "handoff_failed", str(exc))
    else:
        record(db, a, "GRANTBRIDGE", "switch_unavailable", "Issue marked for revision locally; no Switch handoff was sent.")
    a.current_stage = "revision"
    record(db, a, "Human", "revision_requested", "Requested correction for the compliance finding.", "human")
    db.commit()
    return {"revision_requested": True, "switch_handoff": handed_off}


@app.post("/v1/applications/{application_id}/issues/{issue_id}/resolve")
def resolve_issue(application_id: int, issue_id: int, payload: HumanMessage, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    require_org_editor(db, a.organization_id, user)
    issue = db.get(ComplianceIssue, issue_id)
    if not issue or issue.application_id != a.id:
        raise HTTPException(404, "Issue not found")
    if not issue.revision_requested:
        raise HTTPException(409, "Request a revision before marking the issue resolved")
    invalidate_approval(db, a, f"Compliance issue resolution changed: {issue.issue}")
    issue.resolved = True
    record(db, a, "Human", "issue_resolved", payload.content, "human")
    db.commit()
    return {"resolved": True}


@app.post("/v1/applications/{application_id}/approve")
def approve(application_id: int, payload: ApprovalIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    owned_org(db, a.organization_id, user)
    require_org_editor(db, a.organization_id, user)
    if not payload.approved:
        a.status = "under_review"
        record(db, a, "Human", "approval_declined", payload.note or "Human requested further changes.", "human")
        db.add(HumanApproval(application_id=a.id, user_id=user, decision="changes_requested",
            note=payload.note or "Human requested further changes.", content_digest=application_digest(a)))
    else:
        unresolved = db.scalar(select(ComplianceIssue).where(ComplianceIssue.application_id == a.id, ComplianceIssue.resolved.is_(False)))
        if unresolved:
            raise HTTPException(409, "Resolve all compliance issues before approval")
        pending_budget = db.scalar(select(BudgetItem).where(BudgetItem.application_id == a.id,
            (BudgetItem.amount_cents.is_(None)) | (BudgetItem.approval_status != "human_approved")))
        if pending_budget:
            raise HTTPException(409, "Enter and approve every budget amount before final approval")
        a.status = "approved"
        a.current_stage = "approved"
        digest = application_digest(a)
        approval = HumanApproval(application_id=a.id, user_id=user, decision="approved", note=payload.note,
                                 content_digest=digest)
        db.add(approval)
        record(db, a, "Human", "application_approved", f"Human approved the current draft (SHA-256 {digest}). It has not been submitted.", "human")
    db.commit()
    return application_json(a)


@app.put("/v1/applications/{application_id}/tracking")
def update_tracking(application_id: int, payload: TrackingUpdate, db: Session = Depends(get_db), user: str = Depends(require_user)):
    a = owned_app(db, application_id, user)
    require_org_editor(db, a.organization_id, user)
    previous = a.status
    allowed = {
        "draft": {"draft", "under_review", "awaiting_human_approval"},
        "under_review": {"under_review", "awaiting_human_approval", "draft"},
        "awaiting_human_approval": {"awaiting_human_approval", "under_review", "approved"},
        "approved": {"approved", "submitted", "under_review"},
        "submitted": {"submitted", "awarded", "rejected"},
        "awarded": {"awarded"},
        "rejected": {"rejected"},
    }
    if payload.status not in allowed.get(previous, set()):
        raise HTTPException(409, f"Cannot move application from {previous} to {payload.status}")
    if payload.status == "approved" and previous != "approved":
        raise HTTPException(409, "Use the human approval action to approve an application")
    if payload.status == "submitted" and previous != "approved":
        raise HTTPException(409, "A human must approve the application before marking it submitted")
    if payload.status in {"awarded", "rejected"} and previous != "submitted":
        raise HTTPException(409, "Record an award or rejection after manual submission")
    a.status = payload.status
    if payload.status == "submitted":
        a.submitted_at = payload.submitted_at or datetime.now(timezone.utc)
        record(db, a, "Human", "application_marked_submitted", "Organization recorded that it submitted the application outside GRANTBRIDGE.", "human")
    elif payload.status != previous:
        record(db, a, "Human", f"application_status_{payload.status}", f"Status changed from {previous} to {payload.status}.", "human")
    if payload.award_amount_cents is not None:
        a.award_amount_cents = payload.award_amount_cents
    a.reporting_requirements = payload.reporting_requirements
    db.commit()
    return application_json(a)


@app.get("/v1/notifications")
def notifications(db: Session = Depends(get_db), user: str = Depends(require_user)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user).order_by(Notification.created_at.desc()).limit(100)).all()
    return [{"id": n.id, "organization_id": n.organization_id, "application_id": n.application_id,
             "title": n.title, "body": n.body, "type": n.notification_type,
             "due_at": n.due_at.isoformat() if n.due_at else None,
             "read_at": n.read_at.isoformat() if n.read_at else None,
             "created_at": n.created_at.isoformat()} for n in rows]


@app.post("/v1/notifications/reminders")
def create_reminder(payload: ReminderIn, db: Session = Depends(get_db), user: str = Depends(require_user)):
    org = owned_org(db, payload.organization_id, user)
    require_org_editor(db, org.id, user)
    if payload.application_id is not None:
        a = owned_app(db, payload.application_id, user)
        if a.organization_id != org.id:
            raise HTTPException(422, "Application must belong to the selected organization")
    notification = Notification(organization_id=org.id, application_id=payload.application_id, user_id=user,
        title=payload.title, body=payload.body, notification_type="reminder", due_at=payload.due_at)
    db.add(notification); db.commit(); db.refresh(notification)
    return {"id": notification.id, "title": notification.title, "due_at": notification.due_at.isoformat() if notification.due_at else None}


@app.post("/v1/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: str = Depends(require_user)):
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user:
        raise HTTPException(404, "Notification not found")
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"read": True}
