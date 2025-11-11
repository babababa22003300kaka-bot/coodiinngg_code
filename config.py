#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚙️ Configuration & Constants
كل الإعدادات والثوابت في ملف واحد
"""

from typing import Set

# ═══════════════════════════════════════════════════════════════
# 🔧 Settings & Constants
# ═══════════════════════════════════════════════════════════════

# CSRF Token caching
CSRF_TOKEN_TTL = 1200  # 20 دقيقة

# Smart Cache Settings
CACHE_TTL_MIN = 60  # 2 دقيقة (عند نشاط عالي)
CACHE_TTL_NORMAL = 90  # 1.5 دقيقة (عادي)
CACHE_TTL_MAX = 120  # 2 دقيقة (عند هدوء)

# Burst Mode Settings
BURST_MODE_DURATION = 60  # مدة الـ Burst: 60 ثانية
BURST_MODE_INTERVAL = 2.5  # فاصل التحديث في وضع Burst: 2.5 ثانية

# Background monitor intervals
POLLING_INTERVALS = {
    "LOGGING": (3.1, 5.2),
    "LOGGED": (10, 30),
    "LOGGED IN": (10, 30),
    "AVAILABLE": (10, 300),
    "ACTIVE": (10, 300),
    "CODE SENT": (5, 15),
    "AMOUNT TAKEN": (300, 600),
    "WRONG DETAILS": (900, 1800),
    "NEW ACCOUNT": (600, 1200),
    "DISABLED": (1800, 3600),
    "NO TRANSFER ACCESS": (300, 600),
    "BACKUP CODE WRONG": (180, 300),
    "TRANSFER LIST IS FULL": (120, 240),
    "NO CLUB": (600, 1200),
    "GENERAL LOGIN ERROR": (300, 600),
    "ERROR": (600, 1200),
    "BLOCKED": (1800, 3600),
    "WAITING": (30, 60),
    "DEFAULT": (60, 120),
}

# Status classification
TRANSITIONAL_STATUSES: Set[str] = {
    "LOGGING",
    "LOGGED",
    "LOGGED IN",
    "WAITING",
    "NEW ACCOUNT",
}

FINAL_STATUSES: Set[str] = {
    "AVAILABLE",
    "ACTIVE",
    "WRONG DETAILS",
    "BACKUP CODE WRONG",
    "CODE SENT",
    "DISABLED",
    "NO TRANSFER ACCESS",
    "TRANSFER LIST IS FULL",
    "NO CLUB",
    "GENERAL LOGIN ERROR",
    "ERROR",
    "BLOCKED",
    "AMOUNT TAKEN",
}

# Database files
MONITORED_ACCOUNTS_FILE = "monitored_accounts.json"
STATS_FILE = "request_stats.json"

# Status Emojis
STATUS_EMOJIS = {
    "LOGGING": "🔄",
    "LOGGED": "✅",
    "LOGGED IN": "👤",
    "ACTIVE": "✅",
    "AVAILABLE": "💰",
    "CODE SENT": "📧",
    "AMOUNT TAKEN": "💸",
    "WRONG DETAILS": "⚠️",
    "NEW ACCOUNT": "🆕",
    "DISABLED": "🔒",
    "NO TRANSFER ACCESS": "🚫",
    "BACKUP CODE WRONG": "🔑",
    "TRANSFER LIST IS FULL": "📦",
    "NO CLUB": "⛔",
    "GENERAL LOGIN ERROR": "❗",
    "ERROR": "❌",
    "WAITING": "⏳",
    "BLOCKED": "🚫",
}

# Status Descriptions (Arabic)
STATUS_DESCRIPTIONS_AR = {
    "LOGGING": "جاري تسجيل الدخول",
    "LOGGED": "تم تسجيل الدخول",
    "LOGGED IN": "العميل دخل على الحساب",
    "ACTIVE": "نشط",
    "AVAILABLE": "متاح - الحساب تمام وجاهز للتحويلات",
    "CODE SENT": "الكود اتبعت",
    "AMOUNT TAKEN": "الفلوس (الكوينز) اتأخدت والكوينز اتنقلت",
    "WRONG DETAILS": "البيانات غلط - الإيميل أو الباسورد أو الـ EA Account مش صح",
    "NEW ACCOUNT": "حساب جديد - الحساب لسة جديد وما فيهوش لاعيبة كفاية",
    "DISABLED": "الحساب معطل",
    "NO TRANSFER ACCESS": "ماركت مقفول - ويب اب مقفول - Companion مقفول",
    "BACKUP CODE WRONG": "اكواد غلط - جدد اكواد وابعتهم تاني",
    "TRANSFER LIST IS FULL": "قائمة التحويلات كاملة - فضي ماركت شوية وابعت (لاعيبة)",
    "NO CLUB": "ما فيش كلوب",
    "GENERAL LOGIN ERROR": "مشكلة عامة في الدخول - خطأ عشوائي في اللوج إن",
    "ERROR": "خطأ عام",
    "WAITING": "منتظر",
    "BLOCKED": "محظور",
}
