from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=2, max_length=160)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        email = value.strip().casefold()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return email


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        email = value.strip().casefold()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return email


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name must contain at least two characters")
        return value


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    org_type: str = "Nonprofit"
    country: str = ""
    mission: str = ""
    registration_number: str = ""
    operating_regions: str = ""
    areas_of_operation: list[str] = Field(default_factory=list, max_length=20)
    beneficiaries: str = ""
    previous_projects: str = ""
    previous_funding: str = ""
    contact_email: str = ""
    contact_phone: str = ""


class OrganizationMemberIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: str = "member"

    @field_validator("email")
    @classmethod
    def normalize_member_email(cls, value):
        return value.strip().casefold()

    @field_validator("role")
    @classmethod
    def validate_member_role(cls, value):
        if value not in {"admin", "member", "viewer"}:
            raise ValueError("Role must be admin, member, or viewer")
        return value


class OrganizationMemberRoleIn(BaseModel):
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_member_role(cls, value):
        if value not in {"admin", "member", "viewer"}:
            raise ValueError("Role must be admin, member, or viewer")
        return value


class GrantImportIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    funder: str = Field(min_length=2, max_length=200)
    amount: str = Field(min_length=1, max_length=100)
    deadline: datetime | None = None
    sector: str = Field(min_length=2, max_length=100)
    source_url: str = Field(min_length=10, max_length=2000)
    requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("source_url")
    @classmethod
    def require_https_source(cls, value):
        if not value.startswith("https://"):
            raise ValueError("Source URL must use HTTPS")
        return value


class TrackingUpdate(BaseModel):
    status: str
    submitted_at: datetime | None = None
    award_amount_cents: int | None = Field(default=None, ge=0)
    reporting_requirements: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        allowed = {"draft", "under_review", "awaiting_human_approval", "approved", "submitted", "awarded", "rejected"}
        if value not in allowed:
            raise ValueError("Invalid application status")
        return value


class ReminderIn(BaseModel):
    organization_id: int
    application_id: int | None = None
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=2, max_length=2000)
    due_at: datetime | None = None


class SectionEdit(BaseModel):
    content: str = Field(max_length=12000)


class ApprovalIn(BaseModel):
    approved: bool
    note: str = ""


class BudgetItemEdit(BaseModel):
    amount_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    approved: bool

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value):
        return value.upper()


class HumanMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    recipient: str | None = None

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value):
        allowed = {None, "Grant Scout", "Eligibility Analyst", "Budget Analyst", "Grant Writer", "Compliance Reviewer", "Reporting Agent"}
        if value not in allowed:
            raise ValueError("Unknown team member")
        return value


class TeamMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value
