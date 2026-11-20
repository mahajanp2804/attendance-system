"""
Access-control tests for the API against a real Postgres (needs TEST_DATABASE_URL).

Demo data from db/seed.py: Priya teaches CS301 and CS302 (students 01–10 enrolled),
Rajesh teaches EC301 (nobody enrolled), and there is one admin.
"""

import os

from conftest import run_sql


def open_session(api, day, who="priya", code="CS301"):
    r = api.client.post("/api/attendance/sessions",
                        json={"slot_id": api.slots[code], "date": day}, headers=api.h(who))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def records(api, session_id, who="priya"):
    return api.client.get(f"/api/attendance/sessions/{session_id}/records", headers=api.h(who))


# ── Class sessions ────────────────────────────────────────────────────────────

def test_only_the_class_professor_can_open_a_session(api):
    r = api.client.post("/api/attendance/sessions",
                        json={"slot_id": api.slots["CS301"], "date": "2026-11-02"}, headers=api.h("rajesh"))
    assert r.status_code == 403
    open_session(api, "2026-11-02")                          # Priya: her own class
    open_session(api, "2026-11-02", who="admin", code="EC301")   # admin: any class


def test_only_the_class_professor_can_close_a_session(api):
    sid = open_session(api, "2026-11-03")
    assert api.client.patch(f"/api/attendance/sessions/{sid}/close", headers=api.h("rajesh")).status_code == 403
    assert api.client.patch(f"/api/attendance/sessions/{sid}/close", headers=api.h("priya")).status_code == 200


def test_students_only_see_their_own_record(api):
    sid = open_session(api, "2026-11-04")
    assert len(records(api, sid).json()) == 10
    own = records(api, sid, "s01").json()
    assert [r["roll_number"] for r in own] == ["CS2024001"]
    assert records(api, sid, "rajesh").status_code == 403


def test_only_the_class_professor_can_override_a_record(api):
    sid = open_session(api, "2026-11-05")
    record_id = records(api, sid).json()[0]["id"]
    body = {"status": "present", "reason": "came late"}
    assert api.client.patch(f"/api/attendance/records/{record_id}", json=body, headers=api.h("rajesh")).status_code == 403
    assert api.client.patch(f"/api/attendance/records/{record_id}", json=body, headers=api.h("priya")).status_code == 200


# ── Face snapshots ────────────────────────────────────────────────────────────

def test_face_snapshots_are_private(api):
    from config import settings
    sid = open_session(api, "2026-11-06")
    with_snap, without_snap = (r["id"] for r in records(api, sid).json()[:2])

    path = os.path.join(settings.SNAPSHOTS_DIR, sid, "face.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\xff\xd8 fake jpeg")
    run_sql("UPDATE attendance_records SET face_snapshot = :p WHERE id = :i", p=path, i=with_snap)

    assert api.client.get(f"/snapshots/{sid}/face.jpg").status_code == 404   # no public route
    url = f"/api/attendance/records/{with_snap}/snapshot"
    assert api.client.get(url).status_code == 401
    assert api.client.get(url, headers=api.h("s01")).status_code == 403
    assert api.client.get(url, headers=api.h("rajesh")).status_code == 403
    r = api.client.get(url, headers=api.h("priya"))
    assert r.status_code == 200 and r.content.startswith(b"\xff\xd8")

    other = f"/api/attendance/records/{without_snap}/snapshot"
    assert api.client.get(other, headers=api.h("priya")).status_code == 404
    run_sql("UPDATE attendance_records SET face_snapshot = '/etc/hosts' WHERE id = :i", i=without_snap)
    assert api.client.get(other, headers=api.h("priya")).status_code == 404   # outside snapshots dir


# ── Face index and scanning ───────────────────────────────────────────────────

def test_face_index_endpoints_need_a_professor(api):
    assert api.client.get("/api/recognition/index-status").status_code == 401
    assert api.client.post("/api/recognition/reload-index").status_code == 401
    assert api.client.post("/api/recognition/reload-index", headers=api.h("s01")).status_code == 403
    assert api.client.post("/api/recognition/reload-index", headers=api.h("priya")).status_code == 200


def first_ws_message(api, session_id, token):
    with api.client.websocket_connect(f"/api/recognition/ws/{session_id}") as ws:
        ws.send_text(token)
        return ws.receive_json()


def test_only_the_class_professor_can_scan(api):
    sid = open_session(api, "2026-11-07")
    api.h("rajesh"); api.h("priya")   # make sure both are logged in
    assert first_ws_message(api, sid, api.tokens["rajesh"]) == {"type": "error", "message": "You don't teach this class"}
    assert first_ws_message(api, sid, "not-a-token") == {"type": "error", "message": "Auth failed"}
    msg = first_ws_message(api, sid, api.tokens["priya"])
    assert msg["type"] == "connected" and msg["total_enrolled"] == 10
