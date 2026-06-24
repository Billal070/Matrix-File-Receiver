import logging, os, io
from datetime import datetime
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
import database as db
from config import ADMIN_BOT_TOKEN, USER_BOT_TOKEN, ADMIN_TELEGRAM_ID, BOT_NAME, DIVIDER

logger = logging.getLogger(__name__)
SELECT_USER, ENTER_AMOUNT, ENTER_NOTE, ATTACH_FILE = range(4)
BROADCAST_TEXT = 10
STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "declined": "❌"}

def is_admin(uid):
    try: return int(uid) == int(ADMIN_TELEGRAM_ID)
    except: return str(uid) == str(ADMIN_TELEGRAM_ID)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🪪 *Telegram ID:*\n`{update.effective_user.id}`\n\n_Railway variable: ADMIN_TELEGRAM_ID_", parse_mode="Markdown")

def fmt_dt(s):
    try: return datetime.fromisoformat(s).strftime("%d %b %Y  %I:%M %p")
    except: return s or "N/A"

def pbar(val, total, w=8):
    if total == 0: return "░" * w
    f = round(val / total * w)
    return "█" * f + "░" * (w - f)

def pct(val, total):
    return round(val / total * 100) if total else 0

def _dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Pending", callback_data="nav_pending"), InlineKeyboardButton("📋 History", callback_data="nav_history")],
        [InlineKeyboardButton("👥 Members", callback_data="nav_members"), InlineKeyboardButton("💰 Payments", callback_data="nav_payments")],
        [InlineKeyboardButton("📊 Stats", callback_data="nav_stats"), InlineKeyboardButton("📣 Broadcast", callback_data="nav_broadcast")],
        [InlineKeyboardButton("💸 পেমেন্ট পাঠান", callback_data="nav_sendpayment")]
    ])

def _build_dashboard_text(stats):
    alert = f"\n🔔 *{stats['pending']} Pending!*" if stats["pending"] else ""
    t = stats["total_subs"]
    return (
        f"〔 👨‍💼 *Admin Panel* 〕\n🔷 {BOT_NAME}\n{DIVIDER}{alert}\n\n"
        f"📊 *Stats:*\n  👥 সদস্য: *{stats['total_users']}* জন\n  📁 সাবমিশন: *{t}* টি\n\n"
        f"  ✅ {pbar(stats['approved'],t)} *{stats['approved']}* ({pct(stats['approved'],t)}%)\n"
        f"  ⏳ {pbar(stats['pending'],t)} *{stats['pending']}* ({pct(stats['pending'],t)}%)\n"
        f"  ❌ {pbar(stats['declined'],t)} *{stats['declined']}* ({pct(stats['declined'],t)}%)\n\n"
        f"  💰 মোট পেমেন্ট: *{stats['total_paid']:,.0f} ৳*\n{DIVIDER}\n_সিলেক্ট করুন_ 👇"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(f"⛔ *Unauthorized!*\n\nID: `{update.effective_user.id}`", parse_mode="Markdown")
        return
    await update.message.reply_text(_build_dashboard_text(db.get_stats()), parse_mode="Markdown", reply_markup=_dashboard_keyboard())

# ── Dashboard nav (nav_sendpayment removed — handled by ConversationHandler) ──
async def cb_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Unauthorized", show_alert=True); return
    await q.answer()
    if q.data == "nav_pending": await _send_pending(q.message.chat_id, context)
    elif q.data == "nav_history": await _send_history(q.message.chat_id, context)
    elif q.data == "nav_members": await _send_members(q.message.chat_id, context)
    elif q.data == "nav_payments": await _send_payments(q.message.chat_id, context)
    elif q.data == "nav_stats": await _send_stats(q.message.chat_id, context)
    elif q.data == "nav_broadcast":
        await context.bot.send_message(q.message.chat_id, f"📣 *Broadcast*\n{DIVIDER}\n\nবার্তাটি লিখুন।\n\n_বাতিল করতে /cancel লিখুন।_", parse_mode="Markdown")
        context.user_data["awaiting_broadcast"] = True
    elif q.data == "nav_done":
        pass  # Just a display button, do nothing

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_stats(update.message.chat_id, context)

async def _send_stats(chat_id, context):
    s = db.get_stats()
    t = s["total_subs"]
    text = (
        f"📊 *বিস্তারিত পরিসংখ্যান*\n{DIVIDER}\n\n👥 *সদস্য:* *{s['total_users']}* জন\n\n"
        f"📁 *সাবমিশন:* *{t}*\n"
        f"   ✅ Approved: *{s['approved']}*  {pbar(s['approved'],t)} {pct(s['approved'],t)}%\n"
        f"   ⏳ Pending:  *{s['pending']}*  {pbar(s['pending'],t)} {pct(s['pending'],t)}%\n"
        f"   ❌ Declined: *{s['declined']}*  {pbar(s['declined'],t)} {pct(s['declined'],t)}%\n\n"
        f"💰 *পেমেন্ট:* *{s['total_payments']}* বার\n   মোট: *{s['total_paid']:,.0f} ৳*\n\n{DIVIDER}"
    )
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_pending(update.message.chat_id, context)

async def _send_pending(chat_id, context):
    subs = db.get_pending_submissions()
    if not subs:
        await context.bot.send_message(chat_id, "✅ *কোনো Pending সাবমিশন নেই!*", parse_mode="Markdown"); return
    await context.bot.send_message(chat_id, f"⏳ *{len(subs)} টি Pending সাবমিশন*", parse_mode="Markdown")
    for sub in subs[:6]:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅  Approve", callback_data=f"approve_{sub['sub_id']}"), InlineKeyboardButton("❌  Decline", callback_data=f"decline_{sub['sub_id']}")]])
        cap = f"📨 <b>{sub['sub_id']}</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>{sub['full_name']}</b> (@{sub['username'] or '—'})\n📄 <code>{sub['file_name']}</code>\n💬 {sub['caption'] or 'caption নেই'}\n📅 {fmt_dt(sub['submitted_at'])}"
        try: await context.bot.send_document(chat_id=chat_id, document=sub["file_id"], caption=cap, parse_mode="HTML", reply_markup=kb)
        except Exception as e: logger.error(f"Doc send error: {e}")

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_history(update.message.chat_id, context)

async def _send_history(chat_id, context):
    subs = db.get_all_submissions(limit=20)
    if not subs:
        await context.bot.send_message(chat_id, "📭 *কোনো হিস্ট্রি নেই।*", parse_mode="Markdown"); return
    text = f"📋 *সাবমিশন হিস্ট্রি*\n{DIVIDER}\n\n"
    for sub in subs:
        em = STATUS_EMOJI.get(sub["status"], "❓")
        text += f"{em} *{sub['sub_id']}* — _{sub['status'].upper()}_\n   👤 {sub['full_name']}\n   📄 `{sub['file_name']}`\n\n"
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_members(update.message.chat_id, context)

async def _send_members(chat_id, context):
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 *কোনো সদস্য নেই।*", parse_mode="Markdown"); return
    text = f"👥 *সকল সদস্য ({len(users)} জন)*\n{DIVIDER}\n\n"
    keyboard = []
    for i, u in enumerate(users, 1):
        ms = db.get_member_stats(u["user_id"])
        text += f"*{i}. {u['full_name']}* (@{u['username'] or '—'})\n   📁 {len(ms['subs'])} সাব | 💰 *{ms['total_paid']:,.0f} ৳*\n\n"
        keyboard.append([InlineKeyboardButton(f"👤 {u['full_name']}", callback_data=f"member_{u['user_id']}")])
    await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def cb_member_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔", show_alert=True); return
    await q.answer()
    uid = int(q.data.replace("member_", ""))
    user = db.get_user(uid)
    if not user: await q.message.reply_text("❌ সদস্য পাওয়া যায়নি।"); return
    ms = db.get_member_stats(uid)
    text = (f"👤 *{user['full_name']}*\n{DIVIDER}\n\nID: `{uid}`\n📅 যোগদান: {fmt_dt(user['registered_at'])}\n\n"
            f"📁 *সাবমিশন:* মোট {len(ms['subs'])} (✅{ms['approved']} ⏳{ms['pending']} ❌{ms['declined']})\n💰 *পেমেন্ট:* মোট {ms['total_paid']:,.0f} ৳\n\n")
    if ms["subs"]:
        text += "📋 *সর্বশেষ সাবমিশন:*\n"
        for sub in ms["subs"][:5]:
            em = STATUS_EMOJI.get(sub["status"], "❓")
            text += f"   {em} `{sub['sub_id']}` — {fmt_dt(sub['submitted_at'])}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💸 পেমেন্ট পাঠান", callback_data=f"quickpay_{uid}")]])
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_payments(update.message.chat_id, context)

async def _send_payments(chat_id, context):
    pays = db.get_all_payments(limit=20)
    if not pays:
        await context.bot.send_message(chat_id, "💰 *কোনো পেমেন্ট হিস্ট্রি নেই।*", parse_mode="Markdown"); return
    total = sum(p["amount"] for p in pays)
    text = f"💰 *পেমেন্ট হিস্ট্রি*\n{DIVIDER}\n\n"
    for pay in pays:
        text += f"💵 *{pay['pay_id']}*\n   👤 {pay['full_name']}\n   💲 *{pay['amount']:,.0f} ৳* — {fmt_dt(pay['sent_at'])}\n\n"
    text += f"{DIVIDER}\n💎 *সর্বমোট: {total:,.0f} ৳*"
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

# ── Payment Flow ──────────────────────────────────────────────────────────────

async def _sendpayment_init(chat_id, context):
    """Show member selection list."""
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 _কোনো সদস্য নেই।_", parse_mode="Markdown"); return False
    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}
    kb = []
    for u in users:
        total = sum(p["amount"] for p in db.get_user_payments(u["user_id"]))
        kb.append([InlineKeyboardButton(f"👤 {u['full_name']} ({total:,.0f} ৳)", callback_data=f"payto_{u['user_id']}")])
    kb.append([InlineKeyboardButton("❌ বাতিল", callback_data="pay_cancel")])
    await context.bot.send_message(chat_id, f"💸 *পেমেন্ট পাঠান*\n{DIVIDER}\n\nকার কাছে পেমেন্ট পাঠাবেন?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return True

# Entry point: /sendpayment command
async def cmd_sendpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    ok = await _sendpayment_init(update.message.chat_id, context)
    return SELECT_USER if ok else ConversationHandler.END

# Entry point: Dashboard button "💸 পেমেন্ট পাঠান"
async def cb_nav_sendpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔", show_alert=True); return ConversationHandler.END
    await q.answer()
    ok = await _sendpayment_init(q.message.chat_id, context)
    return SELECT_USER if ok else ConversationHandler.END

# Entry point: Member detail "💸 পেমেন্ট পাঠান" button
async def cb_quickpay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔", show_alert=True); return ConversationHandler.END
    await q.answer()
    uid = int(q.data.replace("quickpay_", ""))
    user = db.get_user(uid)
    users = db.get_all_users()
    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}
    context.user_data["pay_uid"] = uid
    context.user_data["pay_name"] = user["full_name"] if user else str(uid)
    await q.message.reply_text(
        f"✅ নির্বাচিত: *{context.user_data['pay_name']}*\n\n💲 *কত টাকা পাঠাবেন?*\n_শুধু সংখ্যা লিখুন (যেমন: 5000)_",
        parse_mode="Markdown"
    )
    return ENTER_AMOUNT

async def cb_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "pay_cancel":
        await q.edit_message_text("❌ _বাতিল।_", parse_mode="Markdown"); return ConversationHandler.END
    uid_str = q.data.replace("payto_", "")
    sel = context.user_data.get("pay_users", {}).get(uid_str)
    if not sel: await q.edit_message_text("❌ ত্রুটি।"); return ConversationHandler.END
    context.user_data["pay_uid"] = int(uid_str)
    context.user_data["pay_name"] = sel["full_name"]
    await q.edit_message_text(
        f"✅ নির্বাচিত: *{sel['full_name']}*\n\n💲 *কত টাকা পাঠাবেন?*\n_শুধু সংখ্যা লিখুন (যেমন: 5000)_",
        parse_mode="Markdown"
    )
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", "").replace("৳", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ *সঠিক পরিমাণ লিখুন।*\n_উদাহরণ: 5000_", parse_mode="Markdown")
        return ENTER_AMOUNT
    context.user_data["pay_amount"] = amount
    await update.message.reply_text(
        f"💲 পরিমাণ: *{amount:,.0f} ৳* ✅\n\n📝 *কোনো note লিখবেন?*\n_(bKash নম্বর, Nagad reference ইত্যাদি)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Note ছাড়া এগিয়ে যান", callback_data="note_skip")]])
    )
    return ENTER_NOTE

async def cb_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["pay_note"] = ""
    await q.edit_message_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳* | 📝 Note: _নেই_\n\n📎 *ফাইল বা রশীদ পাঠান অথবা /skip লিখুন।*",
        parse_mode="Markdown"
    )
    return ATTACH_FILE

async def enter_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_note"] = update.message.text.strip()
    await update.message.reply_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳* | 📝 _{context.user_data['pay_note']}_\n\n📎 *ফাইল বা রশীদ পাঠান অথবা /skip লিখুন।*",
        parse_mode="Markdown"
    )
    return ATTACH_FILE

async def attach_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid, fname = None, "receipt"
    if update.message.document:
        fid = update.message.document.file_id
        fname = update.message.document.file_name or "document"
    elif update.message.photo:
        fid = update.message.photo[-1].file_id
        fname = "receipt.jpg"
    context.user_data["pay_file"] = fid
    context.user_data["pay_filename"] = fname
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
    uid, name = context.user_data["pay_uid"], context.user_data["pay_name"]
    amount, note = context.user_data["pay_amount"], context.user_data.get("pay_note", "")
    fid = context.user_data.get("pay_file")
    fname = context.user_data.get("pay_filename", "receipt")
    pay_id = db.add_payment(uid, amount, note, fid)
    user_text = f"〔 💰 *পেমেন্ট নোটিফিকেশন!* 〕\n{DIVIDER}\n\n🆔 ID: `{pay_id}`\n💵 পরিমাণ: *{amount:,.0f} ৳*\n"
    if note: user_text += f"📝 বিস্তারিত: _{note}_\n"
    user_text += f"📅 তারিখ: {fmt_dt(datetime.now().isoformat())}\n\nধন্যবাদ! 🙏"
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            if fid:
                file_obj = await context.bot.get_file(fid)
                file_bytes = await file_obj.download_as_bytearray()
                file_io = io.BytesIO(file_bytes)
                file_io.name = fname
                await user_bot.send_document(chat_id=uid, document=file_io, caption=user_text, parse_mode="Markdown")
            else:
                await user_bot.send_message(chat_id=uid, text=user_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Payment notify failed: {e}")
        await update.message.reply_text(f"⚠️ Save হয়েছে কিন্তু notify করা যায়নি!\nError: {e}")
        return
    await update.message.reply_text(
        f"〔 ✅ *পেমেন্ট পাঠানো হয়েছে!* 〕\n{DIVIDER}\n\n🆔 {pay_id}\n👤 *{name}*\n💲 *{amount:,.0f} ৳*",
        parse_mode="Markdown"
    )
    context.user_data.clear()

# ── Broadcast ─────────────────────────────────────────────────────────────────
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text(f"📣 *Broadcast*\n{DIVIDER}\n\nবার্তা লিখুন।\n_বাতিল: /cancel_", parse_mode="Markdown")
    return BROADCAST_TEXT

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    users = db.get_all_users()
    if not users: await update.message.reply_text("👥 কোনো সদস্য নেই।"); return ConversationHandler.END
    proc = await update.message.reply_text("📣 _Broadcasting..._", parse_mode="Markdown")
    success, failed = 0, 0
    broadcast_text = f"📣 *Matrix File Receiver*\n{DIVIDER}\n\n{msg}\n\n_{fmt_dt(datetime.now().isoformat())}_"
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            for u in users:
                try:
                    await user_bot.send_message(chat_id=u["user_id"], text=broadcast_text, parse_mode="Markdown")
                    success += 1
                except: failed += 1
    except Exception as e: logger.error(f"Broadcast failed: {e}")
    await proc.delete()
    await update.message.reply_text(f"✅ *Broadcast সম্পন্ন!*\n\n✅ সফল: {success}\n❌ ব্যর্থ: {failed}", parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ _বাতিল।_", parse_mode="Markdown"); return ConversationHandler.END

# ── Approve / Decline ─────────────────────────────────────────────────────────
async def cb_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔ Unauthorized!", show_alert=True); return
    action, sub_id = q.data.split("_", 1)
    sub = db.get_submission(sub_id)
    if not sub: await q.answer("❌ পাওয়া যায়নি!", show_alert=True); return
    if sub["status"] != "pending": await q.answer(f"⚠️ ইতিমধ্যে {sub['status'].upper()} করা হয়েছে!", show_alert=True); return
    now = fmt_dt(datetime.now().isoformat())
    if action == "approve":
        db.update_submission_status(sub_id, "approved")
        user_msg = f"〔 🎉 *ফাইল অনুমোদিত!* 〕\n{DIVIDER}\n\n🆔 ID: `{sub_id}`\n📄 `{sub['file_name']}`\n✅ *Approved*\n\nধন্যবাদ 🙏"
        result_line = f"\n━━━━━━━━━━━━━━━━━━\n✅ <b>APPROVED</b> — {now}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Approved ✅", callback_data="nav_done")]])
        await q.answer("✅ Approved!")
    else:
        db.update_submission_status(sub_id, "declined")
        user_msg = f"〔 ❌ *ফাইল বাতিল হয়েছে।* 〕\n{DIVIDER}\n\n🆔 ID: `{sub_id}`\n📄 `{sub['file_name']}`\n❌ *Declined*"
        result_line = f"\n━━━━━━━━━━━━━━━━━━\n❌ <b>DECLINED</b> — {now}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Declined ❌", callback_data="nav_done")]])
        await q.answer("❌ Declined!")
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            await user_bot.send_message(chat_id=sub["user_id"], text=user_msg, parse_mode="Markdown")
    except Exception as e: logger.error(f"Notify failed: {e}")
    try:
        new_cap = (q.message.caption_html or "") + result_line
        await q.edit_message_caption(caption=new_cap, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Caption edit failed: {e}")
        try: await q.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as ex: logger.error(f"Markup edit failed: {ex}")

# ── Debug ─────────────────────────────────────────────────────────────────────
async def cmd_testnotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("🔍 Testing... wait.")
    info = f"📋 <b>Check:</b>\nYour ID: <code>{uid}</code>\nADMIN_TELEGRAM_ID: <code>{ADMIN_TELEGRAM_ID}</code>\nMatch: {'✅' if str(uid) == str(ADMIN_TELEGRAM_ID) else '❌ MISMATCH!'}"
    await update.message.reply_text(info, parse_mode="HTML")
    try:
        async with Bot(token=USER_BOT_TOKEN) as test_bot:
            bot_info = await test_bot.get_me()
            await update.message.reply_text(f"✅ USER_BOT: <b>{bot_info.full_name}</b>", parse_mode="HTML")
            try:
                await test_bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text="✅ Test notification working!")
                await update.message.reply_text("✅ Notification sent successfully!")
            except Exception as e:
                await update.message.reply_text(f"❌ Send error:\n<code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Token error:\n<code>{e}</code>", parse_mode="HTML")

async def cmd_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_history(update.message.chat_id, context)
async def cmd_members_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_members(update.message.chat_id, context)
async def cmd_payments_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_payments(update.message.chat_id, context)

# ── App Factory ───────────────────────────────────────────────────────────────
def create_admin_app():
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()

    pay_conv = ConversationHandler(
        entry_points=[
            CommandHandler("sendpayment", cmd_sendpayment),
            CallbackQueryHandler(cb_nav_sendpayment, pattern=r"^nav_sendpayment$"),  # Dashboard button ✅
            CallbackQueryHandler(cb_quickpay, pattern=r"^quickpay_"),               # Member detail button ✅
        ],
        states={
            SELECT_USER: [CallbackQueryHandler(cb_select_user, pattern=r"^(payto_|pay_cancel)")],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_NOTE: [
                CallbackQueryHandler(cb_note_skip, pattern=r"^note_skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_note)
            ],
            ATTACH_FILE: [
                CommandHandler("skip", cmd_skip_file),
                MessageHandler(filters.Document.ALL | filters.PHOTO, attach_file)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel_pay), CommandHandler("start", cmd_start)],
        per_message=False, allow_reentry=True
    )

    bc_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast)],
        states={BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_broadcast)]},
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        per_message=False, allow_reentry=True
    )

    app.add_handler(pay_conv)
    app.add_handler(bc_conv)
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("testnotify", cmd_testnotify))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("history", cmd_history_cmd))
    app.add_handler(CommandHandler("members", cmd_members_cmd))
    app.add_handler(CommandHandler("payments", cmd_payments_cmd))
    app.add_handler(CallbackQueryHandler(cb_nav, pattern=r"^nav_"))
    app.add_handler(CallbackQueryHandler(cb_submission, pattern=r"^(approve|decline)_"))
    app.add_handler(CallbackQueryHandler(cb_member_detail, pattern=r"^member_\d+$"))
    return app
