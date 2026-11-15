"""
TEST SUITE FOR 3-QADAM: DONAT TIZIMINI SODDALASHTIRISH
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from handlers.donate_handler import donate_menu_keyboard


def test_step3_donate_simplification():
    print("=" * 60)
    print("RUNNING 3-QADAM DONAT SODDALASHTIRISH TESTLARI")
    print("=" * 60)

    # 1. Sotuvda faqat 3 ta paket qolganligi
    assert len(config.ACTIVE_DONATE_TIERS) == 3, f"ACTIVE_DONATE_TIERS 3 ta bo'lishi kerak, hozir: {len(config.ACTIVE_DONATE_TIERS)}"
    assert "starter_pack" in config.ACTIVE_DONATE_TIERS
    assert "knight" in config.ACTIVE_DONATE_TIERS
    assert "premium_pass" in config.ACTIVE_DONATE_TIERS
    print("[PASS] 1. ACTIVE_DONATE_TIERS da faqat 3 ta paket: starter_pack, knight, premium_pass.")

    # 2. Hech bir sotuvdagi paketda ajdar yoki pulga askar sotilmasligi
    for t_id in config.ACTIVE_DONATE_TIERS:
        t = config.DONATE_TIERS[t_id]
        assert not t.get("is_troops"), f"{t_id} askar sotmasligi shart!"
        assert "dragon" not in t.get("bonus", {}), f"{t_id} ajdar sotmasligi shart!"
        assert t.get("infantry", 0) == 0, f"{t_id} to'g'ridan-to'g'ri piyoda sotmasligi shart!"
        assert t.get("cavalry", 0) == 0, f"{t_id} to'g'ridan-to'g'ri otliq sotmasligi shart!"
    print("[PASS] 2. Barcha sotuvdagi paketlar tekshirildi: ajdarlar va pullik askarlar yo'q.")

    # 3. Menyu klaviaturasida faqat 3 ta paket va "Mening so'rovlarim" mavjudligi
    kb = donate_menu_keyboard()
    pick_callbacks = []
    has_troops_btn = False
    has_my_requests = False

    for row in kb.inline_keyboard:
        for btn in row:
            cd = btn.callback_data or ""
            if cd.startswith("donate_pick:"):
                pick_callbacks.append(cd.replace("donate_pick:", ""))
            if "donate_troops" in cd:
                has_troops_btn = True
            if cd == "donate_my_requests":
                has_my_requests = True

    assert not has_troops_btn, "Menyuda 'Qo'shin sotib olish' tugmasi mutlaqo bo'lmasligi shart!"
    assert has_my_requests, "Menyuda 'Mening so'rovlarim' tugmasi bo'lishi shart!"
    assert set(pick_callbacks) == set(config.ACTIVE_DONATE_TIERS), f"Menyuda faqat 3 ta paket bo'lishi kerak! Hozir: {pick_callbacks}"
    print("[PASS] 3. Donat menyusida faqat 3 ta paket va 'Mening so'rovlarim' ko'rsatilmoqda (qo'shin sotib olish paneli yashirilgan).")

    # 4. Doimiy daromad bonusi (+25%) sotuvdagi 3 ta paketda yo'qligi
    for t_id in config.ACTIVE_DONATE_TIERS:
        t = config.DONATE_TIERS[t_id]
        assert t.get("vip_tier") != "sovereign", f"{t_id} da doimiy daromad bonusi bo'lmasligi kerak!"
    print("[PASS] 4. Sotuvdagi hech bir paketda doimiy +25% daromad bonusi yo'q (u faqat yashirilgan sovereign da).")

    print("\n>>> 3-QADAM DONAT TIZIMI SODDALASHTIRISH TESTLARI 100% MUVAFFAQIShIYATLI O'TDI! <<<\n")


if __name__ == "__main__":
    test_step3_donate_simplification()
