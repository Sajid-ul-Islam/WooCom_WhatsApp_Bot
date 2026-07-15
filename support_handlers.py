import os
import logging
from context import BotContext

logger = logging.getLogger(__name__)


async def handle_human_agent(ctx: BotContext, to: str):
    """Pauses the bot and provides a link to contact a human agent."""
    await ctx.db.set_bot_paused(to, True)
    agent_phone = os.getenv("HUMAN_AGENT_PHONE", "8801952700500")
    msg = (
        "⏸️ I have paused my automated responses.\n\n"
        f"Please click this link to chat directly with our human agent on WhatsApp:\n👉 https://wa.me/{agent_phone}\n\n"
        "Type */resume* when you want me to take over again."
    )
    await ctx.wa.send_text_message(to, msg)


async def _handle_wit_resume_bot(ctx: BotContext, to: str):
    """Resume bot for user after human agent handoff."""
    await ctx.db.set_bot_paused(to, False)
    await ctx.db.set_user_state(to, "idle")
    await ctx.wa.send_text_message(to, "✅ Bot resumed. How can I help you?")
