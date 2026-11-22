"""Vercel·로컬 공통 진입점: uvicorn app:app"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server.main import app  # noqa: E402,F401
