import os
import tempfile
import asyncio

_tmp = tempfile.TemporaryDirectory(prefix="grantbridge-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name.replace(os.sep, '/')}/test.db"
os.environ["AUTH_SECRET"] = "test-signing-secret-for-authentication-tests"
os.environ["UPLOAD_DIR"] = f"{_tmp.name}/uploads"
os.environ["SWITCH_BASE_URL"] = ""
os.environ["SWITCH_AGENT_ID"] = ""
os.environ["SWITCH_AGENT_API_KEY"] = ""

from fastapi.testclient import TestClient
import app.models  # Ensure all mapped tables are registered before test schema creation.
from app.database import Base, engine, SessionLocal
Base.metadata.create_all(bind=engine)
from app.main import app
from app.models import Application
from app.switch_events import persist_event
from app.switch_adapter import SwitchAdapter
from app.workflow_router import route_agent_reply
import pytest

client = TestClient(app)
AUTH = {}


@pytest.fixture(autouse=True)
def close_test_engine():
    yield
    engine.dispose()
    _tmp.cleanup()


def test_sample_application_review_and_human_approval(monkeypatch):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/organizations").status_code == 401

    registered = client.post("/v1/auth/register", json={"email": "owner@grantbridge.test", "display_name": "Demo Owner", "password": "CorrectHorseBatteryStaple!9"})
    assert registered.status_code == 200
    AUTH["Authorization"] = f"Bearer {registered.json()['access_token']}"
    assert client.get("/v1/profile", headers=AUTH).json()["email"] == "owner@grantbridge.test"
    renamed = client.patch("/v1/profile", headers=AUTH, json={"display_name": "Demo Owner Updated"})
    assert renamed.status_code == 200 and renamed.json()["display_name"] == "Demo Owner Updated"

    organization = client.post("/v1/organizations", headers=AUTH, json={
        "name": "Demo Rural Learning Network", "country": "India",
        "mission": "Expand access to learning resources in rural communities.",
        "registration_number": ""
    })
    assert organization.status_code == 200
    org = organization.json()

    grant = client.post("/v1/demo/seed", headers=AUTH)
    assert grant.status_code == 200 and grant.json()["is_sample"] is True
    rejected_import = client.post("/v1/grants/import", headers=AUTH, json={"title": "Copied grant listing", "funder": "Example Fund", "amount": "$10,000", "sector": "education", "source_url": "http://example.org/grant"})
    assert rejected_import.status_code == 422
    imported = client.post("/v1/grants/import", headers=AUTH, json={"title": "Community Learning Fund", "funder": "Example Foundation", "amount": "$10,000", "sector": "education", "source_url": "https://example.org/grant", "requirements": ["Nonprofit registration"]})
    assert imported.status_code == 200 and imported.json()["source_status"] == "user_provided_unverified"
    application = client.post(f"/v1/organizations/{org['id']}/applications?grant_id={grant.json()['id']}", headers=AUTH)
    assert application.status_code == 200
    app_id = application.json()["id"]
    assert application.json()["switch_status"] == "unavailable"

    detail = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert detail["sections"]
    assert detail["issues"] and detail["issues"][0]["resolved"] is False

    upload = client.post(f"/v1/applications/{app_id}/documents", headers=AUTH, data={"category": "registration_certificate"},
                         files={"file": ("registration.txt", b"Registration certificate: DEMO-123", "text/plain")})
    assert upload.status_code == 200 and upload.json()["provenance"] == "human_provided"
    assert upload.json()["text_extracted"] is True
    assert upload.json()["switch_handoff"] is False
    listed = client.get(f"/v1/organizations/{org['id']}/documents", headers=AUTH)
    assert listed.status_code == 200 and listed.json()[0]["category"] == "registration_certificate"
    downloaded = client.get(f"/v1/documents/{upload.json()['id']}/download", headers=AUTH)
    assert downloaded.status_code == 200 and b"DEMO-123" in downloaded.content

    with SessionLocal() as db:
        app_row = db.get(Application, app_id)
        app_row.switch_room_id = "room-demo"
        app_row.switch_status = "connected"
        app_row.current_stage = "scout"
        db.commit()

    async def fake_handoff(self, room_id, recipient, content):
        assert room_id == "room-demo"
        return {"event_id": "mock-switch-event", "target_statuses": {recipient: "live"}}

    monkeypatch.setattr(SwitchAdapter, "handoff", fake_handoff)
    asyncio.run(route_agent_reply(app_id, "grant-scout", "Scout found an education opportunity."))
    current = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert current["current_stage"] == "eligibility"
    asyncio.run(route_agent_reply(app_id, "eligibility-analyst", '{"status":"potentially eligible","evidence":["DEMO-123"]}'))
    current = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert current["current_stage"] == "budget"
    assert current["eligibility_assessments"][-1]["status"] == "potentially_eligible"
    assert current["eligibility_assessments"][-1]["evidence"] == ["DEMO-123"]
    asyncio.run(route_agent_reply(app_id, "budget-analyst", '{"eligible_categories":[{"category":"Equipment","description":"Devices, subject to funder caps."}]}'))
    current = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert current["current_stage"] == "awaiting_budget"

    blocked = client.post(f"/v1/applications/{app_id}/approve", headers=AUTH, json={"approved": True})
    assert blocked.status_code == 409

    issue = detail["issues"][0]
    premature = client.post(f"/v1/applications/{app_id}/issues/{issue['id']}/resolve", headers=AUTH,
                            json={"content": "reviewed"})
    assert premature.status_code == 409
    handoff = client.post(f"/v1/applications/{app_id}/issues/{issue['id']}/handoff", headers=AUTH)
    assert handoff.status_code == 200 and handoff.json()["switch_handoff"] is True
    resolved = client.post(f"/v1/applications/{app_id}/issues/{issue['id']}/resolve", headers=AUTH,
                           json={"content": "Human reviewed the revised content."})
    assert resolved.status_code == 200 and resolved.json()["resolved"] is True

    budget_blocked = client.post(f"/v1/applications/{app_id}/approve", headers=AUTH, json={"approved": True})
    assert budget_blocked.status_code == 409
    for item in detail["budget_items"]:
        saved = client.put(f"/v1/applications/{app_id}/budget-items/{item['id']}", headers=AUTH,
                           json={"amount_cents": 125000, "currency": "usd", "approved": True})
        assert saved.status_code == 200 and saved.json()["approval_status"] == "human_approved"

    with SessionLocal() as db:
        db.get(Application, app_id).current_stage = "writing"
        db.commit()
    asyncio.run(route_agent_reply(app_id, "grant-writer", '{"sections":[{"title":"Executive summary","content":"A draft using human-provided evidence."}]}'))
    current = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert current["current_stage"] == "compliance"
    assert next(s for s in current["sections"] if s["title"] == "Executive summary")["provenance"] == "ai_generated_switch"
    asyncio.run(route_agent_reply(app_id, "compliance-reviewer", '{"overall_readiness":"needs_changes","issues":[{"issue":"Outcome measures are not sourced.","severity":"high","requirement":"Support outcomes with evidence.","evidence":"No source is included.","suggested_correction":"Add a verified source.","assigned_to":"Grant Writer"}]}'))
    current = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    for issue in current["issues"]:
        if issue["resolved"]:
            continue
        handoff = client.post(f"/v1/applications/{app_id}/issues/{issue['id']}/handoff", headers=AUTH)
        assert handoff.status_code == 200 and handoff.json()["switch_handoff"] is True
        resolved = client.post(f"/v1/applications/{app_id}/issues/{issue['id']}/resolve", headers=AUTH,
                               json={"content": "Human reviewed and corrected the issue."})
        assert resolved.status_code == 200 and resolved.json()["resolved"] is True

    section = detail["sections"][0]
    edited = client.put(f"/v1/applications/{app_id}/sections/{section['id']}", headers=AUTH,
                        json={"content": "Human verified executive summary."})
    assert edited.status_code == 200 and edited.json()["provenance"] == "human_edited"

    approved = client.post(f"/v1/applications/{app_id}/approve", headers=AUTH,
                           json={"approved": True, "note": "Reviewed by the organization."})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    approved_detail = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    approved_section = approved_detail["sections"][0]
    edited_after_approval = client.put(f"/v1/applications/{app_id}/sections/{approved_section['id']}", headers=AUTH,
        json={"content": "A post-approval correction must invalidate approval."})
    assert edited_after_approval.status_code == 200
    changed = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert changed["status"] == "under_review" and changed["approvals"][-1]["superseded_at"] is not None
    reapproved = client.post(f"/v1/applications/{app_id}/approve", headers=AUTH, json={"approved": True, "note": "Reviewed the corrected version."})
    assert reapproved.status_code == 200
    submitted = client.put(f"/v1/applications/{app_id}/tracking", headers=AUTH, json={"status": "submitted", "reporting_requirements": ["Annual outcomes report"]})
    assert submitted.status_code == 200 and submitted.json()["submitted_at"]
    awarded = client.put(f"/v1/applications/{app_id}/tracking", headers=AUTH, json={"status": "awarded", "award_amount_cents": 2500000, "reporting_requirements": ["Quarterly progress update"]})
    assert awarded.status_code == 200 and awarded.json()["status"] == "awarded"
    reminder = client.post("/v1/notifications/reminders", headers=AUTH,
        json={"organization_id": org["id"], "application_id": app_id, "title": "Prepare impact update", "body": "Collect project metrics."})
    assert reminder.status_code == 200
    assert any(n["id"] == reminder.json()["id"] for n in client.get("/v1/notifications", headers=AUTH).json())

    final = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    assert any(e["event_type"] == "application_approved" and e["source"] == "human" for e in final["events"])

    frame = {"event": "message", "id": 73, "data": {"type": "message", "room_id": "room-demo",
        "payload": {"sender_name": "grant-writer", "body": "Revised the unsupported claim and cited the source."}}}
    persist_event(frame)
    persist_event(frame)
    final = client.get(f"/v1/applications/{app_id}", headers=AUTH).json()
    received = [e for e in final["events"] if e["event_type"] == "switch_message"]
    assert len(received) == 1 and received[0]["source"] == "switch"

    outsider = client.post("/v1/auth/register", json={"email": "outsider@grantbridge.test", "display_name": "Outside User", "password": "AnotherSecurePassword!8"})
    outsider_auth = {"Authorization": f"Bearer {outsider.json()['access_token']}"}
    assert client.get(f"/v1/organizations/{org['id']}/applications", headers=outsider_auth).status_code == 404
    assert client.get(f"/v1/documents/{upload.json()['id']}/download", headers=outsider_auth).status_code == 404
    added = client.post(f"/v1/organizations/{org['id']}/members", headers=AUTH, json={"email": "outsider@grantbridge.test", "role": "viewer"})
    assert added.status_code == 200
    changed_role = client.patch(f"/v1/organizations/{org['id']}/members/{added.json()['id']}", headers=AUTH, json={"role": "member"})
    assert changed_role.status_code == 200 and changed_role.json()["role"] == "member"
    changed_role = client.patch(f"/v1/organizations/{org['id']}/members/{added.json()['id']}", headers=AUTH, json={"role": "viewer"})
    assert changed_role.status_code == 200 and changed_role.json()["role"] == "viewer"
    assert client.get(f"/v1/organizations/{org['id']}/applications", headers=outsider_auth).status_code == 200
    assert client.put(f"/v1/applications/{app_id}/sections/{approved_section['id']}", headers=outsider_auth,
        json={"content": "Viewer should not edit."}).status_code == 403
    assert client.delete(f"/v1/organizations/{org['id']}/members/{added.json()['id']}", headers=AUTH).status_code == 200

    logged_out = client.post("/v1/auth/logout", headers=AUTH)
    assert logged_out.status_code == 200
    assert client.get("/v1/profile", headers=AUTH).status_code == 401
