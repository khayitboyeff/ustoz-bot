from __future__ import annotations

import ipaddress
from typing import Any

import requests


def validate_ip_address(value: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 45:
        return False
    try:
        ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return True


def validate_ipv4_address(value: str) -> bool:
    if not validate_ip_address(value):
        return False
    return isinstance(ipaddress.ip_address(value.strip()), ipaddress.IPv4Address)


def get_ip_details(ip_value: str, api_key: str | None = None) -> dict[str, Any]:
    cleaned = (ip_value or "").strip()
    if not validate_ip_address(cleaned):
        raise ValueError("Noto‘g‘ri IP manzil.")

    ip_obj = ipaddress.ip_address(cleaned)
    if not ip_obj.is_global:
        raise ValueError("Private, loopback yoki noto‘g‘ri IP manzil rad etildi.")

    for url in (
        f"https://ipwho.is/{cleaned}",
        f"https://ipapi.co/{cleaned}/json/",
    ):
        payload = {"output": "json"}
        if api_key and "ipwho.is" in url:
            payload["access_key"] = api_key
        try:
            response = requests.get(url, params=payload, timeout=(3, 6))
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                continue
            return {
                "ip": data.get("ip") or cleaned,
                "country": data.get("country") or data.get("country_name") or "mavjud emas",
                "region": data.get("region") or data.get("region_name") or "mavjud emas",
                "city": data.get("city") or "mavjud emas",
                "provider": data.get("org") or data.get("asn") or data.get("provider") or "mavjud emas",
                "type": data.get("type") or "IPv4",
                "status": "ok",
            }
        except (requests.RequestException, ValueError, TypeError):
            continue

    return {
        "ip": cleaned,
        "country": "mavjud emas",
        "region": "mavjud emas",
        "city": "mavjud emas",
        "provider": "mavjud emas",
        "type": "IPv4",
        "status": "error",
        "message": "IP ma’lumoti uchun tashqi xizmat ishlamadi. Iltimos, keyinroq urinib ko‘ring.",
    }
