# 🔷 Matrix File Receiver
### দুটি Bot System — User Bot + Admin Bot

---

## ⚙️ Setup করুন

### Step 1 — দুটি Bot বানান (@BotFather)
1. Telegram → **@BotFather** → `/newbot`
2. প্রথম bot → নাম দিন → Token কপি করুন → `USER_BOT_TOKEN`
3. আবার `/newbot` → দ্বিতীয় bot → Token কপি → `ADMIN_BOT_TOKEN`

### Step 2 — আপনার Telegram ID নিন
**@userinfobot** → `/start` → `Id:` এর সংখ্যা = `ADMIN_TELEGRAM_ID`

### Step 3 — GitHub এ Upload করুন
1. github.com → New Repository → `matrix-bots`
2. এই zip এর সব ফাইল upload করুন → Commit

### Step 4 — Railway.app Deploy
1. railway.app → New Project → GitHub repo select
2. **Variables** tab → তিনটি variable দিন:

| Variable | Value |
|---|---|
| `USER_BOT_TOKEN` | User bot এর token |
| `ADMIN_BOT_TOKEN` | Admin bot এর token |
| `ADMIN_TELEGRAM_ID` | আপনার Telegram ID |

3. **Redeploy** → Logs এ দেখবেন: `🔷 Matrix File Receiver — LIVE`

---

## 📱 User Bot — Commands

| Button / Command | কাজ |
|---|---|
| 📁 ফাইল জমা দিন | ফাইল জমার নির্দেশনা |
| 📊 আমার সাবমিশন | সব সাবমিশন + স্ট্যাটাস |
| 💰 আমার পেমেন্ট | পেমেন্ট হিস্ট্রি |
| ℹ️ সাহায্য | সাহায্য |
| `.xlsx` ফাইল পাঠান | সরাসরি জমা |

---

## 👨‍💼 Admin Bot — Commands

| Command / Button | কাজ |
|---|---|
| /start | Dashboard (inline buttons সহ) |
| /pending | Pending সাবমিশন (Approve/Decline) |
| /history | সাবমিশন হিস্ট্রি |
| /members | সব সদস্য (Detail দেখা যাবে) |
| /payments | পেমেন্ট হিস্ট্রি |
| /sendpayment | পেমেন্ট পাঠান |
| /broadcast | সব সদস্যকে বার্তা পাঠান |
| /stats | বিস্তারিত পরিসংখ্যান |

---

## 💡 Notes
- **Database:** SQLite (Railway restart হলে data যাবে — ভবিষ্যতে Supabase দিয়ে fix করা যাবে)
- **Payment:** Bot notify করে, টাকা manually bKash/Nagad এ দিতে হবে
- **File Storage:** Telegram নিজেই রাখে, আলাদা storage লাগবে না
