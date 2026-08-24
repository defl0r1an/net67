@echo off
rem Otkryvaet viki net67 v brauzere.
cd /d "%~dp0"
py -3.14 serve.py 2>nul || py serve.py 2>nul || python serve.py
pause
