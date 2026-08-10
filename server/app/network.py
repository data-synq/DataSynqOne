import ipaddress

from fastapi import Request

from .config import settings


def resolve_client_ip(peer: str, forwarded: str | None, trusted_proxy_cidrs: list[str]) -> str:
    if not forwarded:
        return peer
    try:
        peer_ip = ipaddress.ip_address(peer)
        trusted = any(
            peer_ip in ipaddress.ip_network(cidr, strict=False) for cidr in trusted_proxy_cidrs
        )
        chain = [ipaddress.ip_address(part.strip()) for part in forwarded.split(",")]
    except ValueError:
        return peer
    if not trusted or not chain or len(chain) > 5:
        return peer
    return str(chain[-1])


def request_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if settings.environment != "production":
        return peer
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), settings.trusted_proxy_cidrs)


def is_admin_network(client_ip: str) -> bool:
    try:
        address = ipaddress.ip_address(client_ip)
        return any(
            address in ipaddress.ip_network(cidr, strict=False) for cidr in settings.admin_client_cidrs
        )
    except ValueError:
        return False
