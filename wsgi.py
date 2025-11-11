#!/usr/bin/env python3
"""
WSGI configuration for PythonAnywhere

هذا الملف هو entry point لـ uWSGI على PythonAnywhere
"""

import sys
import os

# إضافة مسار المشروع
project_home = '/home/zizo32332/mysite'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# تحميل Flask app من app.py
from app import flask_app as application

# PythonAnywhere يتوقع متغير اسمه 'application'
# application = flask_app  # Already imported above
