"""Experimental WhatsApp Channel admin-invite auto-accept adapter.

This module deliberately keeps the WhatsApp Web client isolated from the existing
Cloud API client. It can be enabled independently and reports failures without
bringing down the commerce bot.

The underlying WhatsApp Web client is expected to expose an async
`accept_channel_admin_invite(invite)` operation. Different Web client libraries
may expose different event/acceptance APIs, so the adapter uses a small protocol
and does not assume a particular library implementation.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelAdminInvite:
    """Normalized invitation information."""

    channel_id: str
    channel_name: Optional[str] = None
    invite_id: Optional[str] = None
    raw: Any = None


class ChannelAdminAutoAcceptor:
    """Accept Channel admin invitations through an injected Web client.

    The client must provide one of:
      * `accept_channel_admin_invite(invite)`
      * `acceptChannelAdminInvite(invite)`

    `allowed_channel_ids`, when configured, prevents accepting invitations for
    channels that were not explicitly approved.
    """

    def __init__(
        self,
        client: Any,
        *,
        allowed_channel_ids: Optional[set[str]] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.client = client
        self.allowed_channel_ids = allowed_channel_ids or set()
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)

    async def accept(self, invite: ChannelAdminInvite) -> bool:
        if not invite.channel_id:
            logger.warning("Ignoring Channel admin invite without channel_id")
            return False

        if self.allowed_channel_ids and invite.channel_id not in self.allowed_channel_ids:
            logger.warning(
                "Ignoring Channel admin invite for unapproved channel %s (%s)",
                invite.channel_id,
                invite.channel_name or "unknown",
            )
            return False

        method = getattr(self.client, "accept_channel_admin_invite", None)
        if method is None:
            method = getattr(self.client, "acceptChannelAdminInvite", None)

        if method is None:
            logger.error(
                "WhatsApp Web client does not expose a Channel admin invite "
                "acceptance method. R&D is required for the installed client."
            )
            return False

        for attempt in range(1, self.max_retries + 1):
            try:
                result = method(invite.raw if invite.raw is not None else invite)
                if inspect.isawaitable(result):
                    result = await result

                logger.info(
                    "Channel admin invite accepted: channel=%s name=%s attempt=%s result=%r",
                    invite.channel_id,
                    invite.channel_name or "unknown",
                    attempt,
                    result,
                )
                return True
            except Exception:
                logger.exception(
                    "Failed to accept Channel admin invite: channel=%s attempt=%s/%s",
                    invite.channel_id,
                    attempt,
                    self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)

        return False


def normalize_invite(raw: Any) -> Optional[ChannelAdminInvite]:
    """Convert common event-object/dict shapes into our normalized model."""
    if raw is None:
        return None

    def get(name: str, default: Any = None) -> Any:
        if isinstance(raw, dict):
            return raw.get(name, default)
        return getattr(raw, name, default)

    channel = get("channel")
    channel_id = get("channel_id") or get("channelId")
    channel_name = get("channel_name") or get("channelName")

    if channel is not None:
        if isinstance(channel, dict):
            channel_id = channel_id or channel.get("id")
            channel_name = channel_name or channel.get("name")
        else:
            channel_id = channel_id or getattr(channel, "id", None)
            channel_name = channel_name or getattr(channel, "name", None)

    if not channel_id:
        return None

    return ChannelAdminInvite(
        channel_id=str(channel_id),
        channel_name=str(channel_name) if channel_name else None,
        invite_id=(str(get("invite_id")) if get("invite_id") else None),
        raw=raw,
    )


async def handle_channel_admin_invite(
    raw_invite: Any,
    *,
    client: Any,
    allowed_channel_ids: Optional[set[str]] = None,
) -> bool:
    """Entry point for a WhatsApp Web client's invitation event."""
    invite = normalize_invite(raw_invite)
    if invite is None:
        logger.warning("Received an unrecognized Channel admin invitation event: %r", raw_invite)
        return False

    acceptor = ChannelAdminAutoAcceptor(
        client,
        allowed_channel_ids=allowed_channel_ids,
    )
    return await acceptor.accept(invite)
