#!/bin/bash
cd "$(dirname "$0")"
echo ""
echo " WarRoom v2 - Real Agentic System"
echo " Installing dependencies..."
pip install -r requirements.txt --quiet
echo ""
echo " Starting server on http://localhost:3000"
echo ""
python main.py
