#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🛣️ API Routes
Endpoints للـ Web API
"""

import logging
from aiohttp import web
from core import add_to_pending_queue

logger = logging.getLogger(__name__)


async def register_handler(request: web.Request):
    """
    POST /api/register
    استقبال طلب إضافة حساب جديد

    Request Body (JSON):
    {
        "email": "user@example.com",
        "password": "password123",
        "backup_codes": "12345678,87654321",  // اختياري
        "amount_take": "100",                  // اختياري
        "amount_keep": "50"                    // اختياري
    }

    Response (JSON):
    {
        "status": "success",
        "message": "Account added successfully",
        "email": "user@example.com"
    }
    """
    try:
        # قراءة البيانات
        data = await request.json()

        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()
        backup_codes = data.get("backup_codes", "")
        amount_take = data.get("amount_take", "")
        amount_keep = data.get("amount_keep", "")

        # Validation
        if not email or not password:
            return web.json_response(
                {"status": "error", "message": "Email and password are required"},
                status=400,
            )

        # الحصول على api_manager من الـ app
        api_manager = request.app["api_manager"]

        # إضافة الحساب
        success, message = await api_manager.add_sender(
            email=email,
            password=password,
            backup_codes=backup_codes,
            amount_take=amount_take,
            amount_keep=amount_keep,
        )

        if success:
            # 🆕 إضافة للـ queue
            add_to_pending_queue(email)

            logger.info(f"✅ Account added via API: {email}")

            return web.json_response(
                {
                    "status": "success",
                    "message": "Account added successfully and queued for Sheet sync",
                    "email": email,
                },
                status=200,
            )
        else:
            logger.warning(f"⚠️ Failed to add account via API: {email} - {message}")

            return web.json_response(
                {"status": "error", "message": message}, status=400
            )

    except Exception as e:
        logger.exception(f"❌ API Error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def health_handler(request: web.Request):
    """
    GET /health
    Health check endpoint

    Response (JSON):
    {
        "status": "ok",
        "service": "Smart Sender API"
    }
    """
    return web.json_response(
        {"status": "ok", "service": "Smart Sender API", "version": "1.0.0"}
    )


def setup_routes(app: web.Application):
    """
    إعداد جميع الـ routes
    """
    app.router.add_post("/api/register", register_handler)
    app.router.add_get("/health", health_handler)

    logger.info("✅ API routes configured")
