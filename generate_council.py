import random

situations = [
    "Qirollikda oziq-ovqat tanqisligi yuzaga keldi.",
    "Xazinadagi mablag‘ kamayib ketdi.",
    "Savdogarlar qirollikdan ketishni boshladi.",
    "Chegara hududida tartibsizliklar boshlandi.",
    "Bir viloyatda hosil juda kam bo‘ldi.",
    "Qirollikdagi yo‘llar yomonlashdi.",
    "Port orqali savdo kamayib ketdi.",
    "Mahalliy lord qo‘shimcha yordam so‘ramoqda.",
    "Xazinaga keladigan soliqlar kamaydi.",
    "Qirollikda savdogarlar o‘rtasida kelishmovchilik chiqdi.",
    "Chegaradagi qal'a qo‘shimcha ta'minot so‘radi.",
    "Bir shahar aholisi narxlarning oshishidan shikoyat qildi.",
    "Qirollikda yangi bozor ochish taklifi berildi.",
    "Savdo kemalari kechikib kelmoqda.",
    "Bir viloyatda ishchilar yetishmayapti.",
    "Qirollikning oltin zaxirasi kamaymoqda.",
    "Dehqonlar yangi soliqdan norozi bo‘ldi.",
    "Bir lord qirol saroyidan yordam so‘radi.",
    "Qirollikning muhim ko‘prigi ta'mirga muhtoj.",
    "Chegaradagi savdo yo‘li xavfsizligini kuchaytirish kerak."
]

decisions = [
    (
        "Muammoni bosqichma-bosqich hal qilish",
        "Darhol barcha soliqlarni oshirish",
        "Barcha savdoni vaqtincha to‘xtatish"
    ),
    (
        "Savdogarlarga qulay sharoit yaratish",
        "Savdogarlardan qo‘shimcha katta soliq olish",
        "Bozorlarni yopish"
    ),
    (
        "Xazinadan zarur mablag‘ ajratish",
        "Barcha xarajatlarni birdan to‘xtatish",
        "Aholiga yangi katta soliq solish"
    ),
    (
        "Muammoni tekshirish uchun vakil yuborish",
        "Tekshirmasdan jazolash",
        "Muammoni butunlay e'tiborsiz qoldirish"
    ),
    (
        "Savdo va ishlab chiqarishni qo‘llab-quvvatlash",
        "Savdoni cheklash",
        "Bozorlarni yopish"
    )
]

question_forms = [
    "Nima qilasiz?",
    "Qirol sifatida qanday qaror qabul qilasiz?",
    "Bu vaziyatda eng to‘g‘ri qaroringiz qanday bo‘ladi?",
    "Muammoni hal qilish uchun nima buyurasiz?",
    "Kengash a'zolari sizdan qaror kutmoqda. Nima qilasiz?"
]

questions = []

random.seed(2026)

# 20 vaziyat × 5 qaror × 5 savol shakli = 500 ta noyob savol
for situation in situations:
    for decision in decisions:
        for form in question_forms:

            question_text = situation + " " + form

            options = [
                decision[0],
                decision[1],
                decision[2]
            ]

            # Birinchi variantni to‘g‘ri javob qilamiz
            correct_text = decision[0]

            # Javoblarni aralashtiramiz
            random.shuffle(options)

            # Aralashtirilgandan keyin to‘g‘ri javob indeksini topamiz
            correct = options.index(correct_text)

            reward = random.choice([
                80,
                100,
                120,
                150,
                180,
                200
            ])

            questions.append(
                (
                    question_text,
                    options,
                    correct,
                    reward
                )
            )

# Savollarni yana aralashtiramiz
random.shuffle(questions)

# council_questions.py faylini yaratamiz
with open("council_questions.py", "w", encoding="utf-8") as file:

    file.write("COUNCIL_QUESTIONS = [\n")

    for question in questions:

        file.write("    (\n")
        file.write(f"        {question[0]!r},\n")
        file.write(f"        {question[1]!r},\n")
        file.write(f"        {question[2]},\n")
        file.write(f"        {question[3]}\n")
        file.write("    ),\n")

    file.write("]\n")

print("===================================")
print("500 ta KENGASH savoli yaratildi!")
print("Jami savollar:", len(questions))
print("council_questions.py yangilandi")
print("===================================")