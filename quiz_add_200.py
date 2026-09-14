from pathlib import Path
import ast

NEW_QUESTIONS = [
("Aegon I Targaryenning ajdari nima edi?",["Balerion","Vhagar","Meraxes"],0),
("Visenya Targaryenning ajdari nima edi?",["Vhagar","Balerion","Drogon"],0),
("Rhaenys Targaryenning ajdari nima edi?",["Meraxes","Vhagar","Caraxes"],0),
("Balerionning laqabi nima edi?",["The Black Dread","The Red Dragon","The Golden"],0),
("Daenerysning uchta ajdari qanday nomlangan?",["Drogon, Rhaegal, Viserion","Balerion, Vhagar, Meraxes","Caraxes, Syrax, Meleys"],0),
("Caraxes kimning ajdari edi?",["Daemon Targaryen","Aemond Targaryen","Rhaegar Targaryen"],0),
("Vhagar kimning ajdari bo'lgan?",["Aemond Targaryen","Jon Snow","Viserys Targaryen"],0),
("Syrax kimning ajdari edi?",["Rhaenyra Targaryen","Daenerys Targaryen","Visenya Targaryen"],0),
("Meleys kimning ajdari edi?",["Rhaenys Targaryen","Rhaenyra Targaryen","Alicent Hightower"],0),
("House of the Dragon voqealari qaysi sulola haqida?",["Targaryenlar","Starklar","Lannisterlar"],0),

("Daemon Targaryen kimning ukasi edi?",["Viserys I","Robert Baratheon","Aegon II"],0),
("Rhaenyra Targaryenning otasi kim?",["Viserys I Targaryen","Daemon Targaryen","Aegon II"],0),
("Alicent Hightowerning otasi kim?",["Otto Hightower","Corlys Velaryon","Criston Cole"],0),
("Otto Hightower qaysi lavozimni egallagan?",["Hand of the King","Lord Commander","Master of Ships"],0),
("Corlys Velaryon qanday laqab bilan tanilgan?",["The Sea Snake","The Dragon","The Kraken"],0),
("Velaryonlar qaysi joy bilan bog'liq?",["Driftmark","Winterfell","Casterly Rock"],0),
("Laena Velaryonning ajdari nima edi?",["Vhagar","Drogon","Syrax"],0),
("Laenor Velaryon qaysi ajdarga ega edi?",["Seasmoke","Caraxes","Balerion"],0),
("Criston Cole qaysi tashkilotga a'zo edi?",["Kingsguard","Night's Watch","Faith Militant"],0),
("Aegon II Targaryen kimning o'g'li?",["Viserys I","Daemon","Corlys"],0),

("The Dance of the Dragons nimaga sabab bo'lgan?",["Targaryen fuqarolar urushi","White Walkerlar hujumi","Dorne urushi"],0),
("Rhaenyra Targaryenning o'g'illaridan biri kim?",["Jacaerys Velaryon","Joffrey Baratheon","Robb Stark"],0),
("Rhaenyra Targaryenning ajdari nima edi?",["Syrax","Vhagar","Drogon"],0),
("Aemond Targaryenning ajdari nima?",["Vhagar","Caraxes","Meraxes"],0),
("Aemond Targaryenning bir ko'zi nima sababli yo'qolgan?",["Bolalikdagi janjal","Urushda","Ajdar hujumida"],0),
("Daemon Targaryenning qilichi nima deb atalgan?",["Dark Sister","Ice","Longclaw"],0),
("Valyrian po'latidan yasalgan qilichlardan biri qaysi?",["Dark Sister","Widow's Wail","Needle"],0),
("Blackfyre kimlarning mashhur qilichi?",["Targaryenlar","Starklar","Tyrellar"],0),
("Longclaw kimga tegishli bo'lgan?",["Jon Snow","Ned Stark","Robb Stark"],0),
("Needle qilichi kimniki?",["Arya Stark","Sansa Stark","Brienne"],0),

("Winterfellning asosiy xudosi qaysi?",["Old Gods","Many-Faced God","R'hllor"],0),
("Night's Watchning qasamyodi qayerda bajariladi?",["The Wall","Winterfell","Dragonstone"],0),
("Night's Watch kiyimi asosan qanday rangda?",["Qora","Oq","Qizil"],0),
("Night's Watch a'zolari qanday ataladi?",["Brothers","Kingsguard","Ironborn"],0),
("Lord Commander Mormontning laqabi nima?",["Old Bear","Blackfish","The Hound"],0),
("Castle Black qayerda joylashgan?",["The Wall","The Vale","The Reach"],0),
("Eastwatch-by-the-Sea nimaning bir qismi?",["The Wall qal'alari","King's Landing","Iron Islands"],0),
("The Wall kim tomonidan qurilgan deb hisoblanadi?",["Brandon the Builder","Aegon I","Harren the Black"],0),
("The Wallning asosiy vazifasi nima?",["Shimoldan keladigan xavfdan himoya","Dorne bilan savdo","Qirolni himoya qilish"],0),
("White Walkers nimadan zaif?",["Dragonglass va Valyrian steel","Oddiy yog'och","Oltin"],0),

("Dragonglass yana qanday ataladi?",["Obsidian","Valyrian steel","Iron"],0),
("Samwell Tarly White Walkerni nima bilan o'ldirgan?",["Dragonglass","Longclaw","Oddiy qilich"],0),
("Jon Snow White Walkerni nima bilan o'ldirgan?",["Longclaw","Needle","Ice"],0),
("White Walkersning yetakchisi kim?",["Night King","Night's Watch Lord Commander","The Hound"],0),
("Wights nima?",["O'lganlarning tiriltirilgan jasadlari","Ajdarlar","Dothrakilar"],0),
("Night King qaysi mavjudotlarni boshqara olgan?",["Wights","Dragons only","Krakenlar"],0),
("Bran Starkning ko'rish qobiliyati qanday ataladi?",["Greensight","Bloodraven","Dragon sight"],0),
("Three-Eyed Ravenning oldingi nomi kim edi?",["Brynden Rivers","Bran Stark","Howland Reed"],0),
("Brynden Riversning laqabi nima edi?",["Bloodraven","Blackfish","The Raven King"],0),
("Bloodraven qaysi xonadonga mansub edi?",["Targaryen","Stark","Lannister"],0),

("Gendry kimning noqonuniy o'g'li?",["Robert Baratheon","Ned Stark","Tywin Lannister"],0),
("Gendry qaysi kasbni bilgan?",["Temirchi","Maester","Dengizchi"],0),
("Davos Seaworthning laqabi nima?",["The Onion Knight","The Hound","Blackfish"],0),
("Davos Stannisga qanday xizmat qilgan?",["Maslahatchi va qo'mondon","Maester","Kingsguard"],0),
("Stannisning qizi kim?",["Shireen Baratheon","Myrcella Baratheon","Margaery Tyrell"],0),
("Shireenning onasi kim?",["Selyse Florent","Cersei Lannister","Catelyn Stark"],0),
("Melisandre qaysi xudoga sig'ingan?",["R'hllor","Old Gods","Many-Faced God"],0),
("R'hllor yana qanday nom bilan tanilgan?",["Lord of Light","God of Death","Old King"],0),
("Thoros of Myr qaysi xudoga xizmat qilgan?",["R'hllor","Old Gods","Drowned God"],0),
("Beric Dondarrion necha marta tirilgan?",["Bir necha marta","Hech qachon","Faqat bir marta"],0),

("Brotherhood Without Banners kim boshchiligida bo'lgan?",["Beric Dondarrion","Tyrion Lannister","Jaime Lannister"],0),
("Thoros of Myr Bericni nima bilan tiriltirgan?",["R'hllorning kuchi orqali","Ajdar qoni bilan","Sehrli qilich bilan"],0),
("Jorah Mormont qaysi xonadondan?",["Mormont","Stark","Tully"],0),
("Jeor Mormont Jorahning kimligi?",["Otasi","Akasi","Amakisi"],0),
("Jorah Daenerysga qanday xizmat qilgan?",["Maslahatchi va qo'riqchi","Maester","Lord Commander"],0),
("Jorah Mormontning ajdodiy qal'asi qayerda?",["Bear Island","Dragonstone","Pike"],0),
("Grey Wormning asl ismi qanday?",["Grey Worm","Worm","Unsullied"],0),
("Unsullied qayerda tayyorlangan?",["Astapor","Winterfell","Braavos"],0),
("Astapor qaysi hududda?",["Slaver's Bay","The North","The Reach"],0),
("Yunkai qaysi hududda joylashgan?",["Slaver's Bay","The Vale","Dorne"],0),

("Meereen qanday shahar edi?",["Slaver's Baydagi shahar","The North qal'asi","Iron Islands qal'asi"],0),
("Daenerys Meereenni kimlardan ozod qilgan?",["Qul egalari","Starklar","Night's Watch"],0),
("Daenerysning unvonlaridan biri nima?",["Breaker of Chains","Kingslayer","The Hound"],0),
("Daenerysning asosiy shiori qaysi?",["Fire and Blood","Winter Is Coming","Hear Me Roar"],0),
("Viserys Targaryen Daenerysga kim bo'lgan?",["Akasi","Otasi","Amakisi"],0),
("Viserys Targaryen qanday tojni xohlagan?",["Iron Throne","Seastone Chair","Dragonstone"],0),
("Rhaegar Targaryen Daenerysga kim bo'lgan?",["Akasi","Otasi","Amakisi"],0),
("Rhaegar Targaryenning o'g'illaridan biri kim?",["Aegon Targaryen","Joffrey Baratheon","Tommen Baratheon"],0),
("Jon Snowning haqiqiy otasi kim?",["Rhaegar Targaryen","Ned Stark","Robert Baratheon"],0),
("Jon Snowning haqiqiy onasi kim?",["Lyanna Stark","Catelyn Stark","Elia Martell"],0),

("Tyrion Lannisterning akasi kim?",["Jaime Lannister","Kevan Lannister","Lancel Lannister"],0),
("Tyrion Lannisterning opasi kim?",["Cersei Lannister","Myrcella Baratheon","Joanna Lannister"],0),
("Tyrionning otasi kim?",["Tywin Lannister","Jaime Lannister","Kevan Lannister"],0),
("Tywin Lannister qaysi qal'aning lordidir?",["Casterly Rock","Winterfell","Highgarden"],0),
("Casterly Rock qaysi xonadonga tegishli?",["Lannister","Stark","Baratheon"],0),
("Lannisterlar boyligi bilan nima bilan mashhur?",["Oltin konlari","Ajdarlar","Kemalar"],0),
("Tywin Lannisterning singlisi kim?",["Genna Lannister","Cersei Lannister","Joanna Lannister"],0),
("Lancel Lannister Cerseiga qanday qarindosh?",["Amakivachcha","Uka","Amaki"],0),
("Tyrion Blackwater jangida nimani boshqargan?",["Mudofaani","Dothraki qo'shinini","Night's Watchni"],0),
("Blackwater jangida ishlatilgan mashhur modda nima?",["Wildfire","Dragonglass","Valyrian steel"],0),

("King's Landing qaysi qirollikning poytaxti?",["Seven Kingdoms","Dorne","Iron Islands"],0),
("King's Landingda qirol qarorgohi nima deb ataladi?",["Red Keep","Winterfell","Dragonstone"],0),
("Red Keep ichidagi taxt xonasi qanday ataladi?",["Throne Room","Great Sept","Dragonpit"],0),
("Iron Throne kimning ramzi?",["Qirol hokimiyati","Night's Watch","Faith"],0),
("King's Landingdagi katta ibodatxona nima?",["Great Sept of Baelor","House of Black and White","Citadel"],0),
("Dragonpit qayerda joylashgan?",["King's Landing","Winterfell","Oldtown"],0),
("Dragonpit nima uchun ishlatilgan?",["Ajdarlarni saqlash","Qamoqxona","Bozor"],0),
("King's Landingning mashhur bozori qaysi?",["Street of Steel","Flea Bottom","The Twins"],0),
("Flea Bottom qayerda?",["King's Landing","Braavos","Oldtown"],0),
("King's Landing qaysi ko'rfaz bo'yida joylashgan?",["Blackwater Bay","Ironman's Bay","Shipbreaker Bay"],0),

("Braavos qaysi dengiz bo'yida joylashgan?",["Narrow Sea","Sunset Sea","Summer Sea"],0),
("Braavosdagi ulkan haykal nima?",["Titan of Braavos","Dragon of Braavos","Giant of Braavos"],0),
("Braavosning mashhur banki nima?",["Iron Bank","Golden Bank","Royal Bank"],0),
("Iron Bank qaysi shaharda?",["Braavos","Meereen","Oldtown"],0),
("Arya Braavosda kimdan ta'lim olgan?",["Faceless Men","Night's Watch","Maesters"],0),
("Jaqen H'ghar qaysi guruhga mansub?",["Faceless Men","Golden Company","Second Sons"],0),
("Faceless Men qaysi shaharda?",["Braavos","King's Landing","Winterfell"],0),
("The Hound Aryani qaysi hududlarda olib yurgan?",["Riverlands","Dorne","Iron Islands"],0),
("Arya Stark Walder Freyga qarshi nimadan foydalangan?",["Yashirin reja va Faceless Men mahorati","Ajdar","Dothraki"],0),
("Arya Stark qaysi xonadon vakili?",["Stark","Tully","Arryn"],0),
]

file = Path("quiz_questions.py")
text = file.read_text(encoding="utf-8")
tree = ast.parse(text)

questions = None

for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "QUIZ_QUESTIONS":
                questions = ast.literal_eval(node.value)

if questions is None:
    raise RuntimeError("QUIZ_QUESTIONS topilmadi")

old_count = len(questions)
seen = {q.strip().lower() for q, _, _ in questions}
added = 0

for item in NEW_QUESTIONS:
    if item[0].strip().lower() not in seen:
        questions.append(item)
        seen.add(item[0].strip().lower())
        added += 1

output = "# GAME OF THRONES — VIKTORINA\n\nQUIZ_QUESTIONS = [\n"

for q, options, correct in questions:
    output += f"    ({q!r}, {options!r}, {correct}),\n"

output += "]\n"
file.write_text(output, encoding="utf-8")

print("Eski savollar:", old_count)
print("Yangi qo'shilgan:", added)
print("Jami savollar:", len(questions))