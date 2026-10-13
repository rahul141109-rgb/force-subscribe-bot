import os
import sqlite3
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DB_PATH = os.getenv("DB_PATH", "bot.db")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS channels "
        "(chat_id TEXT PRIMARY KEY, join_url TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def is_admin(update):
    return bool(
        update.effective_user
        and update.effective_user.id == ADMIN_ID
    )


def get_channels():
    with db() as conn:
        return conn.execute(
            "SELECT chat_id, join_url FROM channels"
        ).fetchall()


def get_video():
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='video_id'"
        ).fetchone()
        return row[0] if row else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = get_channels()
    if not channels:
        await update.message.reply_text(
            "Channels abhi configure nahi hue hain. Baad mein try karo."
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"📢 Join Channel {i}", url=url)]
        for i, (_, url) in enumerate(channels, 1)
    ]
    keyboard.append([
        InlineKeyboardButton("✅ Verify Joined", callback_data="verify")
    ])

    await update.message.reply_text(
        "Video unlock karne ke liye sabhi channels join karo, "
        "phir Verify dabao.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    for chat_id, _ in get_channels():
        try:
            member = await context.bot.get_chat_member(
                chat_id, query.from_user.id
            )
            joined = (
                member.status in ("creator", "administrator", "member")
                or (
                    member.status == "restricted"
                    and getattr(member, "is_member", False)
                )
            )
            if not joined:
                await query.message.reply_text(
                    "❌ Sabhi channels join karo, phir Verify dabao."
                )
                return
        except Exception:
            log.exception("Membership check failed")
            await query.message.reply_text(
                "Channel verify nahi ho raha. Admin se contact karo."
            )
            return

    video_id = get_video()
    if not video_id:
        await query.message.reply_text("Abhi video upload nahi hui hai.")
        return

    await context.bot.send_video(
        query.from_user.id,
        video_id,
        caption="✅ Verified! Enjoy your video."
    )


async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    parts = (update.message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await update.message.reply_text(
            "Use: /addchannel @Channel https://t.me/Channel"
        )
        return

    chat_id, url = parts[1], parts[2]
    if not url.startswith("https://t.me/"):
        await update.message.reply_text("Valid https://t.me/ link do.")
        return

    try:
        chat = await context.bot.get_chat(chat_id)
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("Bot ko channel admin banao.")
            return

        with db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO channels VALUES (?, ?)",
                (str(chat.id), url)
            )
        await update.message.reply_text(f"✅ Added: {chat.title}")
    except Exception:
        log.exception("Could not add channel")
        await update.message.reply_text(
            "Channel add nahi hua. ID, link aur admin permissions check karo."
        )


async def removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Use: /removechannel @ChannelUsername"
        )
        return

    target = context.args[0]
    try:
        if target.startswith("@"):
            target = str((await context.bot.get_chat(target)).id)
    except Exception:
        pass

    with db() as conn:
        cur = conn.execute("DELETE FROM channels WHERE chat_id=?", (target,))
    await update.message.reply_text(
        "✅ Channel removed." if cur.rowcount else "Channel nahi mila."
    )


async def channels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    channels = get_channels()
    if not channels:
        await update.message.reply_text("Koi channel add nahi hai.")
    else:
        await update.message.reply_text(
            "Channels:\n" + "\n".join(
                f"{i}. {cid} — {url}"
                for i, (cid, url) in enumerate(channels, 1)
            )
        )


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or update.effective_chat.type != "private":
        return
    if not update.message.video:
        return

    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings VALUES ('video_id', ?)",
            (update.message.video.file_id,)
        )
    await update.message.reply_text("✅ Video save ho gayi!")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(
            "/addchannel @Channel https://t.me/Channel\n"
            "/removechannel @Channel\n"
            "/channels\n\n"
            "Video update karne ke liye nayi video bhejo."
        )
    else:
        await update.message.reply_text("/start")


def main():
    with db():
        pass

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", addchannel))
    app.add_handler(CommandHandler("removechannel", removechannel))
    app.add_handler(CommandHandler("channels", channels_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))
    app.add_handler(MessageHandler(filters.VIDEO, receive_video))
    app.run_polling()


if __name__ == "__main__":
    main()
