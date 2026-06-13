"""
axiom/backends/transport.py

Shared httpx transport for every cloud/LLM HTTP client (Gemini + universal).

Solves a real-world failure mode (QA-test-connexion-gemini, 2026-06-12): on a
machine whose IPv6 routing is silently broken, SYNs to a provider's AAAA
addresses get no answer, and Python tries addresses one by one — each dead
IPv6 address stalls for the kernel's ~130s SYN timeout before the next one is
tried. With several AAAA records published, the first request of a client
took minutes. The google-genai SDK makes it worse by passing timeout=None on
every request, which also disables any client-level httpx timeout.

Strategy, in order:
1. IPv4 first: the connection is attempted on a socket pinned to AF_INET
   (via local_address), so IPv6 addresses fail instantly at bind time —
   no network wait at all. Virtually every provider has IPv4, so this is
   the fast path everywhere.
2. IPv6 fallback: if IPv4 itself cannot connect (IPv6-only network), the
   request is retried once on a regular dual-stack transport, and the
   choice is remembered so later requests skip the dead probe.
3. Connect timeout: a per-address connect timeout is injected when the
   request has none, so even the fallback path can never stall for minutes.
   Read/write timeouts are left untouched: long generations stay unlimited.
"""

from __future__ import annotations

import httpx

# Per address attempt (TCP connect + TLS). Generous: a healthy connect is
# RTT-bound and takes well under a second.
_CONNECT_TIMEOUT_S: float = 5.0


class IPv4FirstTransport(httpx.BaseTransport):
    """httpx transport that prefers IPv4 and enforces a connect timeout.

    Safe to retry on the fallback path: a connect error happens before
    anything is sent, and our request bodies are plain bytes (not streams).
    """

    def __init__(self) -> None:
        # local_address pins the socket family to AF_INET: getaddrinfo still
        # returns AAAA records first, but socket.create_connection skips them
        # instantly (bind error) instead of waiting on a dead route.
        self._ipv4 = httpx.HTTPTransport(local_address="0.0.0.0")
        self._dual = httpx.HTTPTransport()
        self._ipv4_broken = False

    @staticmethod
    def _ensure_connect_timeout(request: httpx.Request) -> None:
        timeouts = dict(request.extensions.get("timeout", {}))
        if timeouts.get("connect") is None:
            timeouts["connect"] = _CONNECT_TIMEOUT_S
            request.extensions["timeout"] = timeouts

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._ensure_connect_timeout(request)
        if not self._ipv4_broken:
            try:
                return self._ipv4.handle_request(request)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # No IPv4 path to this network — remember it and stop paying
                # the probe on every request.
                self._ipv4_broken = True
        return self._dual.handle_request(request)

    def close(self) -> None:
        self._ipv4.close()
        self._dual.close()
