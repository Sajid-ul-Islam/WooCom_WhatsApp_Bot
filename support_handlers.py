import os
import logging
from context import BotContext
from i18n import get_text, format_text

logger = logging.getLogger(__name__)


async def handle_human_agent(ctx: BotContext, to: str):
    """Pauses the bot and provides a link to contact a human agent."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_bot_paused(to, True)
    agent_phone = os.getenv("HUMAN_AGENT_PHONE", "8801952700500")
    msg = format_text(lang, "bot_paused_msg", phone=agent_phone)
    await ctx.wa.send_text_message(to, msg)


async def _handle_wit_resume_bot(ctx: BotContext, to: str):
    """Resume bot for user after human agent handoff."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_bot_paused(to, False)
    await ctx.db.set_user_state(to, "idle")
    await ctx.wa.send_text_message(to, get_text(lang, "bot_resumed"))
