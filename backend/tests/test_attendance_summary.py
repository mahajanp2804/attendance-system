"""A student's per-subject attendance summary (needs TEST_DATABASE_URL)."""


def test_subject_with_no_classes_yet_is_not_low_attendance(api):
    summary = api.client.get("/api/attendance/summary", headers=api.h("s01")).json()
    not_started = [s for s in summary if s["total_classes"] == 0]
    assert not_started, "expected a subject with no completed classes in the demo data"
    assert all(s["is_low"] is False for s in not_started)
