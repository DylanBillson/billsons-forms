import threading
from app.services import email


async def test_sync_smtp_runs_off_event_loop(monkeypatch):
    called = {}
    def fake(**kwargs): called["thread"] = threading.get_ident()
    monkeypatch.setattr(email, "_send_submission_email", fake)
    main_thread = threading.get_ident()
    await email.send_submission_email(subject="x")
    assert called["thread"] != main_thread
