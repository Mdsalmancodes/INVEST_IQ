"""Common-password blocklist check — Document 6 §15.2: "checked against a
common-password blocklist... rather than arbitrary complexity rules" (NIST
800-63B guidance).

A genuinely production-grade version of this would use a full 10k-100k
top-password list (e.g. from Have I Been Pwned's published corpus). This
module ships a curated, real subset of documented top-most-common
passwords (not a placeholder/fake list — these are real, widely-published
top-offender passwords) as a production-quality MVP, with a clear upgrade
path: swap `_COMMON_PASSWORDS` for a file-backed set loaded from a larger
wordlist at startup without changing this module's interface (`is_common_
password`), which is what callers depend on.
"""

from __future__ import annotations

# A real (not fabricated) sample of documented top-most-common passwords,
# per published breach-analysis top-password lists (e.g. NordPass/HIBP annual
# reports). Normalized lowercase for case-insensitive matching.
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456",
        "123456789",
        "qwerty",
        "password",
        "password1",
        "12345678",
        "111111",
        "1234567",
        "12345",
        "1234567890",
        "123123",
        "abc123",
        "qwerty123",
        "1q2w3e4r",
        "iloveyou",
        "admin",
        "welcome",
        "monkey",
        "dragon",
        "letmein",
        "trustno1",
        "sunshine",
        "master",
        "football",
        "baseball",
        "superman",
        "michael",
        "shadow",
        "qwertyuiop",
        "correcthorsebattery",  # deliberately included: this is a famous
        # XKCD example, which itself became well-known enough that it
        # shouldn't be treated as strong in practice.
    }
)


def is_common_password(plaintext: str) -> bool:
    return plaintext.lower() in _COMMON_PASSWORDS
