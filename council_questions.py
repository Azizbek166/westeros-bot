import random

# ============================================================
# QIROLLIK KENGASHI — 500 TA STRATEGIK MASALA
# ============================================================

_situations = [
    "Qirollikda oziq-ovqat tanqisligi yuzaga keldi.",
    "Xazinadagi mablag' kamayib ketdi.",
    "Savdogarlar qirollikdan ketishni boshladi.",
    "Chegara hududida tartibsizliklar boshlandi.",
    "Bir viloyatda hosil juda kam bo'ldi.",
    "Qirollikdagi yo'llar yomonlashdi.",
    "Port orqali savdo kamayib ketdi.",
    "Mahalliy lord qo'shimcha yordam so'ramoqda.",
    "Xazinaga keladigan soliqlar kamaydi.",
    "Qirollikda savdogarlar o'rtasida kelishmovchilik chiqdi.",
    "Chegaradagi qal'a qo'shimcha ta'minot so'radi.",
    "Bir shahar aholisi narxlarning oshishidan shikoyat qildi.",
    "Qirollikda yangi bozor ochish taklifi berildi.",
    "Savdo kemalari kechikib kelmoqda.",
    "Bir viloyatda ishchilar yetishmayapti.",
    "Qirollikning oltin zaxirasi kamaymoqda.",
    "Dehqonlar yangi soliqdan norozi bo'ldi.",
    "Bir lord qirol saroyidan yordam so'radi.",
    "Qirollikning muhim ko'prigi ta'mirga muhtoj.",
    "Chegaradagi savdo yo'li xavfsizligini kuchaytirish kerak.",
    "Poytaxtda non narxi keskin oshdi.",
    "Bir qal'ada oziq-ovqat zaxirasi kamaydi.",
    "Savdo yo'lida qaroqchilar ko'paydi.",
    "Qirollikda yangi hunarmandlar gildiyasi tashkil qilindi.",
    "Bir shahar qo'shimcha qo'riqchilar so'ramoqda.",
    "Daryo orqali yuk tashish qiyinlashdi.",
    "Qirollikda temir yetishmovchiligi boshlandi.",
    "Bir viloyatda suv ta'minoti muammosi yuzaga keldi.",
    "Qirol xazinasiga kutilgan to'lov kelmadi.",
    "Chegara lordlari yangi kelishuv taklif qildi.",
    "Savdogarlar bojxona to'lovlarini kamaytirishni so'radi.",
    "Bir shaharda omborlar to'lib ketdi.",
    "Qirollikda kumush qazib olish kamaydi.",
    "Dehqonlar urug'lik yetishmasligidan shikoyat qildi.",
    "Bir portda kemalar uchun joy yetishmayapti.",
    "Qirollikning eski yo'li qayta qurilishi kerak.",
    "Bir lord askarlar uchun ta'minot so'radi.",
    "Shahar aholisi yangi bozor qurishni taklif qildi.",
    "Qirollikda chorva soni kamaymoqda.",
    "Savdogarlar yangi savdo yo'lini ochishni taklif qildi.",
    "Bir viloyatda soliqlarni yig'ish qiyinlashdi.",
    "Poytaxtdagi bozor nazoratga muhtoj.",
    "Chegara hududida yangi qishloq tashkil qilindi.",
    "Qirollikda yog'och zaxirasi kamaydi.",
    "Bir qal'a devorlarini ta'mirlash kerak.",
    "Savdo kemalaridan biri zarar ko'rdi.",
    "Qirollikda ishchilar maoshini oshirish talabi paydo bo'ldi.",
    "Bir viloyatda oltin koni topildi.",
    "Poytaxtda yangi savdo markazi qurish taklifi berildi.",
    "Qish yaqinlashmoqda, oziq-ovqat zaxiralarini ko'paytirish kerak."
]

_decisions = [
    (
        "Muammoni bosqichma-bosqich hal qilish",
        "Darhol barcha soliqlarni oshirish",
        "Barcha savdoni vaqtincha to'xtatish"
    ),
    (
        "Savdogarlarga qulay sharoit yaratish",
        "Savdogarlardan qo'shimcha katta soliq olish",
        "Bozorlarni yopish"
    ),
    (
        "Xazinadan zarur mablag' ajratish",
        "Barcha xarajatlarni birdan to'xtatish",
        "Aholiga yangi katta soliq solish"
    ),
    (
        "Muammoni tekshirish uchun vakil yuborish",
        "Tekshirmasdan jazolash",
        "Muammoni butunlay e'tiborsiz qoldirish"
    ),
    (
        "Savdo va ishlab chiqarishni qo'llab-quvvatlash",
        "Savdoni cheklash",
        "Bozorlarni yopish"
    ),
    (
        "Mahalliy lordlar bilan maslahatlashish",
        "Lordlarni jazolash",
        "Muammoni e'tiborsiz qoldirish"
    ),
    (
        "Zaxiradagi resurslardan foydalanish",
        "Barcha zaxiralarni sotish",
        "Resurslarni umuman ishlatmaslik"
    ),
    (
        "Yangi savdo yo'llarini rivojlantirish",
        "Savdo yo'llarini yopish",
        "Savdogarlarni cheklash"
    ),
    (
        "Ta'mirlash uchun mablag' ajratish",
        "Ta'mirlashni kechiktirish",
        "Obyektni butunlay yopish"
    ),
    (
        "Aholiga vaqtinchalik yordam berish",
        "Yangi soliq joriy qilish",
        "Yordam bermaslik"
    ),
]

_question_templates = [
    "{} Nima qilasiz?",
    "{} Bunday vaziyatda qanday qaror qabul qilasiz?",
    "{} Qirollik manfaatlari uchun qaysi yo'lni tanlaysiz?",
    "{} Sizning qaroringiz qanday bo'ladi?",
    "{} Xazinani va xalqni hisobga olib nima qilasiz?",
    "{} Bu muammoni qanday hal qilasiz?",
    "{} Lordlar kengashida qanday qaror taklif qilasiz?",
    "{} Qirollik barqarorligi uchun nima qilasiz?",
    "{} Savdo va iqtisodiyotni hisobga olib qanday yo'l tutasiz?",
    "{} Sizningcha, eng to'g'ri qaror qaysi?"
]

def _generate_council_questions():
    rng = random.Random(2026)
    questions = []
    for situation in _situations:
        for template in _question_templates:
            q_text = template.format(situation)
            decision = rng.choice(_decisions)
            options = list(decision)
            correct_text = options[0]
            rng.shuffle(options)
            correct_idx = options.index(correct_text)
            reward = rng.choice([80, 100, 120, 150, 180, 200])
            questions.append((q_text, options, correct_idx, reward))
    rng.shuffle(questions)
    return questions[:500]

COUNCIL_QUESTIONS = _generate_council_questions()