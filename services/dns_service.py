from __future__ import annotations

import asyncio
import logging
import re
import ipaddress

import dns.exception
import dns.asyncresolver
import dns.resolver

logger = logging.getLogger(__name__)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
LOCAL_SUFFIXES = {"localhost", "local", "internal", "intranet", "lan", "home", "corp", "test", "invalid", "arpa"}


def validate_domain_name(value: str) -> bool:
    if not value or not isinstance(value, str) or len(value) > 254:
        return False
    cleaned = value.strip().lower().rstrip(".")
    if not cleaned or cleaned.startswith("."):
        return False
    if cleaned.split(".")[-1] in LOCAL_SUFFIXES:
        return False
    return bool(DOMAIN_RE.fullmatch(cleaned))


def normalize_domain(value: str) -> str:
    cleaned = (value or "").strip().lower().rstrip(".")
    if not validate_domain_name(cleaned):
        raise ValueError("Noto‘g‘ri domen formati.")
    return cleaned


def lookup_dns_records(domain: str) -> dict[str, list[str]]:
    normalized = normalize_domain(domain)
    records: dict[str, list[str]] = {"A": [], "AAAA": [], "MX": [], "NS": []}
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5

    for record_type in ("A", "AAAA", "MX", "NS"):
        try:
            answers = resolver.resolve(normalized, record_type)
            values = []
            for item in answers:
                value = str(item)
                if record_type in {"A", "AAAA"}:
                    try:
                        if not ipaddress.ip_address(value).is_global:
                            continue
                    except ValueError:
                        continue
                values.append(value[:253].replace("\r", " ").replace("\n", " "))
                if len(values) == 10:
                    break
            records[record_type] = values
        except dns.resolver.NoAnswer:
            records[record_type] = []
        except dns.exception.DNSException:
            records[record_type] = []
    return records


async def lookup_dns_records_async(domain: str, timeout: float = 5.0) -> dict[str, list[str]]:
    normalized = normalize_domain(domain)
    records: dict[str, list[str]] = {"A": [], "AAAA": [], "MX": [], "NS": []}
    errors: list[str] = []

    async def resolve_type(record_type: str) -> tuple[str, list[str], str | None]:
        resolver = dns.asyncresolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        try:
            answers = await resolver.resolve(normalized, record_type, lifetime=timeout)
        except dns.resolver.NoAnswer:
            return record_type, [], None
        except dns.exception.DNSException as exc:
            return record_type, [], type(exc).__name__

        values: list[str] = []
        for item in answers:
            value = str(item)
            if record_type in {"A", "AAAA"}:
                try:
                    if not ipaddress.ip_address(value).is_global:
                        continue
                except ValueError:
                    continue
            values.append(value[:253].replace("\r", " ").replace("\n", " "))
            if len(values) == 10:
                break
        return record_type, values, None

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(resolve_type(record_type) for record_type in records)),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise TimeoutError("DNS so‘rovi vaqtida javob kelmadi.") from exc

    for record_type, values, error in results:
        records[record_type] = values
        if error:
            errors.append(error)
            logger.warning("DNS %s query failed (%s).", record_type, error)

    if errors and not any(records.values()):
        if "Timeout" in errors:
            raise TimeoutError("DNS server belgilangan vaqtda javob bermadi.")
        raise RuntimeError("DNS server so‘rovni bajara olmadi.")
    if errors:
        records["_errors"] = errors
    return records
