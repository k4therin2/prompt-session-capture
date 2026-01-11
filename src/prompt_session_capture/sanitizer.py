"""
Content sanitization for privacy protection.

Redacts PII, secrets, and sensitive paths before storage.
"""

import re
from pathlib import Path
from typing import Optional


class Sanitizer:
    """Sanitizes prompt content to remove PII and secrets."""

    # Regex patterns for sensitive data
    # Note: Replacement strings use escaped brackets to avoid regex interpretation
    PATTERNS = {
        # Email addresses
        "email": (
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            r"[EMAIL]"
        ),
        # IPv4 addresses (but not version numbers like 1.2.3)
        "ipv4": (
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
            r"[IP]"
        ),
        # IPv6 addresses
        "ipv6": (
            r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',
            r"[IP]"
        ),
        # API keys (common patterns)
        "api_key_sk": (
            r'\bsk-[a-zA-Z0-9]{20,}\b',
            r"[REDACTED]"
        ),
        "api_key_pk": (
            r'\bpk-[a-zA-Z0-9]{20,}\b',
            r"[REDACTED]"
        ),
        # AWS access keys
        "aws_key": (
            r'\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b',
            r"[REDACTED]"
        ),
        # AWS secret keys (40 char base64)
        "aws_secret": (
            r'\b[A-Za-z0-9/+=]{40}\b(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])',
            r"[REDACTED]"
        ),
        # Bearer tokens
        "bearer": (
            r'Bearer\s+[A-Za-z0-9\-_]+\.?[A-Za-z0-9\-_]*\.?[A-Za-z0-9\-_]*',
            r"Bearer [REDACTED]"
        ),
        # Generic long hex strings (potential tokens/keys)
        "hex_token": (
            r'\b[a-fA-F0-9]{32,}\b',
            r"[REDACTED]"
        ),
        # Private key blocks
        "private_key": (
            r'-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----',
            r"[REDACTED]"
        ),
        # Password patterns in common formats
        "password_param": (
            r'(?:password|passwd|pwd|secret|token)[\s]*[=:]\s*[^\s]{3,}',
            r"[REDACTED]"
        ),
    }

    # Home directory patterns for different OSes
    # Note: Windows pattern replacement uses \\\\ to produce literal backslash
    HOME_PATTERNS = [
        (r'/home/[^/\s]+/', '~/'),
        (r'/Users/[^/\s]+/', '~/'),
        (r'C:\\Users\\[^\\]+\\', '~\\\\'),  # Double escape for regex replacement
    ]

    def __init__(
        self,
        redact_emails: bool = True,
        redact_ips: bool = True,
        redact_secrets: bool = True,
        anonymize_paths: bool = True,
        custom_patterns: Optional[list] = None
    ):
        """
        Initialize sanitizer with configuration.

        Args:
            redact_emails: Remove email addresses
            redact_ips: Remove IP addresses
            redact_secrets: Remove API keys, tokens, passwords
            anonymize_paths: Convert absolute paths to relative
            custom_patterns: List of (pattern, replacement) tuples
        """
        self.redact_emails = redact_emails
        self.redact_ips = redact_ips
        self.redact_secrets = redact_secrets
        self.anonymize_paths = anonymize_paths
        self.custom_patterns = custom_patterns or []

    def sanitize(self, content: str) -> str:
        """
        Sanitize content by removing/redacting sensitive data.

        Args:
            content: Raw prompt content

        Returns:
            Sanitized content safe for storage
        """
        if not content:
            return content

        result = content

        # Apply redactions based on config
        if self.redact_emails:
            pattern, replacement = self.PATTERNS["email"]
            result = re.sub(pattern, replacement, result)

        if self.redact_ips:
            for key in ["ipv4", "ipv6"]:
                pattern, replacement = self.PATTERNS[key]
                result = re.sub(pattern, replacement, result)

        if self.redact_secrets:
            secret_keys = [
                "api_key_sk", "api_key_pk", "aws_key", "aws_secret",
                "bearer", "hex_token", "private_key", "password_param"
            ]
            for key in secret_keys:
                pattern, replacement = self.PATTERNS[key]
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        if self.anonymize_paths:
            for pattern, replacement in self.HOME_PATTERNS:
                result = re.sub(pattern, replacement, result)

        # Apply custom patterns
        for pattern, replacement in self.custom_patterns:
            result = re.sub(pattern, replacement, result)

        return result

    def is_sensitive(self, content: str) -> bool:
        """
        Check if content contains sensitive data.

        Args:
            content: Content to check

        Returns:
            True if sensitive patterns detected
        """
        for key, (pattern, _) in self.PATTERNS.items():
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False


# Default sanitizer instance
default_sanitizer = Sanitizer()


def sanitize(content: str) -> str:
    """Convenience function using default sanitizer."""
    return default_sanitizer.sanitize(content)
