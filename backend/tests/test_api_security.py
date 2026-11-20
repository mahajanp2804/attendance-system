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


# ── Export and low attendance ─────────────────────────────────────────────────

def export_rows(api, who, **params):
    r = api.client.get("/api/attendance/export", params=params, headers=api.h(who))
    return r.status_code, [line for line in r.text.splitlines()[1:] if line]


def test_professors_only_export_their_own_classes(api):
    sid = open_session(api, "2026-11-09")
    api.client.patch(f"/api/attendance/sessions/{sid}/close", headers=api.h("priya"))

    status, rows = export_rows(api, "rajesh")
    assert status == 200 and not any("CS301" in row for row in rows)
    _, priya_rows = export_rows(api, "priya")
    _, admin_rows = export_rows(api, "admin")
    assert sum("CS301" in row for row in priya_rows) >= 10
    assert len(admin_rows) == len(priya_rows)   # only Priya's classes have students
    status, _ = export_rows(api, "rajesh", subject_id=api.subjects["CS301"])
    assert status == 403


def test_low_attendance_only_covers_own_classes(api):
    sid = open_session(api, "2026-11-10")
    api.client.patch(f"/api/attendance/sessions/{sid}/close", headers=api.h("priya"))   # everyone absent

    low = lambda who: api.client.get("/api/attendance/low-attendance", headers=api.h(who)).json()
    assert low("rajesh") == []
    assert len(low("priya")) > 0
    assert len(low("admin")) == len(low("priya"))


# ── Subjects and timetable slots ──────────────────────────────────────────────

def test_only_the_subject_professor_can_edit_or_delete_it(api):
    url = f"/api/subjects/{api.subjects['CS301']}"
    assert api.client.patch(url, json={"name": "Hacked"}, headers=api.h("rajesh")).status_code == 403
    assert api.client.delete(url, headers=api.h("rajesh")).status_code == 403
    assert api.client.patch(url, json={"name": "Operating Systems"}, headers=api.h("priya")).status_code == 200


def test_only_admins_assign_subjects_to_someone_else(api):
    priya_id = api.client.get("/api/auth/me", headers=api.h("priya")).json()["id"]
    sem_id = next(s["id"] for s in api.client.get("/api/semesters/", headers=api.h("rajesh")).json() if s["is_active"])

    r = api.client.post("/api/subjects/", json={"name": "Fake", "code": "FK1", "semester_id": sem_id,
                                                "professor_id": priya_id}, headers=api.h("rajesh"))
    assert r.status_code == 403
    r = api.client.post("/api/subjects/", json={"name": "Signals", "code": "EC399", "semester_id": sem_id},
                        headers=api.h("rajesh"))
    assert r.status_code == 201
    url = f"/api/subjects/{r.json()['id']}"
    assert api.client.patch(url, json={"professor_id": priya_id}, headers=api.h("rajesh")).status_code == 403
    r = api.client.patch(url, json={"professor_id": priya_id}, headers=api.h("admin"))
    assert r.status_code == 200 and r.json()["professor_id"] == priya_id
    assert api.client.delete(url, headers=api.h("priya")).status_code == 204   # now hers


def test_professors_only_list_their_own_subjects(api):
    codes = lambda who: {s["code"] for s in api.client.get("/api/subjects/", headers=api.h(who)).json()}
    assert codes("rajesh") == {"EC301"}
    assert {"CS301", "CS302", "EC301"} <= codes("admin")


def test_only_the_subject_professor_can_manage_its_slots(api):
    slot = {"subject_id": api.subjects["CS301"], "day": "saturday",
            "start_time": "10:00", "end_time": "11:00", "room": "R1"}
    assert api.client.post("/api/timetable/slots", json=slot, headers=api.h("rajesh")).status_code == 403
    r = api.client.post("/api/timetable/slots", json=slot, headers=api.h("priya"))
    assert r.status_code == 201
    url = f"/api/timetable/slots/{r.json()['id']}"
    assert api.client.patch(url, json={"room": "R2"}, headers=api.h("rajesh")).status_code == 403
    assert api.client.delete(url, headers=api.h("rajesh")).status_code == 403
    r = api.client.patch(url, json={"room": "R2"}, headers=api.h("priya"))
    assert r.status_code == 200 and r.json()["room"] == "R2"
    assert api.client.delete(url, headers=api.h("priya")).status_code == 204


# ── Enrollment ────────────────────────────────────────────────────────────────

def test_professors_only_enroll_into_their_own_classes(api):
    s01 = api.student_ids["student01@college.edu"]
    os_id, ec_id = api.subjects["CS301"], api.subjects["EC301"]

    # One class that's his and one that isn't → refused, and nothing half-applied
    r = api.client.post(f"/api/students/{s01}/enroll", json={"subject_ids": [ec_id, os_id]}, headers=api.h("rajesh"))
    assert r.status_code == 403
    assert api.client.delete(f"/api/students/{s01}/enroll/{os_id}", headers=api.h("rajesh")).status_code == 403

    r = api.client.post(f"/api/students/{s01}/enroll", json={"subject_ids": [ec_id]}, headers=api.h("rajesh"))
    assert r.status_code == 201 and r.json()["enrolled"] == [ec_id]
    assert api.client.delete(f"/api/students/{s01}/enroll/{ec_id}", headers=api.h("rajesh")).status_code == 204


# ── Semesters ─────────────────────────────────────────────────────────────────

def test_only_admins_manage_semesters(api):
    sem_id = next(s["id"] for s in api.client.get("/api/semesters/", headers=api.h("s01")).json() if s["is_active"])
    new = {"name": "Sem 6", "start_date": "2025-01-01", "end_date": "2025-05-31"}
    assert api.client.post("/api/semesters/", json=new, headers=api.h("priya")).status_code == 403
    assert api.client.patch(f"/api/semesters/{sem_id}/activate", headers=api.h("priya")).status_code == 403
    assert api.client.post("/api/semesters/", json=new, headers=api.h("admin")).status_code == 201
    assert api.client.patch(f"/api/semesters/{sem_id}/activate", headers=api.h("admin")).status_code == 200
