"""
=====================================================
  Facebook Messenger Bot + Admin Panel
  Vercel Serverless Entry Point -> Routes to app.py
=====================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

