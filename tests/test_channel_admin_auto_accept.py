import pytest

from channel_admin_auto_accept import (
    ChannelAdminAutoAcceptor,
    ChannelAdminInvite,
    normalize_invite,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    async def accept_channel_admin_invite(self, invite):
        self.calls.append(invite)
        return True


@pytest.mark.asyncio
async def test_accepts_allowed_invite():
    client = FakeClient()
    acceptor = ChannelAdminAutoAcceptor(client, allowed_channel_ids={"123"})

    result = await acceptor.accept(ChannelAdminInvite("123", "DEEN"))

    assert result is True
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_rejects_unapproved_invite():
    client = FakeClient()
    acceptor = ChannelAdminAutoAcceptor(client, allowed_channel_ids={"123"})

    result = await acceptor.accept(ChannelAdminInvite("999", "Other"))

    assert result is False
    assert client.calls == []


def test_normalizes_dict_event():
    invite = normalize_invite({"channel": {"id": "123", "name": "DEEN"}, "invite_id": "abc"})

    assert invite is not None
    assert invite.channel_id == "123"
    assert invite.channel_name == "DEEN"
    assert invite.invite_id == "abc"


def test_normalize_unknown_event_returns_none():
    assert normalize_invite({"message": "hello"}) is None
