import os
import sqlite3
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    ChatMemberHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
GROUP_ID = int(os.environ["GROUP_ID"])

DB_FILE = "members.db"


# ---------- DATABASE ----------

def db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    return conn


def save_member(user_id):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO members(user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_members():
    conn = db()
    rows = conn.execute("SELECT user_id FROM members").fetchall()
    conn.close()
    return [row[0] for row in rows]


# ---------- TRACK MEMBERS ----------

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    if update.effective_chat.id != GROUP_ID:
        return

    user = update.effective_user

    if user:
        save_member(user.id)


async def track_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if not chat or chat.id != GROUP_ID:
        return

    member = update.chat_member.new_chat_member
    user = member.user

    # Member या Administrator/Owner सभी IDs store कर सकते हैं;
    # Remove All के समय admins को skip किया जाएगा।
    save_member(user.id)


# ---------- CHECK ADMIN ----------

async def get_admin_ids(bot):
    admins = await bot.get_chat_administrators(GROUP_ID)
    return {admin.user.id for admin in admins}


# ---------- HIDDEN REMOVE ALL ----------

async def private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_chat:
        return

    # केवल private DM
    if update.effective_chat.type != "private":
        return

    # केवल Owner
    if update.effective_user.id != OWNER_ID:
        return

    text = (update.message.text or "").strip().lower()

    if text != "remove all":
        return

    await update.message.reply_text(
        "⚠️ Remove All शुरू कर रहा हूँ..."
    )

    admin_ids = await get_admin_ids(context.bot)

    members = get_members()

    removed = 0
    skipped = 0

    for user_id in members:

        # Admin/Owner को कभी remove नहीं करना
        if user_id in admin_ids:
            skipped += 1
            continue

        # Bot को भी skip
        if user_id == context.bot.id:
            skipped += 1
            continue

        try:
            await context.bot.ban_chat_member(
                chat_id=GROUP_ID,
                user_id=user_id
            )

            removed += 1

            # Telegram API पर बहुत तेज requests न भेजें
            await asyncio.sleep(0.2)

        except Exception:
            skipped += 1

    await update.message.reply_text(
        f"✅ Remove All पूरा हुआ.\n\n"
        f"Removed: {removed}\n"
        f"Skipped/Failed: {skipped}"
    )


# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and update.effective_user.id == OWNER_ID
    ):
        await update.message.reply_text(
            "🤖 Bot Online\n\n"
            "Hidden command:\n"
            "remove all"
        )


# ---------- MAIN ----------

def main():

    # Database तैयार करो
    db().close()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start केवल Owner के लिए
    from telegram.ext import CommandHandler

    app.add_handler(
        CommandHandler("start", start)
    )

    # Private DM
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT,
            private_text
        )
    )

    # Group messages से members track
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS,
            track_message
        )
    )

    # Join/leave/status changes track
    app.add_handler(
        ChatMemberHandler(
            track_member,
            ChatMemberHandler.CHAT_MEMBER
        )
    )

    print("Bot is running...")

    app.run_polling(
        allowed_updates=[
            "message",
            "chat_member",
            "my_chat_member"
        ]
    )


if __name__ == "__main__":
    main()
