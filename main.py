#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Smart Telegram Sender Bot - Main File
البوت الرئيسي مع كل الأوامر
✅ نسخة كاملة مع الإضافة الفورية لـ pending.json
"""

import asyncio
import json
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from api_manager import OptimizedAPIManager, smart_cache
from config import FINAL_STATUSES, TRANSITIONAL_STATUSES
from core import (
    continuous_monitor,
    format_number,
    get_status_description_ar,
    get_status_emoji,
    is_admin,
    load_monitored_accounts,
    parse_sender_data,
    wait_for_status_change,
)
from sheets.worker import start_sheet_worker
from stats import stats
from web_api.server import start_web_api

# ═══════════════════════════════════════════════════════════════
# 📝 Logging Configuration
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ⚙️ Load Configuration
# ═══════════════════════════════════════════════════════════════

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# ═══════════════════════════════════════════════════════════════
# 🎯 Global Constants
# ═══════════════════════════════════════════════════════════════

# 🎯 تحديد حد أقصى 10 خيوط مؤقتة في نفس الوقت
MAX_CONCURRENT_MONITORS = 10
monitoring_semaphore = asyncio.Semaphore(MAX_CONCURRENT_MONITORS)

# Global vars
telegram_app = None
api_manager = None

# ═══════════════════════════════════════════════════════════════
# 🎯 Bot Commands
# ═══════════════════════════════════════════════════════════════


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start - الرسالة الترحيبية"""
    user = update.effective_user
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(user.id, admin_ids):
        await update.message.reply_text("❌ عذراً، هذا البوت خاص بالمسؤولين.")
        return

    welcome_msg = (
        f"مرحباً {user.first_name}! 👋\n\n"
        "🚀 *بوت السيندرز المتطور*\n"
        "🧠 *Adaptive Hybrid Monitoring*\n\n"
        "*📝 طريقة الإضافة:*\n"
        "```\n"
        "email@gmail.com\n"
        "password123\n"
        "12345678\n"
        "اسحب 100\n"
        "يسيب 50\n"
        "```\n\n"
        "*✨ المميزات المتقدمة:*\n"
        "• 🎯 Strict ID Validation\n"
        "• 🚀 Temporary Burst Mode (60s)\n"
        "• 🧠 Smart TTL (2-10 دقيقة)\n"
        "• 🔄 Fallback Mechanism\n"
        "• 🌐 Bilingual Display\n"
        "• 🆕 Source Tracking (bot/manual)\n"
        "• 🆕 Auto-Discovery\n"
        "• 🆕 Instant Google Sheets Sync\n"
        "• 🆕 Web API Integration\n\n"
        "*⏱️ زمن الاستجابة: 3-10 ثوانٍ*\n\n"
        "*🔍 الأوامر:*\n"
        "`/search email@gmail.com`\n"
        "`/monitored` - الحسابات المراقبة\n"
        "`/stats` - الإحصائيات\n"
        "`/status` - حالة النظام"
    )

    await update.message.reply_text(welcome_msg, parse_mode="Markdown")


async def monitor_account_task(api_manager, email, msg, chat_id, group_name):
    """
    🚀 Task منفصل لمراقبة الحساب (يدعم 10 متزامنين)
    """
    # 🔥 انتظار مكان شاغر (الحد الأقصى 10)
    async with monitoring_semaphore:
        try:
            # 🆕 مراقبة الحساب
            monitoring_success, account_info = await wait_for_status_change(
                api_manager,
                email,
                msg,
                chat_id,
                group_name,
            )

            if account_info:
                status = account_info.get("Status", "غير محدد")
                status_ar = get_status_description_ar(status)
                account_id = account_info.get("idAccount", "N/A")

                result_text = (
                    f"✅ *تمت الإضافة بنجاح!*\n\n"
                    f"📧 `{email}`\n"
                    f"🆔 ID: `{account_id}`\n"
                    f"📊 *تمت الإضافة لـ Google Sheets*\n\n"
                    f"📊 *الحالة النهائية:*\n"
                    f"   `{status}`\n"
                    f"   {get_status_emoji(status)} {status_ar}\n\n"
                )

                # 🆕 عرض حالة الإضافة للمراقبة
                if status.upper() == "AVAILABLE":
                    group_name_acc = account_info.get("Group", "")
                    if group_name_acc == group_name:
                        result_text += f"🔄 *تم إدراجه في المراقبة (المصدر: البوت)*\n"
                    else:
                        result_text += f"ℹ️ *لم يتم إدراجه في المراقبة (الجروب مختلف: {group_name_acc})*\n"
                elif status.upper() in ["WRONG DETAILS", "BACKUP CODE WRONG"]:
                    result_text += f"⚠️ *تحتاج مراجعة!*\n"

                available = format_number(account_info.get("Available", "0"))
                taken = format_number(account_info.get("Taken", "0"))

                if available != "0" or taken != "0":
                    result_text += f"\n💵 المتاح: {available}\n✅ المسحوب: {taken}"

                await msg.edit_text(result_text, parse_mode="Markdown")
            else:
                await msg.edit_text(
                    f"⚠️ *تمت الإضافة لكن لم يتم العثور على الحساب*\n"
                    f"📧 `{email}`\n"
                    f"💡 جرب `/search {email}` بعد قليل",
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.exception(f"❌ Monitoring error: {email}")
            await msg.edit_text(f"❌ خطأ في المراقبة: {str(e)}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إضافة حساب جديد"""
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(update.effective_user.id, admin_ids):
        return

    # تجاهل الأوامر
    if update.message.text.startswith("/"):
        return

    # تحليل البيانات
    data = parse_sender_data(update.message.text)

    if not data["email"] or not data["password"]:
        await update.message.reply_text(
            "❌ بيانات ناقصة! تأكد من إدخال الإيميل والباسورد."
        )
        return

    msg = await update.message.reply_text(
        f"⏳ *جاري الإضافة...*\n📧 `{data['email']}`", parse_mode="Markdown"
    )

    try:
        # إضافة الحساب
        success, message = await api_manager.add_sender(
            email=data["email"],
            password=data["password"],
            backup_codes=data["codes"],
            amount_take=data["amount_take"],
            amount_keep=data["amount_keep"],
        )

        if success:
            await msg.edit_text(
                f"✅ *تمت الإضافة!*\n"
                f"📧 `{data['email']}`\n\n"
                f"🚀 *تفعيل BURST MODE...*\n"
                f"⏱️ متوقع: 3-10 ثوانٍ",
                parse_mode="Markdown",
            )

            # ✅ الحل: اعمل Task منفصل بدون انتظار
            asyncio.create_task(
                monitor_account_task(
                    api_manager,
                    data["email"],
                    msg,
                    update.effective_chat.id,
                    CONFIG["website"]["defaults"]["group_name"],
                )
            )

        else:
            await msg.edit_text(
                f"❌ *فشلت الإضافة*\n" f"📧 `{data['email']}`\n" f"⚠️ {message}",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.exception(f"❌ Error adding account: {data['email']}")
        await msg.edit_text(f"❌ خطأ غير متوقع: {str(e)}")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /search - البحث عن حساب"""
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(update.effective_user.id, admin_ids):
        return

    if not context.args:
        await update.message.reply_text(
            "📝 *الاستخدام:*\n`/search email@example.com`", parse_mode="Markdown"
        )
        return

    email = context.args[0].strip().lower()
    msg = await update.message.reply_text("🔍 جاري البحث...")

    try:
        result = await api_manager.search_sender_by_email(email)

        if result:
            status = result.get("Status", "غير محدد")
            status_ar = get_status_description_ar(status)
            account_id = result.get("idAccount", "N/A")

            status_type = (
                "نهائية ✅"
                if status in FINAL_STATUSES
                else (
                    "انتقالية ⏳" if status in TRANSITIONAL_STATUSES else "غير محددة ❓"
                )
            )

            text = (
                f"✅ *تم العثور على الحساب*\n\n"
                f"📧 `{result.get('Sender', email)}`\n"
                f"🆔 ID: `{account_id}`\n"
                f"👥 المجموعة: {result.get('Group', 'غير محدد')}\n\n"
                f"📊 *الحالة:* `{status}`\n"
                f"   {get_status_emoji(status)} {status_ar}\n"
                f"   🎯 النوع: {status_type}\n\n"
                f"📅 البداية: {format_number(result.get('Start', '0'))}\n"
                f"🕐 آخر تحديث: {result.get('Last Update', 'غير محدد')}\n"
                f"💰 اسحب: {format_number(result.get('Take', '0'))}\n"
                f"💸 يسيب: {format_number(result.get('Keep', '0'))}\n"
                f"✅ المسحوب: {format_number(result.get('Taken', '0'))}\n"
                f"💵 المتاح: {format_number(result.get('Available', '0'))}"
            )

            accounts = load_monitored_accounts()
            # تحقق بالـ ID
            is_monitored = any(
                d.get("account_id") == account_id for d in accounts.values()
            )

            if is_monitored:
                text += f"\n\n🔄 *هذا الحساب تحت المراقبة* (ID-based)"

            await msg.edit_text(text, parse_mode="Markdown")
        else:
            await msg.edit_text(
                f"❌ لم يتم العثور على الحساب\n📧 `{email}`", parse_mode="Markdown"
            )

    except Exception as e:
        logger.exception(f"❌ Search error: {email}")
        await msg.edit_text(f"❌ خطأ في البحث: {str(e)}")


async def monitored_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /monitored - عرض الحسابات المراقبة مع المصدر"""
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(update.effective_user.id, admin_ids):
        return

    accounts = load_monitored_accounts()

    if not accounts:
        await update.message.reply_text("📭 لا توجد حسابات تحت المراقبة حالياً")
        return

    text = f"🔄 *الحسابات المراقبة ({len(accounts)})*\n\n"

    for key, data in accounts.items():
        email = data.get("email", "unknown")
        account_id = data.get("account_id", "N/A")
        status = data["last_known_status"]
        status_ar = get_status_description_ar(status)

        # 🆕 عرض المصدر
        source = data.get("source", "manual")  # default للحسابات القديمة
        source_line = "🤖 من البوت" if source == "bot" else "👤 يدوي"

        text += (
            f"📧 `{email}`\n"
            f"   {source_line}\n"  # 🆕 NEW LINE
            f"   🆔 `{account_id}`\n"
            f"   📊 *{status}*\n"
            f"   {get_status_emoji(status)} {status_ar}\n\n"
        )

    text += f"⚡ Mode: Hybrid (TTL={smart_cache.cache_ttl:.0f}s)"

    await update.message.reply_text(text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /stats - عرض الإحصائيات"""
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(update.effective_user.id, admin_ids):
        return

    from datetime import datetime

    reset_time = datetime.fromisoformat(stats.last_reset)
    hours = max((datetime.now() - reset_time).seconds / 3600, 0.01)
    requests_per_hour = stats.total_requests / hours

    text = (
        "📊 *إحصائيات النظام*\n\n"
        f"📈 إجمالي الطلبات: {stats.total_requests}\n"
        f"⏱️ المعدل: {requests_per_hour:.1f} طلب/ساعة\n"
        f"🚀 Burst activations: {stats.burst_activations}\n"
        f"⚡ اكتشافات سريعة: {stats.fast_detections}\n"
        f"🎯 TTL adjustments: {stats.adaptive_adjustments}\n"
        f"🔄 CSRF refreshes: {stats.csrf_refreshes}\n"
        f"📦 Batch fetches: {stats.batch_fetches}\n"
        f"💾 Cache hits: {stats.cache_hits}\n"
        f"❌ Errors: {stats.errors}\n"
        f"💾 Cache rate: {(stats.cache_hits / max(stats.total_requests, 1) * 100):.1f}%\n\n"
        f"⚡ Mode: Adaptive Hybrid\n"
        f"🧠 Current TTL: {smart_cache.cache_ttl:.0f}s\n"
        f"🕐 منذ: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /status - حالة النظام"""
    admin_ids = CONFIG["telegram"].get("admin_ids", [])

    if not is_admin(update.effective_user.id, admin_ids):
        return

    from datetime import datetime

    accounts = load_monitored_accounts()
    csrf_valid = (
        api_manager.csrf_expires_at and datetime.now() < api_manager.csrf_expires_at
    )

    cache_age = "N/A"
    if smart_cache.cache_timestamp:
        age = (datetime.now() - smart_cache.cache_timestamp).total_seconds()
        cache_age = f"{age:.0f}s"

    api_enabled = CONFIG.get("api", {}).get("enabled", False)
    sheets_enabled = CONFIG.get("google_sheet", {}).get("enabled", False)

    text = (
        "*📊 حالة النظام*\n\n"
        f"🤖 البوت: ✅ شغال\n"
        f"⚡ Mode: *Adaptive Hybrid*\n"
        f"🌐 Web API: {'✅ نشط' if api_enabled else '❌ معطل'}\n"
        f"📊 Google Sheets: {'✅ نشط' if sheets_enabled else '❌ معطل'}\n\n"
        f"🔑 CSRF Token: {'✅ صالح' if csrf_valid else '⚠️ منتهي'}\n"
        f"💾 Cache Status: {'✅ نشط' if smart_cache.cache else '❌ فارغ'}\n"
        f"🕐 Cache Age: {cache_age}\n"
        f"🧠 Current TTL: {smart_cache.cache_ttl:.0f}s\n"
        f"🚀 Burst Mode: {'✅ نشط' if smart_cache.burst_mode_active else '❌ معطل'}\n"
        f"🔄 الحسابات المراقبة: {len(accounts)}\n\n"
        f"*⚡ التحسينات:*\n"
        f"• Strict ID validation: ✅\n"
        f"• Burst mode (60s): ✅\n"
        f"• Smart TTL (2-10min): ✅\n"
        f"• Source tracking: ✅\n"
        f"• Auto-discovery: ✅\n"
        f"• Instant Sheets sync: ✅\n"
        f"• Fallback mechanism: ✅\n"
        f"• Bilingual display: ✅\n"
        f"• Web API integration: {'✅' if api_enabled else '❌'}\n"
        f"• Google Sheets sync: {'✅' if sheets_enabled else '❌'}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════
# 🚀 Initialization & Main Function
# ═══════════════════════════════════════════════════════════════


async def post_init(application: Application):
    """
    التهيئة بعد بدء البوت
    """
    global api_manager

    logger.info("🔧 Initializing API Manager...")
    await api_manager.initialize()

    # 🆕 تمرير parameters للمراقب
    default_group_name = CONFIG["website"]["defaults"]["group_name"]
    admin_ids = CONFIG["telegram"].get("admin_ids", [])
    default_chat_id = admin_ids[0] if admin_ids else None

    logger.info("🔄 Starting background monitor (with auto-discovery)...")
    asyncio.create_task(
        continuous_monitor(
            api_manager,
            application.bot,
            default_group_name,  # 🆕 NEW PARAMETER
            default_chat_id,  # 🆕 NEW PARAMETER
        )
    )

    # تشغيل Web API
    if CONFIG.get("api", {}).get("enabled", False):
        logger.info("🌐 Starting Web API...")
        asyncio.create_task(start_web_api(CONFIG, api_manager))

    # تشغيل Google Sheets Worker
    if CONFIG.get("google_sheet", {}).get("enabled", False):
        logger.info("📊 Starting Google Sheets Worker...")
        asyncio.create_task(start_sheet_worker(CONFIG))

    logger.info("✅ System ready!")


def main():
    """
    🚀 تشغيل البوت الرئيسي
    """
    global telegram_app, api_manager

    print("\n" + "=" * 60)
    print("🚀 SMART SENDER BOT - ADAPTIVE HYBRID MODE")
    print("=" * 60)
    print("🧠 Architecture:")
    print("   • Smart Cache with adaptive TTL (2-10 min)")
    print("   • Strict ID Validation (account_id based)")
    print("   • Temporary Burst Mode (60s on new accounts)")
    print("   • Source Tracking (bot/manual)")
    print("   • Auto-Discovery (AVAILABLE + default group)")
    print("   • Instant Google Sheets Sync on ID detection")
    print("   • Fallback Mechanism (resilient to errors)")
    print("   • Bilingual Status Display (EN/AR)")
    print("   • Web API Integration (FastAPI/aiohttp)")
    print("\n📊 Intelligent & Efficient!")
    print("=" * 60 + "\n")

    # إنشاء API Manager
    api_manager = OptimizedAPIManager(CONFIG)

    # إنشاء تطبيق Telegram
    telegram_app = (
        Application.builder()
        .token(CONFIG["telegram"]["bot_token"])
        .post_init(post_init)
        .build()
    )

    # إضافة معالجات الأوامر
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("search", search_command))
    telegram_app.add_handler(CommandHandler("monitored", monitored_command))
    telegram_app.add_handler(CommandHandler("stats", stats_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    telegram_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("✅ Bot is running in Adaptive Hybrid Mode!")
    print("🧠 Smart TTL: 2-10 minutes (adaptive)")
    print("🚀 Burst Mode: 60s on new accounts")
    print("🎯 ID-based validation enabled")
    print("🆕 Source tracking: bot/manual")
    print("🆕 Auto-discovery: ON")
    print("🆕 Instant pending.json addition on ID detection")
    print("🌐 Web API: " + ("ON" if CONFIG.get("api", {}).get("enabled") else "OFF"))
    print(
        "📊 Google Sheets: "
        + ("ON" if CONFIG.get("google_sheet", {}).get("enabled") else "OFF")
    )
    print("📊 Check /stats for metrics\n")

    # تشغيل البوت
    telegram_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Bot stopped by user")
        stats.save()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.exception("❌ Fatal error occurred")
        stats.save()
    finally:
        import asyncio

        if api_manager:
            asyncio.run(api_manager.close())
