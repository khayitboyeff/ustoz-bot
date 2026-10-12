from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedQuestionTemplate:
    semantic_key: str
    topic: str
    difficulty: str
    question_type: str
    prompt: str
    correct_answer: str
    distractors: tuple[str, str, str]


@dataclass(frozen=True)
class ParameterizedQuestionTemplate:
    semantic_key: str
    topic: str
    difficulty: str
    prompt_template: str
    parameter: str
    correct_answer: str
    distractors: tuple[str, str, str]


VERIFIED_TEMPLATES = (
    VerifiedQuestionTemplate("basics.cia", "cybersecurity_basics", "easy", "single_choice", "Axborot xavfsizligining CIA uchligi nimalardan iborat?", "Maxfiylik, yaxlitlik va mavjudlik", ("Tezlik, narx va qulaylik", "Kirish, chiqish va zaxira", "Parol, login va pochta")),
    VerifiedQuestionTemplate("basics.least_privilege", "cybersecurity_basics", "easy", "single_choice", "Eng kam vakolat tamoyili nimani anglatadi?", "Foydalanuvchiga vazifasi uchun zarur minimal huquqlarni berish", ("Barcha foydalanuvchiga administrator huquqini berish", "Hisoblarni muddatsiz ochiq qoldirish", "Har bir xizmatga bir xil parol qo‘yish")),
    VerifiedQuestionTemplate("basics.mfa", "cybersecurity_basics", "easy", "single_choice", "Ko‘p omilli autentifikatsiya nimani talab qiladi?", "Turli turdagi kamida ikki tasdiqlash omilini", ("Bir parolni ikki marta yozishni", "Faqat ikkita username ishlatishni", "Faqat bitta uzun parolni")),
    VerifiedQuestionTemplate("passwords.unique", "passwords", "easy", "single_choice", "Hisoblar uchun parol tanlashda qaysi usul xavfsizroq?", "Har bir hisob uchun alohida, uzun va taxmin qilish qiyin parol ishlatish", ("Barcha hisoblarda bitta parol ishlatish", "Ism va tug‘ilgan sanani birlashtirish", "Parolni jamoat profilida saqlash")),
    VerifiedQuestionTemplate("passwords.manager", "passwords", "easy", "single_choice", "Parol menejerining asosiy foydasi nima?", "Har bir xizmat uchun noyob parollarni xavfsiz boshqarishga yordam berishi", ("Barcha saytlarda bitta parolni avtomatik qo‘yishi", "Ikki bosqichli himoyani o‘chirishi", "Parollarni ochiq matnda e’lon qilishi")),
    VerifiedQuestionTemplate("passwords.mfa_backup", "passwords", "medium", "single_choice", "Ikki bosqichli himoya uchun zaxira kodlarini qanday saqlash kerak?", "Ularni hisobdan alohida, xavfsiz joyda saqlash", ("Ularni ochiq chatga yuborish", "Ularni parol bilan bir joyda ochiq yozib qo‘yish", "Ularni ijtimoiy tarmoqqa joylash")),
    VerifiedQuestionTemplate("phishing.sender", "phishing", "easy", "single_choice", "Shubhali xatdagi havolani ochishdan oldin nimani tekshirish foydali?", "Yuboruvchi manzili va havolaning haqiqiy domenini", ("Xatdagi logotip rangini", "Xat qaysi shrift bilan yozilganini", "Xatning uzunligini")),
    VerifiedQuestionTemplate("phishing.urgency", "phishing", "easy", "single_choice", "Shoshiltiruvchi xabar va maxfiy ma’lumot so‘rashi nimaning belgisi bo‘lishi mumkin?", "Fishing urinishining", ("Har doim rasmiy xabarning", "DNS yozuvining", "Operatsion tizim yangilanishining")),
    VerifiedQuestionTemplate("phishing.report", "phishing", "medium", "single_choice", "Tashkilot hisobiga kelgan shubhali fishing xati bilan nima qilish kerak?", "Havolalarni ochmasdan, belgilangan xavfsizlik kanaliga xabar berish", ("Xatni barcha kontaktlarga yuborish", "Undagi faylni darhol ishga tushirish", "Javobda parolni yuborish")),
    VerifiedQuestionTemplate("network.tcp", "networks", "easy", "single_choice", "TCP protokoli odatda qanday aloqa xususiyatini ta’minlaydi?", "Ulanishga yo‘naltirilgan, tartibli va yetkazilishni nazorat qiluvchi oqimni", ("Faqat DNS nomlarini ro‘yxatlashni", "Har doim shifrlangan radio aloqani", "Fayllarni avtomatik zaxiralashni")),
    VerifiedQuestionTemplate("network.udp", "networks", "medium", "single_choice", "UDP haqida qaysi fikr to‘g‘ri?", "Ulanish o‘rnatmaydi va yetkazilish kafolatini o‘zi bermaydi", ("Har bir paketni majburiy qayta yuboradi", "Faqat veb sahifalarda ishlaydi", "Har doim TLS bilan shifrlangan bo‘ladi")),
    VerifiedQuestionTemplate("network.port443", "networks", "easy", "single_choice", "HTTPS trafik uchun odatiy TCP port qaysi?", "443", ("21", "25", "110")),
    VerifiedQuestionTemplate("ip.private_ranges", "ip", "medium", "single_choice", "Quyidagilardan qaysi biri RFC 1918 private IPv4 diapazoniga kiradi?", "10.0.0.0/8", ("8.0.0.0/8", "100.0.0.0/8", "224.0.0.0/4")),
    VerifiedQuestionTemplate("ip.loopback6", "ip", "easy", "single_choice", "IPv6 loopback manzili qaysi?", "::1", ("::", "2001:db8::1", "ff02::1")),
    VerifiedQuestionTemplate("ip.private_public", "ip", "easy", "single_choice", "Private IP manzili odatda qayerda yo‘naltiriladi?", "Mahalliy yoki tashkilot ichki tarmog‘ida", ("Internetda butun dunyo bo‘ylab bevosita", "Faqat DNS root serverida", "Faqat Bluetooth tarmog‘ida")),
    VerifiedQuestionTemplate("dns.a", "dns", "easy", "single_choice", "DNS dagi A yozuvi nimani ko‘rsatadi?", "Domen uchun IPv4 manzilni", ("Domen uchun IPv6 manzilni", "Pochta serveri ustuvorligini", "Vakolatli name server nomini")),
    VerifiedQuestionTemplate("dns.aaaa", "dns", "easy", "single_choice", "DNS dagi AAAA yozuvi nimani ko‘rsatadi?", "Domen uchun IPv6 manzilni", ("Domen uchun IPv4 manzilni", "Pochta serveri ustuvorligini", "Sertifikat muddatini")),
    VerifiedQuestionTemplate("dns.mx", "dns", "easy", "single_choice", "DNS dagi MX yozuvi nima uchun ishlatiladi?", "Domen pochtasini qabul qiluvchi serverlarni ko‘rsatish uchun", ("Domenning IPv6 manzilini ko‘rsatish uchun", "Veb-sahifaning HTML kodini saqlash uchun", "TLS shifrini tanlash uchun")),
    VerifiedQuestionTemplate("dns.ns", "dns", "medium", "single_choice", "DNS dagi NS yozuvi nimani ko‘rsatadi?", "Domen zonasi uchun vakolatli name serverlarni", ("Foydalanuvchi parollarini", "Veb-sahifa yo‘naltirish tarixini", "Pochta xabarining matnini")),
    VerifiedQuestionTemplate("dns.ttl", "dns", "medium", "single_choice", "DNS yozuvidagi TTL nimani belgilaydi?", "Javob keshda qancha vaqt saqlanishini", ("Domen nomining maksimal uzunligini", "Serverdagi foydalanuvchilar sonini", "HTTPS sertifikatining algoritmini")),
    VerifiedQuestionTemplate("http.stateless", "http", "medium", "single_choice", "HTTP protokoli odatda qanday protokol sifatida tavsiflanadi?", "Holatsiz protokol", ("Faqat fayl tizimi protokoli", "Doimiy sessiya holatini o‘zi saqlaydigan protokol", "Faqat lokal kompyuterda ishlaydigan protokol")),
    VerifiedQuestionTemplate("http.tls", "http_https", "easy", "single_choice", "HTTPS nimani qo‘shadi?", "HTTP aloqasini TLS orqali himoyalashni", ("DNS so‘rovini bekor qilishni", "Serverni elektr uzilishidan himoyalashni", "Foydalanuvchi parolini avtomatik yangilashni")),
    VerifiedQuestionTemplate("http.status404", "http_https", "easy", "single_choice", "HTTP 404 javobi odatda nimani bildiradi?", "So‘ralgan resurs topilmadi", ("So‘rov muvaffaqiyatli bajarildi", "Server vaqtincha xizmatda emas", "Mijoz autentifikatsiyadan o‘tdi")),
    VerifiedQuestionTemplate("http.status301", "http_https", "medium", "single_choice", "HTTP 301 holat kodi nimani bildiradi?", "Resurs doimiy ravishda boshqa manzilga ko‘chirilganini", ("So‘rov tanasi noto‘g‘ri ekanini", "Resurs taqiqlanganini", "So‘rov muvaffaqiyatli bajarilganini")),
    VerifiedQuestionTemplate("linux.pwd", "linux", "easy", "single_choice", "Linux terminalidagi pwd buyrug‘i nima qiladi?", "Joriy ishchi katalog yo‘lini ko‘rsatadi", ("Jarayonlarni o‘chiradi", "Tarmoq interfeysini uzadi", "Faylni siqadi")),
    VerifiedQuestionTemplate("linux.ls", "linux", "easy", "single_choice", "Linux terminalidagi ls buyrug‘i odatda nima qiladi?", "Katalog tarkibini ko‘rsatadi", ("Foydalanuvchi parolini tiklaydi", "DNS serverni sozlaydi", "Diskni formatlaydi")),
    VerifiedQuestionTemplate("linux.chmod", "linux", "medium", "single_choice", "Linux’da chmod buyrug‘i nima uchun ishlatiladi?", "Fayl yoki katalog ruxsatlarini o‘zgartirish uchun", ("DNS yozuvlarini qidirish uchun", "Paketlarni avtomatik imzolash uchun", "Fayl mazmunini tarjima qilish uchun")),
    VerifiedQuestionTemplate("linux.sudo", "linux", "medium", "single_choice", "Linux’da sudo odatda nima beradi?", "Ruxsat berilgan buyruqni boshqa, ko‘pincha yuqori vakolat bilan bajarish imkonini", ("Har qanday foydalanuvchiga root parolini oshkor qilishni", "Barcha fayllarni ommaga ochishni", "Tarmoq trafikini shifrlashni")),
    VerifiedQuestionTemplate("python.input", "python", "easy", "single_choice", "Python 3’da input() odatda qanday turdagi qiymat qaytaradi?", "str", ("int", "bool", "list")),
    VerifiedQuestionTemplate("python.list", "python", "easy", "single_choice", "Python list tuzilmasining xususiyati qaysi?", "Tartibli va o‘zgartiriladigan elementlar ketma-ketligi", ("Faqat unikal kalitlardan iborat o‘zgarmas xarita", "Faqat son saqlaydigan o‘zgarmas tur", "Tarmoq soketi")),
    VerifiedQuestionTemplate("python.dict", "python", "easy", "single_choice", "Python dict ma’lumotni qanday saqlaydi?", "Kalit-qiymat juftliklari ko‘rinishida", ("Faqat tartib raqami bo‘yicha", "Faqat bayt oqimi ko‘rinishida", "DNS paketlari ko‘rinishida")),
    VerifiedQuestionTemplate("python.eq_is", "python", "medium", "single_choice", "Python’da `==` va `is` orasidagi asosiy farq nima?", "`==` qiymat tengligini, `is` esa obyekt aynanligini tekshiradi", ("Ikkalasi ham faqat sonlarni solishtiradi", "`is` qiymat tengligini, `==` obyekt aynanligini tekshiradi", "Ikkalasi ham o‘zgaruvchini o‘chiradi")),
    VerifiedQuestionTemplate("web.sql_params", "web_security", "medium", "single_choice", "SQL injection xavfini kamaytirish uchun qaysi usul ma’qul?", "Qiymatlarni parametrli SQL so‘roviga uzatish", ("Foydalanuvchi matnini SQL satriga qo‘shib yuborish", "Barcha tekshiruvlarni brauzerda bajarish", "Ma’lumotlar bazasini autentifikatsiyasiz ochish")),
    VerifiedQuestionTemplate("web.xss_output", "web_security", "medium", "single_choice", "XSS xavfini kamaytirishda foydalanuvchi matnini HTML’da chiqarishdan oldin nima qilish kerak?", "Kontekstga mos escaping yoki xavfsiz sanitizatsiya qo‘llash", ("Matnni SQL query sifatida bajarish", "Barcha belgilarni olib tashlamasdan script sifatida talqin qilish", "Foydalanuvchiga admin huquqi berish")),
    VerifiedQuestionTemplate("web.csrf", "web_security", "hard", "single_choice", "CSRF hujumidan himoyada qaysi nazorat yordam beradi?", "Har bir holat o‘zgartiruvchi so‘rovni server tekshiradigan CSRF token bilan bog‘lash", ("GET so‘roviga parol qo‘shish", "Cookie’larni barcha domenlarga ochish", "HTML sarlavhasini yashirish")),
    VerifiedQuestionTemplate("osint.ethics", "osint_ethics", "easy", "single_choice", "Mas’uliyatli OSINT tekshiruvining muhim talabi qaysi?", "Faqat qonuniy va ochiq ma’lumotdan, maqsadga mutanosib foydalanish", ("Login ma’lumotlarini aylanib o‘tish", "Shaxsiy hisobga ruxsatsiz kirish", "Topilgan ma’lumotni roziliksiz tarqatish")),
    VerifiedQuestionTemplate("osint.minimize", "osint_ethics", "medium", "single_choice", "OSINT natijasini qayd etishda maxfiylikni qanday saqlash mumkin?", "Keraksiz shaxsiy ma’lumotni yig‘maslik va ulashmaslik", ("Barcha topilgan ma’lumotni doimiy ommaga chiqarish", "Parol va tasdiqlash kodlarini saqlash", "Ma’lumotni tekshirmasdan fakt deb e’lon qilish")),
    VerifiedQuestionTemplate("defense.backup", "defensive_security", "easy", "single_choice", "Zaxira nusxaning foydaliligini qanday tekshirish kerak?", "Qayta tiklash jarayonini muntazam sinab ko‘rish", ("Faqat fayl nomiga qarash", "Zaxirani yaratib, hech qachon tekshirmaslik", "Yagona nusxani shu qurilmada qoldirish")),
    VerifiedQuestionTemplate("defense.patch", "defensive_security", "easy", "single_choice", "Xavfsizlik yangilanishlarini o‘z vaqtida o‘rnatish nimaga yordam beradi?", "Ma’lum zaifliklardan foydalanish xavfini kamaytirishga", ("Barcha fishing xatlarini yo‘qotishga", "Parollarni avtomatik noyob qilishga", "Tarmoqni doimiy uzishga")),
    VerifiedQuestionTemplate("defense.incident", "defensive_security", "medium", "single_choice", "Zararli dastur yuqqan bo‘lishi mumkin bo‘lgan qurilmada dastlabki ehtiyot chorasi nima?", "Qurilmani tarmoqdan ajratib, tashkilotning javob berish tartibiga xabar qilish", ("Dalillarni saqlamasdan barcha loglarni o‘chirish", "Qurilmani boshqa tarmoqlarga ulash", "Shubhali faylni kontaktlarga yuborish")),
)

PARAMETERIZED_TEMPLATES = (
    ParameterizedQuestionTemplate("network.port.22", "networks", "easy", "TCP {value}-porti odatda qaysi xizmat uchun ishlatiladi?", "22", "SSH", ("DNS", "HTTP", "SMTP")),
    ParameterizedQuestionTemplate("network.port.25", "networks", "medium", "TCP {value}-porti odatda qaysi xizmat bilan bog‘liq?", "25", "SMTP", ("SSH", "HTTPS", "POP3")),
    ParameterizedQuestionTemplate("network.port.53", "networks", "medium", "TCP yoki UDP {value}-porti odatda qaysi xizmat bilan bog‘liq?", "53", "DNS", ("SSH", "HTTPS", "SMTP")),
    ParameterizedQuestionTemplate("network.port.80", "networks", "easy", "TCP {value}-porti odatda qaysi protokol xizmatiga tegishli?", "80", "HTTP", ("DNS", "SSH", "SMTP")),
    ParameterizedQuestionTemplate("network.port.110", "networks", "hard", "TCP {value}-porti odatda qaysi pochta protokoli bilan bog‘liq?", "110", "POP3", ("SMTP", "HTTPS", "SSH")),
    ParameterizedQuestionTemplate("network.port.443", "networks", "easy", "TCP {value}-porti odatda qaysi protokol uchun ishlatiladi?", "443", "HTTPS", ("HTTP", "DNS", "POP3")),
    ParameterizedQuestionTemplate("dns.record.ipv4", "dns", "easy", "Domenni IPv4 manzilga bog‘laydigan DNS yozuvi qaysi?", "A", "A", ("AAAA", "MX", "NS")),
    ParameterizedQuestionTemplate("dns.record.ipv6", "dns", "easy", "IPv6 manzillar uchun belgilangan DNS yozuvi qaysi?", "AAAA", "AAAA", ("A", "MX", "NS")),
    ParameterizedQuestionTemplate("dns.record.mail", "dns", "medium", "Domenning pochta serverlarini ko‘rsatadigan DNS yozuvi qaysi?", "MX", "MX", ("A", "AAAA", "NS")),
    ParameterizedQuestionTemplate("dns.record.nameserver", "dns", "medium", "Domen zonasi uchun vakolatli serverlarni ko‘rsatadigan DNS yozuvi qaysi?", "NS", "NS", ("A", "AAAA", "MX")),
)


def normalize_question_text(question: str) -> str:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    normalized = re.sub(r"\d+", " <number> ", normalized)
    normalized = re.sub(r"[^\w<>]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def generate_verified_questions() -> list[dict[str, object]]:
    generated: list[dict[str, object]] = []
    seen_semantics: set[str] = set()
    seen_prompts: set[str] = set()
    templates = [
        *VERIFIED_TEMPLATES,
        *(
            VerifiedQuestionTemplate(
                semantic_key=template.semantic_key,
                topic=template.topic,
                difficulty=template.difficulty,
                question_type="single_choice",
                prompt=template.prompt_template.format(value=template.parameter),
                correct_answer=template.correct_answer,
                distractors=template.distractors,
            )
            for template in PARAMETERIZED_TEMPLATES
        ),
    ]
    for template in templates:
        normalized = normalize_question_text(template.prompt)
        if template.semantic_key in seen_semantics or normalized in seen_prompts:
            continue
        seen_semantics.add(template.semantic_key)
        seen_prompts.add(normalized)
        options = [template.correct_answer, *template.distractors]
        random.Random(template.semantic_key).shuffle(options)
        generated.append({
            "public_id": hashlib.sha256(template.semantic_key.encode("utf-8")).hexdigest(),
            "semantic_key": template.semantic_key,
            "normalized_question": normalized,
            "topic": template.topic,
            "difficulty": template.difficulty,
            "question_type": template.question_type,
            "question": template.prompt,
            "options": options,
            "answer": options.index(template.correct_answer),
        })
    return generated
