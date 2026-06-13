import asyncio
import os
import logging
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest, GetDialogsRequest
from telethon.tl.types import (
    Channel, Chat, ChatFull, InputPeerChannel, InputPeerChat,
    ChannelParticipantAdmin, ChannelParticipantCreator,
    ChatParticipantAdmin, ChatParticipantCreator
)
from telethon.errors import (
    UserAlreadyParticipantError, ChatAdminRequiredError,
    UserNotMutualContactError, FloodWaitError, PeerFloodError,
    UserPrivacyRestrictedError, BotGroupsBlockedError
)
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH")
SESSION_FILE = "group_adder_session"

user_clients = {}
user_states = {}
pending_phone = {}

async def get_admin_groups(user_client: TelegramClient):
    admin_groups = []
    async for dialog in user_client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            try:
                from telethon.tl.functions.channels import GetFullChannelRequest
                full = await user_client(GetFullChannelRequest(entity))
                me = await user_client.get_me()
                from telethon.tl.functions.channels import GetParticipantRequest
                part = await user_client(GetParticipantRequest(entity, me))
                participant = part.participant
                if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    admin_groups.append(entity)
            except Exception:
                pass
        elif isinstance(entity, Chat):
            try:
                from telethon.tl.functions.messages import GetFullChatRequest
                full = await user_client(GetFullChatRequest(entity.id))
                me = await user_client.get_me()
                for p in full.full_chat.participants.participants:
                    if p.user_id == me.id:
                        if isinstance(p, (ChatParticipantAdmin, ChatParticipantCreator)):
                            admin_groups.append(entity)
                        break
            except Exception:
                pass
    return admin_groups


async def add_bot_to_groups(user_client: TelegramClient, bot_username: str, status_callback):
    try:
        bot_entity = await user_client.get_entity(bot_username)
    except Exception as e:
        await status_callback(f"❌ Bot **{bot_username}** nahi mila. Username check karo.\n\nError: {e}")
        return

    await status_callback(f"🔍 Tumhare admin groups dhundh raha hoon...")
    admin_groups = await get_admin_groups(user_client)

    if not admin_groups:
        await status_callback("❌ Koi bhi group nahi mila jisme tum admin ho.")
        return

    await status_callback(f"✅ **{len(admin_groups)}** groups mile jisme tum admin ho!\n\n⏳ Ab {bot_username} ko add kar raha hoon...")

    success_count = 0
    fail_count = 0
    already_count = 0
    results = []

    for group in admin_groups:
        group_name = getattr(group, 'title', 'Unknown')
        try:
            await asyncio.sleep(1.5)
            if isinstance(group, Channel):
                await user_client(InviteToChannelRequest(group, [bot_entity]))
            elif isinstance(group, Chat):
                await user_client(AddChatUserRequest(group.id, bot_entity, fwd_limit=10))
            success_count += 1
            results.append(f"✅ {group_name}")
            logger.info(f"Added {bot_username} to {group_name}")
        except UserAlreadyParticipantError:
            already_count += 1
            results.append(f"ℹ️ {group_name} (already added)")
        except BotGroupsBlockedError:
            fail_count += 1
            results.append(f"🚫 {group_name} (bot group mein join nahi kar sakta)")
        except ChatAdminRequiredError:
            fail_count += 1
            results.append(f"⛔ {group_name} (admin rights nahi hai)")
        except UserPrivacyRestrictedError:
            fail_count += 1
            results.append(f"🔒 {group_name} (privacy restricted)")
        except FloodWaitError as e:
            await status_callback(f"⏳ Flood wait: {e.seconds} seconds ruk raha hoon...")
            await asyncio.sleep(e.seconds)
            fail_count += 1
            results.append(f"⚠️ {group_name} (flood wait, skip kiya)")
        except PeerFloodError:
            await status_callback("⚠️ Too many requests. Kuch der baad dobara try karo.")
            fail_count += 1
            results.append(f"⚠️ {group_name} (peer flood)")
        except Exception as e:
            fail_count += 1
            results.append(f"❌ {group_name} ({str(e)[:40]})")
            logger.error(f"Failed to add to {group_name}: {e}")

    result_text = "\n".join(results[:30])
    if len(results) > 30:
        result_text += f"\n... aur {len(results)-30} groups"

    summary = (
        f"🎉 **Done!**\n\n"
        f"✅ Successfully added: **{success_count}**\n"
        f"ℹ️ Already in group: **{already_count}**\n"
        f"❌ Failed: **{fail_count}**\n\n"
        f"**Details:**\n{result_text}"
    )
    await status_callback(summary)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "👋 **GROUP ADDER BOT** mein aapka swagat hai!\n\n"
        "Yeh bot kisi bhi dusre bot ko tumhare **saare admin groups** mein add kar deta hai.\n\n"
        "**Kaise use karein:**\n"
        "1️⃣ Pehle `/login` command se apna Telegram account connect karo\n"
        "2️⃣ Phir kisi bhi bot ka username bhejo (e.g. `@SomeBotName`)\n"
        "3️⃣ Bot automatically us bot ko tumhare saare admin groups mein add kar dega!\n\n"
        "👉 Shuru karne ke liye: /login",
        parse_mode="Markdown"
    )


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_clients and user_clients[user_id].is_connected():
        me = await user_clients[user_id].get_me()
        await update.message.reply_text(
            f"✅ Tum pehle se connected ho: **{me.first_name}** (@{me.username})\n\n"
            "Ab kisi bot ka username bhejo jise add karna hai.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "📱 Apna **phone number** bhejo (international format mein):\n"
        "Example: `+919876543210`\n\n"
        "⚠️ Yeh number wahi hona chahiye jis Telegram account ke groups mein bot add karna hai.",
        parse_mode="Markdown"
    )
    user_states[user_id] = "waiting_phone"


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_clients:
        try:
            await user_clients[user_id].disconnect()
        except Exception:
            pass
        del user_clients[user_id]
    if user_id in user_states:
        del user_states[user_id]
    session_path = f"{SESSION_FILE}_{user_id}.session"
    if os.path.exists(session_path):
        os.remove(session_path)
    await update.message.reply_text("✅ Logout ho gaye. Dobara login ke liye /login bhejo.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_clients and user_clients[user_id].is_connected():
        try:
            me = await user_clients[user_id].get_me()
            await update.message.reply_text(
                f"✅ **Connected!**\n"
                f"Name: {me.first_name}\n"
                f"Username: @{me.username}\n"
                f"Phone: {me.phone}",
                parse_mode="Markdown"
            )
        except Exception:
            await update.message.reply_text("⚠️ Connection issue. /login se dobara try karo.")
    else:
        await update.message.reply_text("❌ Connected nahi ho. /login karo pehle.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    state = user_states.get(user_id)

    if state == "waiting_phone":
        phone = text
        if not phone.startswith("+"):
            await update.message.reply_text("❌ Phone number `+` se shuru hona chahiye. Example: `+919876543210`", parse_mode="Markdown")
            return

        await update.message.reply_text("⏳ OTP bhej raha hoon...")

        try:
            client = TelegramClient(f"{SESSION_FILE}_{user_id}", API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            user_clients[user_id] = client
            pending_phone[user_id] = phone
            context.user_data["phone_code_hash"] = result.phone_code_hash
            user_states[user_id] = "waiting_otp"
            await update.message.reply_text(
                "✅ OTP bheja gaya Telegram par!\n\n"
                "📩 Apna OTP bhejo (sirf numbers, spaces ke saath bhi chalega):\n"
                "Example: `12345` ya `1 2 3 4 5`",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}\n\nDobara try karo /login")
            user_states.pop(user_id, None)

    elif state == "waiting_otp":
        otp = text.replace(" ", "").replace("-", "")
        phone = pending_phone.get(user_id)
        phone_code_hash = context.user_data.get("phone_code_hash")
        client = user_clients.get(user_id)

        if not client or not phone:
            await update.message.reply_text("❌ Session expire ho gaya. /login dobara karo.")
            user_states.pop(user_id, None)
            return

        try:
            await client.sign_in(phone, otp, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            user_states.pop(user_id, None)
            pending_phone.pop(user_id, None)
            await update.message.reply_text(
                f"🎉 **Login successful!**\n\n"
                f"Welcome, **{me.first_name}**! (@{me.username})\n\n"
                f"Ab kisi bhi bot ka username bhejo jise tumhare saare admin groups mein add karna hai.\n"
                f"Example: `@SomeBotUsername`",
                parse_mode="Markdown"
            )
        except Exception as e:
            error_str = str(e)
            if "2FA" in error_str or "PASSWORD" in error_str.upper() or "SessionPasswordNeededError" in error_str:
                user_states[user_id] = "waiting_2fa"
                await update.message.reply_text(
                    "🔐 **2-Factor Authentication** required hai!\n\n"
                    "Apna Telegram **2FA password** bhejo:",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ OTP galat hai ya expire ho gaya.\n\nError: {e}\n\nDobara: /login")
                user_states.pop(user_id, None)

    elif state == "waiting_2fa":
        client = user_clients.get(user_id)
        if not client:
            await update.message.reply_text("❌ Session expire. /login dobara karo.")
            user_states.pop(user_id, None)
            return
        try:
            await client.sign_in(password=text)
            me = await client.get_me()
            user_states.pop(user_id, None)
            await update.message.reply_text(
                f"🎉 **Login successful!**\n\n"
                f"Welcome, **{me.first_name}**! (@{me.username})\n\n"
                f"Ab kisi bhi bot ka username bhejo jise tumhare saare admin groups mein add karna hai.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 2FA password galat hai.\n\nError: {e}")

    else:
        if text.startswith("@") or (not text.startswith("/") and "bot" in text.lower()):
            bot_username = text if text.startswith("@") else f"@{text}"

            client = user_clients.get(user_id)
            if not client or not client.is_connected():
                await update.message.reply_text(
                    "❌ Pehle /login karo apna Telegram account connect karne ke liye.",
                    parse_mode="Markdown"
                )
                return

            status_msg = await update.message.reply_text(
                f"⏳ **{bot_username}** ko tumhare admin groups mein add kar raha hoon...",
                parse_mode="Markdown"
            )

            async def update_status(text):
                try:
                    await status_msg.edit_text(text, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(text, parse_mode="Markdown")

            await add_bot_to_groups(client, bot_username, update_status)
        else:
            await update.message.reply_text(
                "❓ Samajh nahi aaya.\n\n"
                "• Login ke liye: /login\n"
                "• Bot add karne ke liye: kisi bot ka username bhejo jaise `@BotUsername`\n"
                "• Status check karne ke liye: /status",
                parse_mode="Markdown"
            )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("GROUP ADDER BOT starting...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
