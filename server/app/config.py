import ipaddress
import os
import re
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import unquote, urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production", "test"]
SmtpSecurity = Literal["starttls", "tls", "none"]
ImapSecurity = Literal["ssl", "starttls", "none"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COOKIE_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_WEAK_VALUES = {"brain", "postgres", "password", "secret", "change-me", "change-me-too", "changeme"}


def reveal_secret(value: SecretStr | str) -> str:
    """Return a secret for an outbound client; tests may monkeypatch plain strings."""
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(value)) and "\r" not in value and "\n" not in value


def _is_non_public_hostname(hostname: str | None) -> bool:
    if not hostname:
        return True
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith((".localhost", ".local", ".lan", ".internal")):
        return True
    try:
        return not ipaddress.ip_address(normalized).is_global
    except ValueError:
        return False


def _http_url_error(name: str, value: str, *, production: bool = False) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return f"{name} muss eine vollständige HTTP(S)-URL sein"
    if parsed.username or parsed.password:
        return f"{name} darf keine Zugangsdaten enthalten"
    if production and (parsed.scheme != "https" or _is_non_public_hostname(parsed.hostname)):
        return f"{name} muss in Produktion eine öffentliche HTTPS-URL sein"
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=False,
        env_ignore_empty=True,
        validate_default=True,
        hide_input_in_errors=True,
        extra="ignore",
    )

    environment: Environment

    paperless_base_url: str = "http://paperless:8000"
    paperless_api_token: SecretStr = SecretStr("")

    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    admin_client_cidrs: list[str] = Field(default_factory=list)
    max_request_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)

    database_url: SecretStr = SecretStr("postgresql://brain:brain@vectordb:5432/brain")
    runtime_database_url: SecretStr = SecretStr("")
    db_pool_min_size: int = Field(default=1, ge=1, le=20)
    db_pool_max_size: int = Field(default=10, ge=1, le=50)
    db_command_timeout_seconds: int = Field(default=30, ge=1, le=300)
    app_timezone: str = "Europe/Berlin"
    embedding_model: str = "text-embedding-3-small"

    # Session cookie. `secure` must be false for `make dev`, which serves the app
    # over plain http://localhost — a Secure cookie would never be stored there.
    session_cookie_name: str = Field(default="dsq_session", min_length=1, max_length=128)
    session_cookie_secure: bool = True
    session_ttl_hours: int = Field(default=12, ge=1, le=24 * 30)
    session_absolute_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    mfa_encryption_key: SecretStr = SecretStr("")

    # Bootstrap admin, applied only while the users table is still empty. Without
    # both values set, no account is created — there is no default password.
    admin_email: str = ""
    admin_password: SecretStr = SecretStr("")

    # Outgoing mail. An empty smtp_host turns sending off entirely: the app stays
    # fully usable, sends nothing and says so instead of failing requests.
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: SmtpSecurity = "starttls"
    smtp_from_email: str = ""
    smtp_from_name: str = "DataSynq One"
    smtp_reply_to: str = ""
    smtp_timeout_seconds: int = Field(default=15, ge=1, le=300)
    allow_insecure_mail_transport: bool = False

    # Invitation links have to be absolute, and the backend cannot know its own
    # public URL. Set this per deployment or every link points at localhost.
    app_base_url: str = "http://localhost:5173"
    invitation_ttl_hours: int = Field(default=72, ge=1, le=24 * 30)

    deadline_digest_enabled: bool = True
    deadline_digest_hour: int = Field(default=7, ge=0, le=23)
    deadline_digest_days_ahead: int = Field(default=14, ge=0, le=365)
    # Empty means every active admin and editor.
    deadline_digest_recipients: list[str] = Field(default_factory=list)

    # Incoming mail via Paperless's own mail fetcher. An empty mail_imap_host
    # turns the seed off entirely — same rule as outgoing mail: the app must be
    # fully usable without it.
    mail_imap_host: str = ""
    mail_imap_port: int = Field(default=993, ge=1, le=65535)
    mail_imap_security: ImapSecurity = "ssl"
    mail_imap_username: str = ""
    mail_imap_password: SecretStr = SecretStr("")
    mail_imap_folder: str = "INBOX"
    # Tags applied to every document that arrives through this rule.
    mail_rule_tags: list[str] = Field(default_factory=lambda: ["correspondence"])

    # Anliegen-Aufnahme: verarbeitet die von der Paperless-Mailregel abgelegten
    # 'correspondence'-Dokumente weiter (Freigabe-Gate, Klassifikation, Fallanlage).
    mail_intake_enabled: bool = True
    mail_ingress_prevalidated: bool = False
    mail_intake_poll_seconds: int = Field(default=300, ge=10, le=86400)
    mail_intake_max_chars: int = Field(default=8000, ge=100, le=100000)
    mail_whitelist_trust_days: int = Field(default=21, ge=1, le=365)

    @model_validator(mode="after")
    def validate_deployment(self):
        errors: list[str] = []
        smtp_password = reveal_secret(self.smtp_password)
        imap_password = reveal_secret(self.mail_imap_password)

        if not _COOKIE_NAME_RE.fullmatch(self.session_cookie_name):
            errors.append("SESSION_COOKIE_NAME enthält unzulässige Zeichen")
        if self.session_absolute_ttl_hours < self.session_ttl_hours:
            errors.append("SESSION_ABSOLUTE_TTL_HOURS muss mindestens SESSION_TTL_HOURS entsprechen")
        if self.db_pool_max_size < self.db_pool_min_size:
            errors.append("DB_POOL_MAX_SIZE muss mindestens DB_POOL_MIN_SIZE entsprechen")
        try:
            ZoneInfo(self.app_timezone)
        except ZoneInfoNotFoundError:
            errors.append("APP_TIMEZONE ist keine bekannte IANA-Zeitzone")

        if self.smtp_from_name and ("\r" in self.smtp_from_name or "\n" in self.smtp_from_name):
            errors.append("SMTP_FROM_NAME darf keine Zeilenumbrüche enthalten")
        if self.smtp_from_email and not is_valid_email(self.smtp_from_email):
            errors.append("SMTP_FROM_EMAIL ist keine gültige E-Mail-Adresse")
        if self.smtp_reply_to and not is_valid_email(self.smtp_reply_to):
            errors.append("SMTP_REPLY_TO ist keine gültige E-Mail-Adresse")
        if self.smtp_host:
            if not self.smtp_from_email:
                errors.append("SMTP_FROM_EMAIL ist bei gesetztem SMTP_HOST erforderlich")
            if bool(self.smtp_username) != bool(smtp_password):
                errors.append("SMTP_USERNAME und SMTP_PASSWORD müssen gemeinsam gesetzt werden")
        if self.mail_imap_host and not (self.mail_imap_username and imap_password):
            errors.append("MAIL_IMAP_USERNAME und MAIL_IMAP_PASSWORD sind bei gesetztem MAIL_IMAP_HOST erforderlich")

        paperless_url_error = _http_url_error("PAPERLESS_BASE_URL", self.paperless_base_url)
        if paperless_url_error:
            errors.append(paperless_url_error)

        app_url_error = _http_url_error(
            "APP_BASE_URL", self.app_base_url, production=self.environment == "production"
        )
        if app_url_error:
            errors.append(app_url_error)

        if self.environment == "production":
            paperless_token = reveal_secret(self.paperless_api_token)
            openai_key = reveal_secret(self.openai_api_key)
            if not paperless_token:
                errors.append("PAPERLESS_API_TOKEN ist in Produktion erforderlich")
            elif paperless_token.lower() in _WEAK_VALUES:
                errors.append("PAPERLESS_API_TOKEN verwendet einen bekannten Platzhalter")
            if not openai_key:
                errors.append("OPENAI_API_KEY ist in Produktion erforderlich")
            elif openai_key.lower() in _WEAK_VALUES:
                errors.append("OPENAI_API_KEY verwendet einen bekannten Platzhalter")
            if not self.session_cookie_secure:
                errors.append("SESSION_COOKIE_SECURE muss in Produktion true sein")
            if not self.session_cookie_name.startswith("__Host-"):
                errors.append("SESSION_COOKIE_NAME muss in Produktion mit __Host- beginnen")
            mfa_key = reveal_secret(self.mfa_encryption_key)
            try:
                valid_mfa_key = (
                    len(b64decode(mfa_key.encode("ascii"), altchars=b"-_", validate=True)) == 32
                )
            except (Base64Error, ValueError, UnicodeEncodeError):
                valid_mfa_key = False
            if not valid_mfa_key:
                errors.append("MFA_ENCRYPTION_KEY muss ein gültiger Fernet-Schlüssel sein")

            for origin in self.cors_origins:
                if origin == "*":
                    errors.append("CORS_ORIGINS darf in Produktion keinen Wildcard-Origin enthalten")
                    continue
                origin_error = _http_url_error("CORS_ORIGINS", origin, production=True)
                parsed = urlsplit(origin)
                if origin_error or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                    errors.append(origin_error or "CORS_ORIGINS darf nur Origins ohne Pfad enthalten")

            if not self.trusted_proxy_cidrs:
                errors.append("TRUSTED_PROXY_CIDRS ist in Produktion erforderlich")
            if not self.admin_client_cidrs:
                errors.append("ADMIN_CLIENT_CIDRS ist in Produktion erforderlich")
            for field_name, cidrs in (
                ("TRUSTED_PROXY_CIDRS", self.trusted_proxy_cidrs),
                ("ADMIN_CLIENT_CIDRS", self.admin_client_cidrs),
            ):
                if len(cidrs) > 8:
                    errors.append(f"{field_name} darf höchstens acht Netzwerke enthalten")
                for cidr in cidrs:
                    try:
                        network = ipaddress.ip_network(cidr, strict=False)
                    except ValueError:
                        errors.append(f"{field_name} enthält ein ungültiges Netzwerk")
                        continue
                    if network.prefixlen == 0:
                        errors.append(f"{field_name} darf nicht das gesamte Internet umfassen")
                    minimum_prefix = 24 if network.version == 4 else 64
                    if network.prefixlen < minimum_prefix:
                        errors.append(f"{field_name} muss auf ein enges Netzwerk begrenzt sein")
                    cgnat = ipaddress.ip_network("100.64.0.0/10")
                    if not network.is_private and not (
                        network.version == 4 and network.subnet_of(cgnat)
                    ):
                        errors.append(f"{field_name} darf nur private oder CGNAT-Netze enthalten")

            def valid_networks(cidrs: list[str]):
                networks = []
                for cidr in cidrs:
                    try:
                        networks.append(ipaddress.ip_network(cidr, strict=False))
                    except ValueError:
                        pass
                return networks

            proxy_networks = valid_networks(self.trusted_proxy_cidrs)
            admin_networks = valid_networks(self.admin_client_cidrs)
            if any(
                proxy.version == admin.version and proxy.overlaps(admin)
                for proxy in proxy_networks
                for admin in admin_networks
            ):
                errors.append("TRUSTED_PROXY_CIDRS und ADMIN_CLIENT_CIDRS dürfen nicht überlappen")

            if self.mail_intake_enabled:
                errors.append("MAIL_INTAKE_ENABLED ist in Produktion bis zum signierten Ingress-Manifest nicht erlaubt")
            if self.mail_receiving_enabled and not self.mail_ingress_prevalidated:
                errors.append(
                    "MAIL_INGRESS_PREVALIDATED muss für produktiven Maileingang true sein"
                )

            database_url = reveal_secret(self.database_url)
            parsed_database = urlsplit(database_url)
            database_password = unquote(parsed_database.password or "")
            database_user = unquote(parsed_database.username or "")
            if (
                parsed_database.scheme not in {"postgres", "postgresql"}
                or not parsed_database.hostname
                or not database_user
                or not database_password
            ):
                errors.append("DATABASE_URL muss in Produktion vollständige PostgreSQL-Zugangsdaten enthalten")
            elif database_password.lower() in _WEAK_VALUES or database_password == database_user:
                errors.append("DATABASE_URL verwendet ein unsicheres Datenbankpasswort")
            elif database_user != "datasynq_runtime":
                errors.append("DATABASE_URL muss in Produktion datasynq_runtime verwenden")

            if self.smtp_security == "none" and self.smtp_host and not self.allow_insecure_mail_transport:
                errors.append("SMTP_SECURITY=none ist in Produktion nicht erlaubt")
            if self.mail_imap_security == "none" and self.mail_imap_host and not self.allow_insecure_mail_transport:
                errors.append("MAIL_IMAP_SECURITY=none ist in Produktion nicht erlaubt")

        if errors:
            raise ValueError("Ungültige Konfiguration: " + "; ".join(dict.fromkeys(errors)))
        return self

    @property
    def database_dsn(self) -> str:
        return reveal_secret(self.database_url)

    @property
    def runtime_database_dsn(self) -> str:
        return reveal_secret(self.runtime_database_url)

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)

    @property
    def mail_receiving_enabled(self) -> bool:
        return bool(self.mail_imap_host and self.mail_imap_username and reveal_secret(self.mail_imap_password))


def load_settings() -> Settings:
    secrets_dir = Path(os.environ.get("DATASYNQ_SECRETS_DIR", "/run/secrets"))
    return Settings(_secrets_dir=secrets_dir if secrets_dir.is_dir() else None)


settings = load_settings()
