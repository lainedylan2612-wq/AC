@echo off
cd /d %~dp0
python monitor.py >> data\monitor.log 2>&1
