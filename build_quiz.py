import ast
from pathlib import Path


SOURCE = Path("quiz_questions.py")
OUTPUT = Path("quiz_questions.py")


def load_questions():
    text = SOURCE.read_text(encoding="utf-8")

    tree = ast.parse(text)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "QUIZ_QUESTIONS":
                    return ast.literal_eval(node.value)

    raise RuntimeError("QUIZ_QUESTIONS topilmadi")


def validate_questions(questions):
    seen = set()

    for number, item in enumerate(questions, 1):

        if not isinstance(item, tuple) or len(item) != 3:
            raise ValueError(
                f"{number}-savol formati noto‘g‘ri"
            )

        question, options, correct = item

        if not isinstance(question, str):
            raise ValueError(
                f"{number}-savol matni noto‘g‘ri"
            )

        if not isinstance(options, list) or len(options) != 3:
            raise ValueError(
                f"{number}-savolda 3 ta variant bo‘lishi kerak"
            )

        if correct not in (0, 1, 2):
            raise ValueError(
                f"{number}-savol correct indeksi noto‘g‘ri"
            )

        key = question.strip().lower()

        if key in seen:
            raise ValueError(
                f"Takrorlangan savol topildi: {question}"
            )

        seen.add(key)

    return True


def save_questions(questions):

    output = """# ============================================================
# GAME OF THRONES — VIKTORINA SAVOLLARI
# ============================================================

QUIZ_QUESTIONS = [
"""

    for question, options, correct in questions:

        output += "    (\n"
        output += f"        {question!r},\n"
        output += f"        {options!r},\n"
        output += f"        {correct}\n"
        output += "    ),\n\n"

    output += """]

if __name__ == "__main__":
    print("===================================")
    print("VIKTORINA BAZASI")
    print("Savollar:", len(QUIZ_QUESTIONS))
    print("===================================")
"""

    OUTPUT.write_text(output, encoding="utf-8")


def main():

    questions = load_questions()

    print("Eski savollar:", len(questions))

    validate_questions(questions)

    print("Mavjud savollar tekshirildi.")
    print("Takroriy savollar: 0")

    if len(questions) != 1200:
        print()
        print("Hozircha baza 1200 taga yetmagan.")
        print("Mavjud:", len(questions))
        print("Kerak:", 1200)
        print()
        print("Yangi savollar keyingi bosqichda qo‘shiladi.")
        return

    save_questions(questions)

    print()
    print("1200 TA SAVOL TAYYOR!")
    print("Takroriy savollar: 0")


if __name__ == "__main__":
    main()