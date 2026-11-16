"""SSRF Validation and Protection Layer.

Provides comprehensive URL and IP address validation to defend against
Server-Side Request Forgery (SSRF), DNS rebinding, and internal network reconnaissance.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from typing import Any, Sequence

import anyio


class SSRFSecurityError(Exception):
    """Base exception for all SSRF and connection security violations."""


class InvalidURLError(SSRFSecurityError):
    """Raised when a URL scheme, format, credential, or hostname syntax is forbidden or invalid."""


class BlockedIPError(SSRFSecurityError):
    """Raised when an IP destination belongs to a private, loopback, or cloud metadata network."""


class DNSResolutionError(SSRFSecurityError):
    """Raised when DNS resolution fails or cannot resolve any valid address."""


class RedirectSecurityError(SSRFSecurityError):
    """Raised when a redirect destination violates security rules or exceeds allowed limits."""


class ResourceLimitError(SSRFSecurityError):
    """Raised when a request violates size, timeout, or resource boundaries."""


class PeerVerificationError(SSRFSecurityError):
    """Raised when the connected socket peer IP does not match the pinned IP or cannot be verified."""


class TLSVerificationError(SSRFSecurityError):
    """Raised when TLS certificate verification or hostname checking fails."""


# Allowed protocols
ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata and internal hostnames explicitly disallowed
BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "localhost",
}

# Explicit IPv4 networks that must be blocked
BLOCKED_IPV4_NETWORKS = [
    ipaddress.IPv4Network("0.0.0.0/8"),          # Current network ("this" host)
    ipaddress.IPv4Network("10.0.0.0/8"),         # RFC 1918 Private
    ipaddress.IPv4Network("100.64.0.0/10"),      # RFC 6598 Shared / Carrier-grade NAT
    ipaddress.IPv4Network("127.0.0.0/8"),        # RFC 1122 Loopback
    ipaddress.IPv4Network("169.254.0.0/16"),     # RFC 3927 Link-local / Cloud metadata (169.254.169.254)
    ipaddress.IPv4Network("172.16.0.0/12"),      # RFC 1918 Private
    ipaddress.IPv4Network("192.0.0.0/24"),       # RFC 6890 IETF Protocol Assignments
    ipaddress.IPv4Network("192.0.2.0/24"),       # RFC 5737 TEST-NET-1
    ipaddress.IPv4Network("192.88.99.0/24"),     # RFC 7526 6to4 Relay Anycast
    ipaddress.IPv4Network("192.168.0.0/16"),     # RFC 1918 Private
    ipaddress.IPv4Network("198.18.0.0/15"),      # RFC 2544 Network Benchmark
    ipaddress.IPv4Network("198.51.100.0/24"),    # RFC 5737 TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),     # RFC 5737 TEST-NET-3
    ipaddress.IPv4Network("224.0.0.0/4"),        # RFC 5771 Multicast
    ipaddress.IPv4Network("240.0.0.0/4"),        # RFC 1112 Reserved for future use
    ipaddress.IPv4Network("255.255.255.255/32"), # RFC 919 Broadcast
]

# Explicit IPv6 networks that must be blocked
BLOCKED_IPV6_NETWORKS = [
    ipaddress.IPv6Network("::/128"),             # Unspecified address
    ipaddress.IPv6Network("::1/128"),            # Loopback
    ipaddress.IPv6Network("64:ff9b::/96"),       # IPv4/IPv6 translation
    ipaddress.IPv6Network("100::/64"),           # Discard-only prefix
    ipaddress.IPv6Network("2001:db8::/32"),      # Documentation prefix
    ipaddress.IPv6Network("2002::/16"),          # 6to4
    ipaddress.IPv6Network("fc00::/7"),           # RFC 4193 Unique Local Address (ULA)
    ipaddress.IPv6Network("fe80::/10"),          # RFC 4291 Link-local unicast
    ipaddress.IPv6Network("ff00::/8"),           # Multicast
]

# Patterns for detecting octal, decimal, or hex obfuscated IP addresses
_HEX_INT_PATTERN = re.compile(r"^0x[0-9a-fA-F]+$", re.IGNORECASE)
_DEC_INT_PATTERN = re.compile(r"^\d+$")
_DOMAIN_LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9_-]{0,61}[a-zA-Z0-9])?$")


def validate_hostname_syntax(hostname: str) -> None:
    """Validate RFC 1123 hostname syntax or bracketed IPv6 syntax."""
    if not hostname or len(hostname) > 253:
        raise InvalidURLError("Hostname length must be between 1 and 253 characters.")

    # Reject whitespace, null bytes, backslashes, forward slashes
    if any(c in hostname for c in " \t\r\n\x00\\/"):
        raise InvalidURLError("Hostname contains invalid whitespace or control characters.")

    if hostname.startswith(".") or hostname.endswith("."):
        raise InvalidURLError("Hostname must not start or end with a dot.")

    if ".." in hostname:
        raise InvalidURLError("Hostname must not contain consecutive dots.")

    # Check if host is a valid IPv4 or IPv6 address literal
    clean_ip = hostname.strip("[]")
    try:
        ipaddress.ip_address(clean_ip)
        return
    except ValueError:
        pass

    # If brackets remain, it's a malformed IPv6 address
    if "[" in hostname or "]" in hostname:
        raise InvalidURLError(f"Malformed IPv6 address literal: '{hostname}'.")

    # Validate individual domain labels
    labels = hostname.split(".")
    for label in labels:
        if not label or len(label) > 63:
            raise InvalidURLError(f"Domain label '{label}' must be 1 to 63 characters long.")
        if not _DOMAIN_LABEL_PATTERN.match(label):
            raise InvalidURLError(f"Domain label '{label}' contains invalid characters or placements.")


def parse_and_validate_url(url: str) -> urllib.parse.ParseResult:
    """Parse a URL and enforce protocol, scheme, credential, and structure invariants."""
    if not isinstance(url, str) or not url.strip():
        raise InvalidURLError("URL must be a non-empty string.")

    cleaned_url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(cleaned_url)
    except Exception as exc:
        raise InvalidURLError(f"Malformed URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError(
            f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted."
        )

    # Reject any user-information syntax in URLs (e.g., http://user:pass@host, http://@host, http://:pass@host)
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise InvalidURLError("User credentials (username/password) in URLs are forbidden.")

    try:
        hostname = parsed.hostname
    except Exception as exc:
        raise InvalidURLError(f"Malformed hostname in URL: {exc}") from exc

    if not hostname:
        raise InvalidURLError("URL must contain a valid, non-empty hostname.")

    validate_hostname_syntax(hostname)

    # Port validation
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise InvalidURLError(f"Invalid port in URL: {exc}") from exc
    except Exception as exc:
        raise InvalidURLError(f"Malformed port in URL: {exc}") from exc

    if parsed_port is not None:
        if not (1 <= parsed_port <= 65535):
            raise InvalidURLError(f"Port {parsed_port} is outside the valid range 1-65535.")

    return parsed


def parse_obfuscated_ip(hostname: str) -> ipaddress.IPv4Address | None:
    """Detect and parse integer or hex representations of IPv4 addresses."""
    clean_host = hostname.strip("[]")

    # Pure decimal integer (e.g. 2130706433 -> 127.0.0.1)
    if _DEC_INT_PATTERN.match(clean_host):
        try:
            val = int(clean_host, 10)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except (ValueError, OverflowError):
            pass

    # Hex integer (e.g. 0x7f000001 -> 127.0.0.1)
    if _HEX_INT_PATTERN.match(clean_host):
        try:
            val = int(clean_host, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except (ValueError, OverflowError):
            pass

    # Dotted with octal parts (e.g. 0177.0.0.1)
    parts = clean_host.split(".")
    if len(parts) == 4 and any(p.startswith("0") and len(p) > 1 for p in parts):
        try:
            octets = []
            for p in parts:
                if p.startswith(("0x", "0X")):
                    octets.append(int(p, 16))
                elif p.startswith("0") and len(p) > 1:
                    octets.append(int(p, 8))
                else:
                    octets.append(int(p, 10))
            if all(0 <= o <= 255 for o in octets):
                return ipaddress.IPv4Address(bytes(octets))
        except (ValueError, OverflowError):
            pass

    return None


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
    """Check if an IPv4 or IPv6 address falls into any non-global, blocked, or private range."""
    # Correctly unwrap and inspect IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if ip.is_loopback:
        return True, f"Loopback address ({ip})"
    if ip.is_private:
        return True, f"Private address ({ip})"
    if ip.is_link_local:
        return True, f"Link-local address ({ip})"
    if ip.is_multicast:
        return True, f"Multicast address ({ip})"
    if ip.is_reserved:
        return True, f"Reserved address ({ip})"
    if ip.is_unspecified:
        return True, f"Unspecified address ({ip})"
    if not ip.is_global:
        return True, f"Non-global address ({ip})"

    if isinstance(ip, ipaddress.IPv4Address):
        for net in BLOCKED_IPV4_NETWORKS:
            if ip in net:
                return True, f"Blocked IPv4 network {net} ({ip})"

    if isinstance(ip, ipaddress.IPv6Address):
        for net in BLOCKED_IPV6_NETWORKS:
            if ip in net:
                return True, f"Blocked IPv6 network {net} ({ip})"

    return False, ""


def validate_ip_address(
    ip_input: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Validate a given IP address against all blocked ranges. Raises BlockedIPError if prohibited."""
    if isinstance(ip_input, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        ip = ip_input
    else:
        clean_str = ip_input.strip("[]")
        try:
            ip = ipaddress.ip_address(clean_str)
        except ValueError:
            obf = parse_obfuscated_ip(clean_str)
            if obf is not None:
                ip = obf
            else:
                raise InvalidURLError(f"Invalid IP address format: {ip_input}")

    blocked, reason = is_ip_blocked(ip)
    if blocked:
        raise BlockedIPError(f"Access to {ip} is forbidden: {reason}.")

    return ip


def _validate_resolved_ips(addr_info: Sequence[Any], clean_host: str) -> list[str]:
    """Helper to validate all resolved socket addrinfo records against SSRF rules."""
    if not addr_info:
        raise DNSResolutionError(f"No DNS records found for '{clean_host}'.")

    validated_ips: list[str] = []
    seen: set[str] = set()

    for item in addr_info:
        sockaddr = item[4]
        raw_ip = sockaddr[0]
        if raw_ip in seen:
            continue
        seen.add(raw_ip)

        # Validate each resolved IP address against all SSRF rules
        validated_ip = validate_ip_address(raw_ip)
        validated_ips.append(str(validated_ip))

    if not validated_ips:
        raise DNSResolutionError(f"No usable IP addresses resolved for '{clean_host}'.")

    return validated_ips


def resolve_and_validate_hostname(hostname: str, port: int | None = None) -> list[str]:
    """Synchronously resolve a hostname to IP addresses via DNS and validate every resolved IP.

    Returns the list of safe, validated IP string addresses.
    Raises BlockedIPError or DNSResolutionError if any resolved IP is prohibited or resolution fails.
    """
    clean_host = hostname.strip().lower()

    if clean_host in BLOCKED_HOSTNAMES:
        raise BlockedIPError(f"Access to prohibited hostname '{clean_host}' is blocked.")

    # Direct IP literal check
    try:
        direct_ip = ipaddress.ip_address(clean_host.strip("[]"))
        validated = validate_ip_address(direct_ip)
        return [str(validated)]
    except ValueError:
        pass

    obfuscated_ip = parse_obfuscated_ip(clean_host)
    if obfuscated_ip is not None:
        validated = validate_ip_address(obfuscated_ip)
        return [str(validated)]

    validate_hostname_syntax(clean_host)

    target_port = port if port is not None else 80
    try:
        addr_info = socket.getaddrinfo(
            clean_host,
            target_port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise DNSResolutionError(f"DNS resolution failed for '{clean_host}': {exc}") from exc
    except SSRFSecurityError:
        raise
    except Exception as exc:
        raise DNSResolutionError(f"Unexpected resolution error for '{clean_host}': {exc}") from exc

    return _validate_resolved_ips(addr_info, clean_host)


async def resolve_and_validate_hostname_async(
    hostname: str,
    port: int | None = None,
    timeout: float | None = None,
) -> list[str]:
    """Asynchronously resolve a hostname to IP addresses with timeout and SSRF validation.

    Non-blocking, respects AnyIO cancellation scopes, checks every returned IPv4 and IPv6
    address, and raises ResourceLimitError if the resolution timeout expires.
    """
    clean_host = hostname.strip().lower()

    if clean_host in BLOCKED_HOSTNAMES:
        raise BlockedIPError(f"Access to prohibited hostname '{clean_host}' is blocked.")

    # Direct IP literal check (no network call needed)
    try:
        direct_ip = ipaddress.ip_address(clean_host.strip("[]"))
        validated = validate_ip_address(direct_ip)
        return [str(validated)]
    except ValueError:
        pass

    obfuscated_ip = parse_obfuscated_ip(clean_host)
    if obfuscated_ip is not None:
        validated = validate_ip_address(obfuscated_ip)
        return [str(validated)]

    validate_hostname_syntax(clean_host)

    target_port = port if port is not None else 80
    try:
        if timeout is not None and timeout > 0:
            with anyio.fail_after(timeout):
                addr_info = await anyio.getaddrinfo(
                    clean_host,
                    target_port,
                    type=socket.SOCK_STREAM,
                )
        else:
            addr_info = await anyio.getaddrinfo(
                clean_host,
                target_port,
                type=socket.SOCK_STREAM,
            )
    except TimeoutError as exc:
        raise ResourceLimitError(f"DNS resolution timed out for '{clean_host}' after {timeout}s.") from exc
    except socket.gaierror as exc:
        raise DNSResolutionError(f"DNS resolution failed for '{clean_host}': {exc}") from exc
    except SSRFSecurityError:
        raise
    except Exception as exc:
        raise DNSResolutionError(f"Unexpected resolution error for '{clean_host}': {exc}") from exc

    return _validate_resolved_ips(addr_info, clean_host)


def validate_target_url(
    url: str,
    resolve_dns: bool = True,
) -> tuple[urllib.parse.ParseResult, list[str]]:
    """Complete validation pipeline for a target URL.

    1. Parses and validates scheme, credentials, port, and hostname syntax.
    2. If resolve_dns is True: synchronously resolves and validates hostname against SSRF rules.
       If resolve_dns is False: validates blocked hostnames and IP literals without blocking on DNS.
    Returns (parsed_url, list_of_validated_ips).
    """
    parsed = parse_and_validate_url(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    clean_host = hostname.strip().lower()
    if clean_host in BLOCKED_HOSTNAMES:
        raise BlockedIPError(f"Access to prohibited hostname '{clean_host}' is blocked.")

    # Validate IP literal immediately
    try:
        direct_ip = ipaddress.ip_address(clean_host.strip("[]"))
        validated = validate_ip_address(direct_ip)
        return parsed, [str(validated)]
    except ValueError:
        pass

    obf = parse_obfuscated_ip(clean_host)
    if obf is not None:
        validated = validate_ip_address(obf)
        return parsed, [str(validated)]

    if resolve_dns:
        validated_ips = resolve_and_validate_hostname(hostname, port)
        return parsed, validated_ips

    return parsed, []


async def validate_target_url_async(
    url: str,
    timeout: float | None = None,
) -> tuple[urllib.parse.ParseResult, list[str]]:
    """Complete asynchronous validation pipeline for a target URL with non-blocking DNS resolution."""
    parsed = parse_and_validate_url(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    validated_ips = await resolve_and_validate_hostname_async(hostname, port, timeout=timeout)
    return parsed, validated_ips
