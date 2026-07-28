# WhatsApp Channel Admin Auto-Accept (v1)

This branch adds an isolated adapter for automatically accepting WhatsApp Channel admin invitations.

## Current architecture

The existing commerce bot uses the WhatsApp Cloud API. Channel admin invitation acceptance is not wired into that API client. This feature therefore uses an **injected WhatsApp Web-compatible client** and keeps it isolated from the Cloud API implementation.

The adapter looks for either of these client methods:

- `accept_channel_admin_invite(invite)`
- `acceptChannelAdminInvite(invite)`

It also supports an allow-list of Channel IDs, retries failures, and logs successful/failed acceptance attempts.

## Files

- `channel_admin_auto_accept.py` — normalized invite model, event normalization, acceptance adapter and retry handling.
- `tests/test_channel_admin_auto_accept.py` — unit tests using a fake Web client.

## Important: v1 is an adapter, not yet a live Web session

A WhatsApp Web client/session still needs to be connected to the adapter and its actual invitation event mapped to `handle_channel_admin_invite()`.

Do **not** expect the current Cloud API webhook alone to trigger this code. The next R&D step is to add a supported WhatsApp Web-compatible client/session and map its real Channel admin invitation event.

## Testing

The unit tests validate the adapter without connecting to WhatsApp. Once a Web client is connected, the real test is:

1. Start the bot with the Web session.
2. Send a Channel admin invitation to the bot account.
3. Do not manually accept it.
4. Confirm the invitation event reaches `handle_channel_admin_invite()`.
5. Confirm logs show acceptance success.
6. Verify the bot account is an admin of the Channel.

Never put WhatsApp session credentials, QR-derived secrets, or authentication state into Git.
