from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_subject: Mapped[str] = mapped_column(String(160), index=True, default="")
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[str] = mapped_column(String(100), default="Nonprofit")
    country: Mapped[str] = mapped_column(String(100), default="")
    mission: Mapped[str] = mapped_column(Text, default="")
    registration_number: Mapped[str] = mapped_column(String(100), default="")
    operating_regions: Mapped[str] = mapped_column(Text, default="")
    areas_of_operation: Mapped[list] = mapped_column(JSON, default=list)
    beneficiaries: Mapped[str] = mapped_column(Text, default="")
    previous_projects: Mapped[str] = mapped_column(Text, default="")
    previous_funding: Mapped[str] = mapped_column(Text, default="")
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    applications: Mapped[list["Application"]] = relationship(back_populates="organization")
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    memberships: Mapped[list["OrganizationMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(40), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class TeamMessage(Base):
    __tablename__ = "team_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    sender: Mapped[User] = relationship()


class Grant(Base):
    __tablename__ = "grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    funder: Mapped[str] = mapped_column(String(200))
    amount: Mapped[str] = mapped_column(String(100))
    deadline: Mapped[str] = mapped_column(String(100))
    sector: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(default=True)
    source_status: Mapped[str] = mapped_column(String(40), default="sample")
    requirements: Mapped[list] = mapped_column(JSON, default=list)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    grant_id: Mapped[int] = mapped_column(ForeignKey("grants.id"))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    current_stage: Mapped[str] = mapped_column(String(80), default="eligibility")
    switch_room_id: Mapped[str] = mapped_column(String(100), default="")
    switch_status: Mapped[str] = mapped_column(String(40), default="unconfigured")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    award_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reporting_requirements: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    organization: Mapped[Organization] = relationship(back_populates="applications")
    sections: Mapped[list["Section"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    events: Mapped[list["WorkflowEvent"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    issues: Mapped[list["ComplianceIssue"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    budget_items: Mapped[list["BudgetItem"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    eligibility_assessments: Mapped[list["EligibilityAssessment"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    approvals: Mapped[list["HumanApproval"]] = relationship(back_populates="application", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(String(40), default="ai_generated")
    application: Mapped[Application] = relationship(back_populates="sections")


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    actor: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="backend")
    switch_event_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    application: Mapped[Application] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, index=True)
    owner_subject: Mapped[str] = mapped_column(String(160), index=True, default="")
    filename: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), default="supporting_evidence")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(150))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ComplianceIssue(Base):
    __tablename__ = "compliance_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    issue: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    requirement: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    suggested_correction: Mapped[str] = mapped_column(Text, default="")
    assigned_to: Mapped[str] = mapped_column(String(100), default="Grant Writer")
    revision_requested: Mapped[bool] = mapped_column(default=False)
    resolved: Mapped[bool] = mapped_column(default=False)
    application: Mapped[Application] = relationship(back_populates="issues")


class BudgetItem(Base):
    __tablename__ = "budget_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    provenance: Mapped[str] = mapped_column(String(40), default="ai_generated_demo")
    approval_status: Mapped[str] = mapped_column(String(40), default="awaiting_human")
    application: Mapped[Application] = relationship(back_populates="budget_items")


class EligibilityAssessment(Base):
    __tablename__ = "eligibility_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    status: Mapped[str] = mapped_column(String(40), default="needs_human_verification")
    matching_requirements: Mapped[list] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    disqualifying_conditions: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    required_documents: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[str] = mapped_column(String(40), default="ai_generated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    application: Mapped[Application] = relationship(back_populates="eligibility_assessments")


class HumanApproval(Base):
    __tablename__ = "human_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    content_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application: Mapped[Application] = relationship(back_populates="approvals")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(50), default="task")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SwitchCursor(Base):
    __tablename__ = "switch_cursors"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    connection_id: Mapped[str] = mapped_column(String(36))
    generation: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
