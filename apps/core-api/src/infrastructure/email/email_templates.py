"""Jinja2-based email template rendering — loads HTML and plaintext
templates from apps/core-api/templates/email/ and renders them with
the supplied context variables.

Uses Jinja2 (not manual string concatenation) per the project's
"prefer a mature library" directive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from observability import get_logger

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


def _render(template_name: str, **context: object) -> str:
    """Render a single template file. Returns empty string on failure."""
    try:
        template = _env.get_template(template_name)
        return template.render(**context)
    except TemplateNotFound:
        logger.error("email.template.not_found", template=template_name)
        return ""
    except Exception:
        logger.error("email.template.render_failed", template=template_name, exc_info=True)
        return ""


def render_verification_email(verify_url: str) -> tuple[str, str]:
    """Render the email-verification HTML and plaintext templates.

    Returns (html_body, plaintext_body). Either may be empty if the
    template failed to render (logged, never raised).
    """
    context = {"verify_url": verify_url, "year": datetime.now(UTC).year}
    html = _render("verify_email.html", **context)
    plaintext = _render("verify_email.txt", **context)
    return html, plaintext


def render_password_reset_email(reset_url: str) -> tuple[str, str]:
    """Render the password-reset HTML and plaintext templates.

    Returns (html_body, plaintext_body). Either may be empty if the
    template failed to render (logged, never raised).
    """
    context = {"reset_url": reset_url, "year": datetime.now(UTC).year}
    html = _render("password_reset.html", **context)
    plaintext = _render("password_reset.txt", **context)
    return html, plaintext
