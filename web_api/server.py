#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Web API Server
FastAPI server لاستقبال طلبات الإضافة
"""

import logging
from typing import Dict

from aiohttp import web
from .routes import setup_routes

logger = logging.getLogger(__name__)


async def start_web_api(config: Dict, api_manager):
    """
    تشغيل Web API server

    Args:
        config: إعدادات التطبيق
        api_manager: OptimizedAPIManager instance
    """
    app = web.Application()

    # تخزين الـ config و api_manager في الـ app
    app["config"] = config
    app["api_manager"] = api_manager

    # إعداد الـ routes
    setup_routes(app)

    # الإعدادات
    api_config = config.get("api", {})
    host = api_config.get("host", "0.0.0.0")
    port = api_config.get("port", 8080)

    # تشغيل الـ server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"✅ Web API running on http://{host}:{port}")
    logger.info(f"📝 Endpoint: POST http://{host}:{port}/api/register")
    logger.info(f"💚 Health: GET http://{host}:{port}/health")
