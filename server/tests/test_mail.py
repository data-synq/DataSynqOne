"""Der Mail-Kern ohne Netzwerk und ohne Datenbank.

Der wichtigste Test ist test_send_without_configuration_returns_false: der ganze
Rest der Anwendung verlaesst sich darauf, dass ein fehlender oder kaputter
Mailserver nichts kaputt macht, sondern nur False meldet.
"""

from dataclasses import dataclass

import pytest

from app.config import settings
from app.mail import client, messages


@dataclass
class _Deadline:
    """Nachbau von dashboard_models.Deadline, so weit die Mail sie braucht."""

    document_id: int
    title: str
    correspondent_name: str | None
    object_name: str | None
    due_date: str
    days_until: int


@pytest.fixture
def smtp_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "smtp_from_email", "one@example.org")
    monkeypatch.setattr(settings, "smtp_from_name", "DataSynq One")


@pytest.fixture
def captured(monkeypatch):
    """Faengt den Aufruf von aiosmtplib.send ab, statt zu verschicken."""
    calls: list[dict] = []

    async def fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(client.aiosmtplib, "send", fake_send)
    return calls


class TestConfiguration:
    def test_disabled_without_host(self, monkeypatch):
        monkeypatch.setattr(settings, "smtp_host", "")
        monkeypatch.setattr(settings, "smtp_from_email", "one@example.org")
        assert not settings.mail_enabled

    def test_disabled_without_sender(self, monkeypatch):
        # Ohne Absender nimmt kaum ein Server die Nachricht an — lieber gar nicht
        # erst versuchen, als bei jedem Versand in einen Fehler zu laufen.
        monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
        monkeypatch.setattr(settings, "smtp_from_email", "")
        assert not settings.mail_enabled


class TestSending:
    async def test_send_without_configuration_returns_false(self, monkeypatch, captured):
        monkeypatch.setattr(settings, "smtp_host", "")
        assert await client.send(["a@example.org"], "Betreff", "Text") is False
        assert captured == [], "ohne Konfiguration darf nichts an SMTP gehen"

    async def test_send_without_recipients_returns_false(self, smtp_configured, captured):
        assert await client.send([], "Betreff", "Text") is False
        assert captured == []

    async def test_failure_is_swallowed(self, smtp_configured, monkeypatch):
        async def boom(message, **kwargs):
            raise ConnectionRefusedError("kein Mailserver")

        monkeypatch.setattr(client.aiosmtplib, "send", boom)
        # Kein raise: ein nicht erreichbarer Mailserver darf einen Request nicht
        # scheitern lassen, der fachlich schon durch ist.
        assert await client.send(["a@example.org"], "Betreff", "Text") is False

    async def test_successful_send_reports_true(self, smtp_configured, captured):
        assert await client.send(["a@example.org"], "Betreff", "Text") is True
        assert len(captured) == 1

    async def test_invalid_header_is_reported_as_failed_delivery(self, smtp_configured, captured):
        assert await client.send(["a@example.org"], "Betreff\nBcc: victim@example.org", "Text") is False
        assert captured == []

    @pytest.mark.parametrize(
        ("security", "start_tls", "use_tls"),
        [(client.STARTTLS, True, False), (client.IMPLICIT_TLS, False, True), (client.NO_TLS, False, False)],
    )
    async def test_tls_mode(self, smtp_configured, captured, monkeypatch, security, start_tls, use_tls):
        monkeypatch.setattr(settings, "smtp_security", security)
        await client.send(["a@example.org"], "Betreff", "Text")
        assert captured[0]["start_tls"] is start_tls
        assert captured[0]["use_tls"] is use_tls

    async def test_empty_credentials_become_none(self, smtp_configured, captured, monkeypatch):
        # aiosmtplib versucht bei einem leeren String ein AUTH mit leerem Nutzer;
        # ein offener Relay lehnt genau das ab.
        monkeypatch.setattr(settings, "smtp_username", "")
        monkeypatch.setattr(settings, "smtp_password", "")
        await client.send(["a@example.org"], "Betreff", "Text")
        assert captured[0]["username"] is None
        assert captured[0]["password"] is None


class TestMessageBuilding:
    def test_text_only_message_has_no_html_part(self, smtp_configured):
        message = client.build_message(["a@example.org"], "Betreff", "Nur Text")
        assert not message.is_multipart()

    def test_html_message_keeps_a_text_part(self, smtp_configured):
        message = client.build_message(["a@example.org"], "Betreff", "Text", "<p>HTML</p>")
        subtypes = [p.get_content_subtype() for p in message.iter_parts()]
        assert subtypes == ["plain", "html"]

    def test_from_header_carries_the_display_name(self, smtp_configured):
        message = client.build_message(["a@example.org"], "Betreff", "Text")
        assert "DataSynq One" in message["From"]
        assert "one@example.org" in message["From"]

    def test_reply_to_is_set_when_given(self, smtp_configured):
        message = client.build_message(["a@example.org"], "B", "T", reply_to="rueck@example.org")
        assert message["Reply-To"] == "rueck@example.org"


class TestDigestText:
    def _deadlines(self):
        overdue = [_Deadline(1, "Rechnung Stadtwerke", "Stadtwerke", "Musterhof", "2026-08-01", -6)]
        upcoming = [
            _Deadline(2, "Wartung Heizung", None, "Musterhof", "2026-08-07", 0),
            _Deadline(3, "Kündigung prüfen", "Mieter", None, "2026-08-15", 8),
        ]
        return overdue, upcoming

    def test_subject_names_both_groups(self):
        overdue, upcoming = self._deadlines()
        subject, _, _ = messages.deadline_digest(overdue, upcoming)
        assert "1 überschrittene Frist" in subject
        assert "2 anstehend" in subject

    def test_subject_without_overdue(self):
        _, upcoming = self._deadlines()
        subject, _, _ = messages.deadline_digest([], upcoming)
        assert "überschritten" not in subject.lower()

    def test_text_lists_every_deadline(self):
        overdue, upcoming = self._deadlines()
        _, text, _ = messages.deadline_digest(overdue, upcoming)
        for d in overdue + upcoming:
            assert d.title in text
            assert d.due_date in text

    def test_relative_wording(self):
        assert messages._relative(0) == "heute fällig"
        assert messages._relative(1) == "morgen fällig"
        assert messages._relative(-1) == "seit gestern überfällig"
        assert messages._relative(-6) == "seit 6 Tagen überfällig"
        assert messages._relative(8) == "in 8 Tagen fällig"

    def test_empty_group_is_left_out(self):
        _, upcoming = self._deadlines()
        _, text, html = messages.deadline_digest([], upcoming)
        assert "Überschritten" not in text
        assert "Überschritten" not in html


class TestInvitationText:
    def test_link_appears_in_both_parts(self):
        link = "https://one.example.org/einladung/abc123"
        _, text, html = messages.invitation("Nina Neu", link)
        assert link in text
        assert link in html

    def test_name_is_escaped_in_html(self):
        # Der Anzeigename kommt aus einem Formular und landet in HTML.
        _, _, html = messages.invitation("<script>alert(1)</script>", "https://x/y")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_agent_message_escapes_the_body(self):
        text, html = messages.agent_message("Guten Tag <b>Herr Meier</b>")
        assert text == "Guten Tag <b>Herr Meier</b>"
        assert "<b>" not in html
