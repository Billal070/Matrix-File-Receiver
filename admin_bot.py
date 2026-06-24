import logging
from datetime import datetime
import io  # ইন-মেমোরি ফাইল হ্যান্ডলিংয়ের জন্য

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes,
)

import database as db
from config import ADMIN_BOT_TOKEN, USER_BOT_TOKEN, ADMIN_TELEGRAM_ID, BOT_NAME, DIVIDER

logger = logging.getLogger(__name__)

# Conversation states
SELECT_USER, ENTER_AMOUNT, ENTER_NOTE, ATTACH_FILE = range(4)
BROADCAST_TEXT = 10

STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "declined": "❌"}


# Safe admin check to avoid string vs int bugs (common in Railway environment variables)
def is_admin(uid):
    try:
        return int(uid) == int(ADMIN_TELEGRAM_ID)
    except Exception:
        return str(uid) == str(ADMIN_TELEGRAM_ID)


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone can use this — shows their Telegram ID."""
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🪪 *আপনার Telegram ID:*\n"
        f"`{uid}`\n\n"
        f"_এই সংখ্যাটি Railway তে `ADMIN_TELEGRAM_ID` হিসেবে দিন।_",
        parse_mode="Markdown",
    )

def fmt_dt(s):
    try:
        return datetime.fromisoformat(s).strftime("%d %b %Y  %I:%M %p")
    except Exception:
        return s or "N/A"

def pbar(val, total, w=8):
    """Text progress bar."""
    if total == 0:
        return "░" * w
    f = round(val / total * w)
    return "█" * f + "░" * (w - f)

def pct(val, total):
    return round(val / total * 100) if total else 0


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _dashboard_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏳ Pending",    callback_data="nav_pending"),
            InlineKeyboardButton("📋 History",    callback_data="nav_history"),
        ],
        [
            InlineKeyboardButton("👥 Members",    callback_data="nav_members"),
            InlineKeyboardButton("💰 Payments",   callback_data="nav_payments"),
        ],
        [
            InlineKeyboardButton("📊 Stats",      callback_data="nav_stats"),
            InlineKeyboardButton("📣 Broadcast",  callback_data="nav_broadcast"),
        ],
        [
            InlineKeyboardButton("💸 পেমেন্ট পাঠান", callback_data="nav_sendpayment"),
        ],
    ])


def _build_dashboard_text(stats):
    alert = f"\n🔔 *{stats['pending']} Pending!*" if stats["pending"] else ""
    t = stats["total_subs"]
    return (
        f"〔 👨‍💼 *Admin Panel* 〕\n"
        f"🔷 {BOT_NAME}\n"
        f"{DIVIDER}{alert}\n\n"
        f"📊 *Quick Stats:*\n"
        f"  👥 সদস্য:         *{stats['total_users']}* জন\n"
        f"  📁 সাবমিশন:      *{t}* টি\n\n"
        f"  ✅ {pbar(stats['approved'],t)} *{stats['approved']}* ({pct(stats['approved'],t)}%)\n"
        f"  ⏳ {pbar(stats['pending'],t)} *{stats['pending']}* ({pct(stats['pending'],t)}%)\n"
        f"  ❌ {pbar(stats['declined'],t)} *{stats['declined']}* ({pct(stats['declined'],t)}%)\n\n"
        f"  💰 মোট পেমেন্ট: *{stats['total_paid']:,.0f} ৳*\n"
        f"{DIVIDER}\n"
        f"_নিচের বাটন থেকে যেকোনো section এ যান_ 👇"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"⛔ *Unauthorized!*\n\n"
            f"🪪 আপনার Telegram ID: `{update.effective_user.id}`\n\n"
            f"_এই ID টি Railway তে `ADMIN_TELEGRAM_ID` variable এ দিন।_",
            parse_mode="Markdown",
        )
        return
    stats = db.get_stats()
    await update.message.reply_text(
        _build_dashboard_text(stats),
        parse_mode="Markdown",
        reply_markup=_dashboard_keyboard(),
    )


# ── Dashboard Navigation Callbacks ────────────────────────────────────────────

async def cb_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Unauthorized", show_alert=True)
        return
    await q.answer()

    action = q.data  # e.g. "nav_pending"

    if action == "nav_pending":
        await _send_pending(q.message.chat_id, context)
    elif action == "nav_history":
        await _send_history(q.message.chat_id, context)
    elif action == "nav_members":
        await _send_members(q.message.chat_id, context)
    elif action == "nav_payments":
        await _send_payments(q.message.chat_id, context)
    elif action == "nav_stats":
        await _send_stats(q.message.chat_id, context)
    elif action == "nav_broadcast":
        await context.bot.send_message(
            q.message.chat_id,
            f"📣 *Broadcast*\n{DIVIDER}\n\n"
            f"সব সদস্যদের কাছে যে বার্তাটি পাঠাতে চান সেটি লিখুন।\n\n"
            f"_বাতিল করতে /cancel লিখুন।_",
            parse_mode="Markdown",
        )
        context.user_data["awaiting_broadcast"] = True
    elif action == "nav_sendpayment":
        # Trigger send payment flow
        await _sendpayment_init(q.message.chat_id, context)


# ── /stats ────────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_stats(update.message.chat_id, context)

async def _send_stats(chat_id, context):
    s = db.get_stats()
    t = s["total_subs"]
    text = (
        f"📊 *বিস্তারিত পরিসংখ্যান*\n"
        f"{DIVIDER}\n\n"
        f"👥 *সদস্য:*\n"
        f"   সক্রিয়: *{s['total_users']}* জন\n\n"
        f"📁 *সাবমিশন:*\n"
        f"   মোট:         *{t}*\n"
        f"   ✅ Approved: *{s['approved']}*  {pbar(s['approved'],t)} {pct(s['approved'],t)}%\n"
        f"   ⏳ Pending:  *{s['pending']}*  {pbar(s['pending'],t)} {pct(s['pending'],t)}%\n"
        f"   ❌ Declined: *{s['declined']}*  {pbar(s['declined'],t)} {pct(s['declined'],t)}%\n\n"
        f"💰 *পেমেন্ট:*\n"
        f"   লেনদেন সংখ্যা: *{s['total_payments']}* বার\n"
        f"   মোট প্রদান:    *{s['total_paid']:,.0f} ৳*\n\n"
        f"{DIVIDER}\n"
        f"🕐 _{fmt_dt(datetime.now().isoformat())}_"
    )
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")


# ── /pending ──────────────────────────────────────────────────────────────────

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_pending(update.message.chat_id, context)

async def _send_pending(chat_id, context):
    subs = db.get_pending_submissions()
    if not subs:
        await context.bot.send_message(
            chat_id,
            f"✅ *কোনো Pending সাবমিশন নেই!*\n_সব ঠিকঠাক আছে।_",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_message(
        chat_id,
        f"⏳ *{len(subs)} টি Pending সাবমিশন*\n_Approve বা Decline করুন:_",
        parse_mode="Markdown",
    )

    for sub in subs[:6]:  # Max 6 at once
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅  Approve", callback_data=f"approve_{sub['sub_id']}"),
            InlineKeyboardButton("❌  Decline", callback_data=f"decline_{sub['sub_id']}"),
        ]])
        cap = (
            f"📨 *{sub['sub_id']}*\n"
            f"{DIVIDER}\n"
            f"👤 *{sub['full_name']}*\n"
            f"   🔗 @{sub['username'] or '—'}\n"
            f"   🪪 `{sub['user_id']}`\n"
            f"📄 `{sub['file_name']}`\n"
            f"💬 _{sub['caption'] or 'caption নেই'}_\n"
            f"🕐 {fmt_dt(sub['submitted_at'])}"
        )
        try:
            # Note: file_id restriction bypass also implemented in pending section if file_id comes from multiple bots
            await context.bot.send_document(
                chat_id=chat_id,
                document=sub["file_id"],
                caption=cap,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Pending doc send error [{sub['sub_id']}]: {e}")

    if len(subs) > 6:
        await context.bot.send_message(
            chat_id,
            f"_...আরও {len(subs)-6}টি pending আছে। /pending দিয়ে আবার দেখুন।_",
            parse_mode="Markdown",
        )


# ── /history ──────────────────────────────────────────────────────────────────

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_history(update.message.chat_id, context)

async def _send_history(chat_id, context):
    subs = db.get_all_submissions(limit=20)
    if not subs:
        await context.bot.send_message(chat_id, "📭 *কোনো হিস্ট্রি নেই।*", parse_mode="Markdown")
        return

    text = f"📋 *সাবমিশন হিস্ট্রি* (সর্বশেষ {len(subs)}টি)\n{DIVIDER}\n\n"
    for sub in subs:
        em = STATUS_EMOJI.get(sub["status"], "❓")
        text += (
            f"{em} *{sub['sub_id']}* — _{sub['status'].upper()}_\n"
            f"   👤 {sub['full_name']}\n"
            f"   📄 `{sub['file_name']}`\n"
            f"   📅 {fmt_dt(sub['submitted_at'])}\n\n"
        )
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")


# ── /members ──────────────────────────────────────────────────────────────────

async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_members(update.message.chat_id, context)

async def _send_members(chat_id, context):
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 *কোনো সদস্য নেই।*", parse_mode="Markdown")
        return

    text = f"👥 *সকল সদস্য ({len(users)} জন)*\n{DIVIDER}\n\n"
    keyboard = []

    for i, u in enumerate(users, 1):
        ms = db.get_member_stats(u["user_id"])
        text += (
            f"*{i}. {u['full_name']}*\n"
            f"   🔗 @{u['username'] or '—'}  🪪 `{u['user_id']}`\n"
            f"   📁 {len(ms['subs'])} সাব  ✅{ms['approved']} ⏳{ms['pending']}\n"
            f"   💰 পেয়েছে: *{ms['total_paid']:,.0f} ৳*\n\n"
        )
        keyboard.append([InlineKeyboardButton(
            f"👤 {u['full_name']}",
            callback_data=f"member_{u['user_id']}"
        )])

    await context.bot.send_message(
        chat_id, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_member_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔", show_alert=True); return
    await q.answer()

    uid  = int(q.data.replace("member_", ""))
    user = db.get_user(uid)
    if not user:
        await q.message.reply_text("❌ সদস্য পাওয়া যায়নি।"); return

    ms = db.get_member_stats(uid)

    text = (
        f"👤 *{user['full_name']}*\n"
        f"{DIVIDER}\n\n"
        f"🔗 @{user['username'] or '—'}\n"
        f"🪪 User ID: `{uid}`\n"
        f"📅 যোগদান: {fmt_dt(user['registered_at'])}\n\n"
        f"📁 *সাবমিশন সারসংক্ষেপ:*\n"
        f"   মোট:         *{len(ms['subs'])}*\n"
        f"   ✅ Approved: *{ms['approved']}*\n"
        f"   ⏳ Pending:  *{ms['pending']}*\n"
        f"   ❌ Declined: *{ms['declined']}*\n\n"
        f"💰 *পেমেন্ট:*\n"
        f"   মোট লেনদেন: *{len(ms['pays'])}* বার\n"
        f"   মোট পেয়েছে: *{ms['total_paid']:,.0f} ৳*\n\n"
    )

    if ms["subs"]:
        text += f"📋 *সর্বশেষ সাবমিশন:*\n"
        for sub in ms["subs"][:5]:
            em = STATUS_EMOJI.get(sub["status"], "❓")
            text += f"   {em} `{sub['sub_id']}` — {fmt_dt(sub['submitted_at'])}\n"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💸 এই সদস্যকে পেমেন্ট পাঠান",
            callback_data=f"quickpay_{uid}"
        )
    ]])
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── /payments ─────────────────────────────────────────────────────────────────

async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_payments(update.message.chat_id, context)

async def _send_payments(chat_id, context):
    pays = db.get_all_payments(limit=20)
    if not pays:
        await context.bot.send_message(chat_id, "💰 *কোনো পেমেন্ট হিস্ট্রি নেই।*", parse_mode="Markdown")
        return

    total = sum(p["amount"] for p in pays)
    text  = f"💰 *পেমেন্ট হিস্ট্রি* (সর্বশেষ {len(pays)}টি)\n{DIVIDER}\n\n"
    for pay in pays:
        text += (
            f"💵 *{pay['pay_id']}*\n"
            f"   👤 {pay['full_name']}  (@{pay['username'] or '—'})\n"
            f"   💲 *{pay['amount']:,.0f} ৳*\n"
            f"   📝 _{pay['note'] or '—'}_\n"
            f"   📅 {fmt_dt(pay['sent_at'])}\n\n"
        )
    text += f"{DIVIDER}\n💎 *সর্বমোট: {total:,.0f} ৳*"
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")


# ── /sendpayment ──────────────────────────────────────────────────────────────

async def cmd_sendpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await _sendpayment_init(update.message.chat_id, context)
    return SELECT_USER


async def _sendpayment_init(chat_id, context):
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 _কোনো সদস্য নেই।_", parse_mode="Markdown")
        return

    context.user_data["pay_users"] = {str(u["user_id"]): dict(u)
