@echo off
title Westeros Bot Runner
:loop
echo [%date% %time%] Bot ishga tushirilmoqda...
python bot.py
echo [%date% %time%] Bot to'xtadi. 5 soniyadan so'ng qayta ishga tushadi...
timeout /t 5
goto loop
