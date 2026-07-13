"""Shared HTTP helper: GET with 429/5xx backoff. Orchestrator handles
skip-on-fail; collectors add transient retry."""

from __future__ import annotations

import asyncio

import httpx


async def aget_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
    backoff: float = 2.0,
    timeout: float = 30.0,
    verify_status: bool = True,
) -> dict:
    """GET JSON with exponential backoff on 429/5xx. Raises on persistent failure."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers or {}) as client:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= retries:
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429 and attempt < retries:
                    await asyncio.sleep(backoff * (2 ** attempt))
                    attempt += 1
                    continue
                if verify_status:
                    resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "json" not in ct and not resp.text.lstrip().startswith(("{", "[")):
                    raise ValueError(f"non-JSON response ({ct}): {resp.text[:120]}")
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt < retries and (isinstance(exc, httpx.HTTPStatusError) and getattr(exc.response, "status_code", 0) == 429):
                    await asyncio.sleep(backoff * (2 ** attempt))
                    attempt += 1
                    continue
                if attempt >= retries:
                    break
                attempt += 1
        raise last_exc or RuntimeError("aget_json failed")


async def aget_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
    backoff: float = 2.0,
    timeout: float = 30.0,
) -> str:
    """GET raw text with backoff on 429/5xx."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers or {}) as client:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= retries:
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429 and attempt < retries:
                    await asyncio.sleep(backoff * (2 ** attempt))
                    attempt += 1
                    continue
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < retries:
                    await asyncio.sleep(backoff * (2 ** attempt))
                    attempt += 1
                    continue
                break
        raise last_exc or RuntimeError("aget_text failed")
