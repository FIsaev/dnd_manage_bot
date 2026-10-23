"""D&D dice bot (beta).

Watches group messages, answers anything that looks like a dice expression with
the result, and hides the full calculation path in an expandable blockquote.

    BOT_TOKEN=123:ABC python bot.py
"""

from __future__ import annotations

import html
import logging
import os
import re
import sys
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import dice

log = logging.getLogger("dndbot")

MAX_INPUT = dice.MAX_EXPR_LEN

# A plain group message is answered only when the whole message is an
# expression -- nothing but dice, numbers, brackets and operators. That keeps
# the bot quiet during normal chat.
EXPRESSION_ONLY = re.compile(r"^[0-9dD%+\-*/()\sкКдД]+$")

# Optional trailing note: "2d6+3 # sneak attack"
NOTE = re.compile(r"\s*[#;]\s*(.*)$", re.DOTALL)

HELP = (
    "<b>Dice bot (beta)</b>\n"
    "Write a dice expression in the chat and I answer with the result; "
    "the full calculation hides in the quote under it.\n\n"
    "<b>Where the bonus goes</b>\n"
    "<code>3d6+1</code> - roll 3d6, then +1 to the <i>total</i>\n"
    "<code>3d6(+1)</code> - +1 to <i>every die</i>, then sum\n"
    "<code>(3d6+1)</code> - same as above: a +/- in brackets belongs to each die\n"
    "<code>2d4(-5)</code> - a die never goes below 0, so this is 0\n\n"
    "<b>More</b>\n"
    "<code>d20+5</code>, <code>2d6(-1)*2</code>, <code>(2d6+1d4)*2</code>, "
    "<code>d%</code>, <code>4d6/2</code>\n"
    "<code>2d6+3 # sneak attack</code> - a note after # is echoed back\n\n"
    "Also works as <code>/roll 3d6+1</code>, and 3к6 is read as 3d6."
)


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def split_note(text: str) -> tuple[str, str]:
    """Split "2d6+3 # sneak attack" into the expression and the note."""
    match = NOTE.search(text)
    if not match:
        return text.strip(), ""
    return text[: match.start()].strip(), match.group(1).strip()


def looks_like_a_roll(text: str) -> bool:
    return bool(EXPRESSION_ONLY.match(text)) and dice.has_dice(text)


def render(result: dice.RollResult, note: str = "") -> str:
    """Result on top, full calculation path in an expandable quote below."""
    head = "\U0001f3b2 <b>%s</b>  <code>%s</code>" % (
        esc(result.total_text),
        esc(result.source),
    )
    if note:
        head += "\n<i>%s</i>" % esc(note)
    detail = "\n".join(esc(line) for line in result.detail_lines())
    return "%s\n<blockquote expandable>%s</blockquote>" % (head, detail)


async def answer(update: Update, text: str, *, quiet_on_error: bool) -> None:
    message = update.effective_message
    expression, note = split_note(text)
    try:
        result = dice.roll(expression)
    except dice.DiceError as error:
        if quiet_on_error:
            return
        await message.reply_text("⚠️ %s" % error, do_quote=True)
        return
    await message.reply_text(
        render(result, note),
        parse_mode=ParseMode.HTML,
        do_quote=True,
    )


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = (message.text or "").strip()
    if not text or len(text) > MAX_INPUT:
        return
    if message.from_user and message.from_user.is_bot:
        return
    expression, _ = split_note(text)
    if not looks_like_a_roll(expression):
        return
    # It passed the gate, so a parse error here is worth reporting.
    await answer(update, text, quiet_on_error=False)


async def on_roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args or "").strip()
    if not text:
        await update.effective_message.reply_text(
            "Give me something to roll, like <code>/roll 3d6(+1)+2</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    await answer(update, text, quiet_on_error=False)


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP, parse_mode=ParseMode.HTML)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("update failed: %s", context.error)


def load_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if token:
        return token
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "BOT_TOKEN":
                return value.strip().strip("'\"")
    sys.exit("No BOT_TOKEN. Put it in .env (see .env.example) or the environment.")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = Application.builder().token(load_token()).build()
    app.add_handler(CommandHandler(["start", "help"], on_help))
    app.add_handler(CommandHandler(["roll", "r"], on_roll_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_message))
    app.add_error_handler(on_error)

    log.info("dice bot is up (beta)")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
