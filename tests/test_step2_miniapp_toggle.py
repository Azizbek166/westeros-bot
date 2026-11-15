"""
TEST SUITE FOR 2-QADAM: MINI APPNI O'CHIRISH (FAQAT BOT ISHLAYDI)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from keyboards.menus import main_menu_keyboard, legacy_main_menu_keyboard


def test_step2_miniapp_toggle():
    print("=" * 60)
    print("RUNNING 2-QADAM MINI APP TOGGLE TESTLARI")
    print("=" * 60)

    # 1. ENABLE_MINIAPP=False bo'lganda MINIAPP_PRIMARY_INTERFACE qat'iy False bo'lishi
    assert config.ENABLE_MINIAPP is False, "ENABLE_MINIAPP .env da false bo'lishi shart!"
    assert config.MINIAPP_PRIMARY_INTERFACE is False, "ENABLE_MINIAPP=False bo'lganda MINIAPP_PRIMARY_INTERFACE ham False bo'lishi kerak!"
    print("[PASS] 1. ENABLE_MINIAPP=False va MINIAPP_PRIMARY_INTERFACE=False tasdiqlandi.")

    # 2. main_menu_keyboard da hech qanday web_app tugmasi bo'lmasligi
    kb = main_menu_keyboard()
    has_webapp_button = False
    for row in kb.inline_keyboard:
        for btn in row:
            if getattr(btn, "web_app", None) is not None:
                has_webapp_button = True
                break
    assert not has_webapp_button, "ENABLE_MINIAPP=False bo'lganda main_menu_keyboard da web_app tugmasi bo'lmasligi kerak!"
    print("[PASS] 2. Asosiy menyudan Mini App tugmalari yashirildi (faqat Telegram inline tugmalari qoldi).")

    # 3. legacy_main_menu_keyboard da ham web_app tugmasi chiqmasligi
    legacy_kb = legacy_main_menu_keyboard()
    legacy_has_webapp = False
    for row in legacy_kb.inline_keyboard:
        for btn in row:
            if getattr(btn, "web_app", None) is not None:
                legacy_has_webapp = True
                break
    assert not legacy_has_webapp, "legacy_main_menu_keyboard da ham web_app tugmasi bo'lmasligi kerak!"
    print("[PASS] 3. Legacy menyudan ham Mini App tugmalari to'liq olib tashlandi.")

    print("\n>>> 2-QADAM MINI APP O'CHIRISH TESTLARI 100% MUVAFFAQIShIYATLI O'TDI! <<<\n")


if __name__ == "__main__":
    test_step2_miniapp_toggle()
