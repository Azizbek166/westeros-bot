"""
TEST SUITE FOR 1-QADAM: XAVFSIZLIK
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from api.main import app


def test_step1_security_features():
    print("=" * 60)
    print("RUNNING 1-QADAM XAVFSIZLIK TESTLARI")
    print("=" * 60)

    # 1. Chek rasmlari ochiq static papkada bo'lmasligi kerak
    static_receipts_dir = os.path.join("static", "uploads", "receipts")
    assert not os.path.exists(static_receipts_dir) or len(os.listdir(static_receipts_dir)) == 0, \
        "static/uploads/receipts da hech qanday fayl bo'lmasligi shart!"
    print("[PASS] 1. static/uploads/receipts ochiq papkasida rasmlar yo'q.")

    # 2. config.py da karta va egasi standart qiymati bo'lmasligi
    cfg_text = (config.BASE_DIR / "config.py").read_text(encoding="utf-8")
    assert "5614688804228251" not in cfg_text, "Karta raqami config.py da qattiq yozilmagan bo'lishi kerak!"
    assert "Shavkatov Azizbek" not in cfg_text, "Karta egasi ismi config.py da qattiq yozilmagan bo'lishi kerak!"
    print("[PASS] 2. Karta ma'lumotlari config.py da qattiq saqlanmagan (.env va DB dan o'qiladi).")

    # 3. ADMIN_IDS ni config.py ga qayta yozish to'xtatilgani
    old_admins = list(config.ADMIN_IDS)
    config.save_admin_id(999999999)
    cfg_text_after = (config.BASE_DIR / "config.py").read_text(encoding="utf-8")
    assert "999999999" not in cfg_text_after, "config.save_admin_id config.py ni o'zgartirmasligi shart!"
    config.remove_admin_id(999999999)
    print("[PASS] 3. ADMIN_IDS ni config.py ga yozish to'xtatilgan.")

    # 4. Production rejimida /api/docs va openapi_url o'chirilgani
    os.environ["ENVIRONMENT"] = "production"
    assert app.docs_url is None, "Production rejimida /api/docs o'chirilgan bo'lishi shart!"
    assert app.openapi_url is None, "Production rejimida openapi_url o'chirilgan bo'lishi shart!"
    print("[PASS] 4. /api/docs va /openapi.json productionda o'chirilgan.")

    print("\n>>> 1-QADAM XAVFSIZLIK TESTLARI 100% MUVAFFAQIShIYATLI O'TDI! <<<\n")


if __name__ == "__main__":
    test_step1_security_features()
