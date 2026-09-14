import ast
from pathlib import Path

FILE = Path("quiz_questions.py")

def load():
    text = FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "QUIZ_QUESTIONS":
                    return ast.literal_eval(node.value)

    raise RuntimeError("QUIZ_QUESTIONS topilmadi")

def save(questions):
    text = "# 1200 TA GAME OF THRONES SAVOLLARI\n\nQUIZ_QUESTIONS = [\n"

    for q, options, correct in questions:
        text += f"    ({q!r}, {options!r}, {correct}),\n"

    text += "]\n"
    FILE.write_text(text, encoding="utf-8")

questions = load()

print("Hozirgi savollar:", len(questions))

seen = {q.strip().lower() for q, _, _ in questions}

# Yangi savollar shu ro'yxatga qo'shiladi
NEW_QUESTIONS = [
    # KEYINGI BOSQICHDA 200 TA YANGI SAVOL SHU YERGA QO'SHILADI
]

for item in NEW_QUESTIONS:
    if item[0].strip().lower() not in seen:
        questions.append(item)
        seen.add(item[0].strip().lower())

save(questions)

print("Yakuniy savollar:", len(questions))
print("Yetishmayapti:", max(0, 1200 - len(questions)))