import logging
from datetime import datetime

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


def is_admin(uid): return uid == ADMIN_TELEGRAM_ID

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
        await update.message.reply_text("⛔ *Unauthorized.*", parse_mode="Markdown")
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

    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}

    kb = []
    for u in users:
        pays = db.get_user_payments(u["user_id"])
        total = sum(p["amount"] for p in pays)
        kb.append([InlineKeyboardButton(
            f"👤 {u['full_name']}  ({total:,.0f} ৳)",
            callback_data=f"payto_{u['user_id']}"
        )])
    kb.append([InlineKeyboardButton("❌ বাতিল", callback_data="pay_cancel")])

    await context.bot.send_message(
        chat_id,
        f"💸 *পেমেন্ট পাঠান*\n{DIVIDER}\n\n"
        f"কার কাছে পেমেন্ট পাঠাবেন?\n"
        f"_(পাশের সংখ্যা = এখন পর্যন্ত মোট পেমেন্ট)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# Quick pay from member detail
async def cb_quickpay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔", show_alert=True); return
    await q.answer()

    uid   = int(q.data.replace("quickpay_", ""))
    user  = db.get_user(uid)
    users = db.get_all_users()
    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}
    context.user_data["pay_uid"]   = uid
    context.user_data["pay_name"]  = user["full_name"] if user else str(uid)

    await q.message.reply_text(
        f"✅ নির্বাচিত: *{context.user_data['pay_name']}*\n\n"
        f"💲 *কত টাকা পাঠাবেন?*\n_শুধু সংখ্যা লিখুন (যেমন: 5000)_",
        parse_mode="Markdown",
    )
    return ENTER_AMOUNT


async def cb_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "pay_cancel":
        await q.edit_message_text("❌ _বাতিল করা হয়েছে।_", parse_mode="Markdown")
        return ConversationHandler.END

    uid_str = q.data.replace("payto_", "")
    sel     = context.user_data.get("pay_users", {}).get(uid_str)
    if not sel:
        await q.edit_message_text("❌ ত্রুটি।"); return ConversationHandler.END

    context.user_data["pay_uid"]  = int(uid_str)
    context.user_data["pay_name"] = sel["full_name"]

    await q.edit_message_text(
        f"✅ নির্বাচিত: *{sel['full_name']}*\n\n"
        f"💲 *কত টাকা পাঠাবেন?*\n_শুধু সংখ্যা লিখুন (যেমন: 5000)_",
        parse_mode="Markdown",
    )
    return ENTER_AMOUNT


async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", "").replace("৳", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ *সঠিক পরিমাণ লিখুন।*\n_উদাহরণ: 5000_", parse_mode="Markdown"
        )
        return ENTER_AMOUNT

    context.user_data["pay_amount"] = amount
    await update.message.reply_text(
        f"💲 পরিমাণ: *{amount:,.0f} ৳* ✅\n\n"
        f"📝 *কোনো note লিখবেন?*\n"
        f"_(bKash নম্বর, Nagad reference, ইত্যাদি)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭️ Note ছাড়াই এগিয়ে যান", callback_data="note_skip")
        ]]),
    )
    return ENTER_NOTE


async def cb_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["pay_note"] = ""
    await q.edit_message_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳*  |  📝 Note: _নেই_\n\n"
        f"📎 *কোনো ফাইল/রশিদ পাঠাবেন?*\n_ফাইল পাঠান অথবা /skip লিখুন।_",
        parse_mode="Markdown",
    )
    return ATTACH_FILE


async def enter_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_note"] = update.message.text.strip()
    await update.message.reply_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳*  |  📝 _{context.user_data['pay_note']}_\n\n"
        f"📎 *কোনো ফাইল/রশিদ পাঠাবেন?*\n_ফাইল পাঠান অথবা /skip লিখুন।_",
        parse_mode="Markdown",
    )
    return ATTACH_FILE


async def attach_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid = None
    if update.message.document:
        fid = update.message.document.file_id
    elif update.message.photo:
        fid = update.message.photo[-1].file_id
    context.user_data["pay_file"] = fid
    await _finalize_payment(update, context)
    return ConversationHandler.END


async def cmd_skip_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_file"] = None
    await _finalize_payment(update, context)
    return ConversationHandler.END


async def cmd_cancel_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ _বাতিল করা হয়েছে।_", parse_mode="Markdown")
    return ConversationHandler.END


async def _finalize_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid    = context.user_data["pay_uid"]
    name   = context.user_data["pay_name"]
    amount = context.user_data["pay_amount"]
    note   = context.user_data.get("pay_note", "")
    fid    = context.user_data.get("pay_file")

    pay_id   = db.add_payment(uid, amount, note, fid)
    user_bot = Bot(token=USER_BOT_TOKEN)

    user_text = (
        f"〔 💰 *পেমেন্ট নোটিফিকেশন!* 〕\n"
        f"{DIVIDER}\n\n"
        f"🆔 Payment ID: `{pay_id}`\n"
        f"💵 পরিমাণ: *{amount:,.0f} টাকা*\n"
    )
    if note:
        user_text += f"📝 বিস্তারিত: _{note}_\n"
    user_text += (
        f"📅 তারিখ: {fmt_dt(datetime.now().isoformat())}\n\n"
        f"✅ _পেমেন্ট পেয়েছেন কিনা নিশ্চিত করুন।_\n"
        f"ধন্যবাদ! 🙏"
    )

    try:
        if fid:
            await user_bot.send_document(chat_id=uid, document=fid, caption=user_text, parse_mode="Markdown")
        else:
            await user_bot.send_message(chat_id=uid, text=user_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Payment notify failed uid={uid}: {e}")
        await update.message.reply_text(
            f"⚠️ Save হয়েছে কিন্তু notify করা যায়নি!\n🪪 User ID: `{uid}`",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        f"〔 ✅ *পেমেন্ট পাঠানো হয়েছে!* 〕\n"
        f"{DIVIDER}\n\n"
        f"🆔 {pay_id}\n"
        f"👤 *{name}*\n"
        f"💲 *{amount:,.0f} ৳*\n"
        f"📝 _{note or '—'}_",
        parse_mode="Markdown",
    )
    context.user_data.clear()


# ── Broadcast ─────────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text(
        f"📣 *Broadcast*\n{DIVIDER}\n\n"
        f"সব সদস্যদের কাছে যে বার্তা পাঠাতে চান লিখুন।\n\n"
        f"_বাতিল করতে /cancel লিখুন।_",
        parse_mode="Markdown",
    )
    return BROADCAST_TEXT


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg   = update.message.text.strip()
    users = db.get_all_users()

    if not users:
        await update.message.reply_text("👥 কোনো সদস্য নেই।")
        return ConversationHandler.END

    proc = await update.message.reply_text(
        f"📣 _Broadcasting to {len(users)} members..._", parse_mode="Markdown"
    )

    user_bot = Bot(token=USER_BOT_TOKEN)
    success, failed = 0, 0

    broadcast_text = (
        f"📣 *Matrix File Receiver*\n"
        f"{DIVIDER}\n\n"
        f"{msg}\n\n"
        f"_{fmt_dt(datetime.now().isoformat())}_"
    )

    for u in users:
        try:
            await user_bot.send_message(
                chat_id=u["user_id"],
                text=broadcast_text,
                parse_mode="Markdown",
            )
            success += 1
        except Exception:
            failed += 1

    await proc.delete()
    await update.message.reply_text(
        f"✅ *Broadcast সম্পন্ন!*\n\n"
        f"✅ পাঠানো হয়েছে: *{success}* জনকে\n"
        f"❌ ব্যর্থ: *{failed}* জন",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ _বাতিল।_", parse_mode="Markdown")
    return ConversationHandler.END


# ── Approve / Decline Callback ─────────────────────────────────────────────────

async def cb_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Unauthorized!", show_alert=True); return

    action, sub_id = q.data.split("_", 1)
    sub = db.get_submission(sub_id)

    if not sub:
        await q.answer("❌ পাওয়া যায়নি!", show_alert=True); return

    if sub["status"] != "pending":
        await q.answer(f"⚠️ ইতোমধ্যে {sub['status'].upper()} করা হয়েছে!", show_alert=True)
        return

    user_bot = Bot(token=USER_BOT_TOKEN)
    now      = fmt_dt(datetime.now().isoformat())

    if action == "approve":
        db.update_submission_status(sub_id, "approved")
        user_msg = (
            f"〔 🎉 *ফাইল অনুমোদিত!* 〕\n"
            f"{DIVIDER}\n\n"
            f"🆔 ID: `{sub_id}`\n"
            f"📄 `{sub['file_name']}`\n"
            f"✅ স্ট্যাটাস: *Approved*\n\n"
            f"চমৎকার কাজ! ধন্যবাদ 🙏"
        )
        result_line = f"\n{DIVIDER}\n✅ *APPROVED* — {now}"
        await q.answer("✅ Approved!")

    else:
        db.update_submission_status(sub_id, "declined")
        user_msg = (
            f"〔 ❌ *ফাইল বাতিল হয়েছে।* 〕\n"
            f"{DIVIDER}\n\n"
            f"🆔 ID: `{sub_id}`\n"
            f"📄 `{sub['file_name']}`\n"
            f"❌ স্ট্যাটাস: *Declined*\n\n"
            f"_সমস্যার জন্য অ্যাডমিনের সাথে যোগাযোগ করুন।_"
        )
        result_line = f"\n{DIVIDER}\n❌ *DECLINED* — {now}"
        await q.answer("❌ Declined!")

    try:
        await user_bot.send_message(chat_id=sub["user_id"], text=user_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"User notify failed: {e}")

    try:
        new_cap = (q.message.caption or "") + result_line
        await q.edit_message_caption(caption=new_cap, parse_mode="Markdown", reply_markup=None)
    except Exception as e:
        logger.warning(f"Caption edit failed: {e}")


# ── /pending and /history commands ────────────────────────────────────────────

async def cmd_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_history(update.message.chat_id, context)

async def cmd_members_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_members(update.message.chat_id, context)

async def cmd_payments_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _send_payments(update.message.chat_id, context)


# ── App Factory ────────────────────────────────────────────────────────────────

def create_admin_app():
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()

    # Payment conversation
    pay_conv = ConversationHandler(
        entry_points=[
            CommandHandler("sendpayment", cmd_sendpayment),
            CallbackQueryHandler(cb_quickpay, pattern=r"^quickpay_"),
        ],
        states={
            SELECT_USER: [
                CallbackQueryHandler(cb_select_user, pattern=r"^(payto_|pay_cancel)"),
            ],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount),
            ],
            ENTER_NOTE: [
                CallbackQueryHandler(cb_note_skip, pattern=r"^note_skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_note),
            ],
            ATTACH_FILE: [
                CommandHandler("skip",   cmd_skip_file),
                MessageHandler(filters.Document.ALL | filters.PHOTO, attach_file),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel_pay),
            CommandHandler("start",  cmd_start),
        ],
        per_message=False,
        allow_reentry=True,
    )

    # Broadcast conversation
    bc_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast)],
        states={
            BROADCAST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, do_broadcast),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(pay_conv)
    app.add_handler(bc_conv)

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CommandHandler("pending",  cmd_pending))
    app.add_handler(CommandHandler("history",  cmd_history_cmd))
    app.add_handler(CommandHandler("members",  cmd_members_cmd))
    app.add_handler(CommandHandler("payments", cmd_payments_cmd))

    # Inline callbacks
    app.add_handler(CallbackQueryHandler(cb_nav,           pattern=r"^nav_"))
    app.add_handler(CallbackQueryHandler(cb_submission,    pattern=r"^(approve|decline)_"))
    app.add_handler(CallbackQueryHandler(cb_member_detail, pattern=r"^member_\d+$"))

    return app
