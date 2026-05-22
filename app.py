import os
import re
import html
import sqlite3
import difflib
from typing import Dict, Tuple, Optional

import pymorphy3
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session
)
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

DB_PATH = "anglicisms.db"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ADMIN_TOKEN = "pytomo-admin"

ADMINS = [

    {
        "email": "vika21061929@gmail.com",
        "password": "Nianglismam2026"
    },

    {
        "email": "fechak.anastasia@gmail.com",
        "password": "Nianglismam2026"
    }

]

USER_LIMIT_COUNT = 10
USER_LIMIT_CHARS = 3000

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)


app.secret_key = "pytomo-secret-key"

client = OpenAI(api_key=OPENAI_API_KEY)

morph = pymorphy3.MorphAnalyzer(lang="uk")

user_usage = {}


word_of_the_day_cache = None


# =========================
# HOME PAGE STATISTICS
# =========================


def get_anglicisms_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Англізм")

    count = cursor.fetchone()[0]

    conn.close()

    return count


# =========================
# DICTIONARY
# =========================


def get_all_anglicisms():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT
        a.ID,
        a.Англізм,
        a."Частина мови",
        v.Відповідник
    FROM Англізм a
    LEFT JOIN Відповідник v
        ON a.ID = v."ID англізма"
    WHERE v.ID = (
        SELECT MIN(v2.ID)
        FROM Відповідник v2
        WHERE v2."ID англізма" = a.ID
    )
    ORDER BY a.Англізм COLLATE NOCASE
    """

    cursor.execute(query)

    rows = cursor.fetchall()

    conn.close()

    anglicisms = []

    for row in rows:
        anglicisms.append({
            "id": row[0],
            "anglicism": row[1],
            "part_of_speech": row[2],
            "replacement": row[3]
        })

    return anglicisms


# =========================
# ARTICLE PAGE
# =========================


def get_anglicism_by_id(anglicism_id):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    main_query = """
    SELECT
        ID,
        Англізм,
        "Частина мови",
        "Оригінальне написання англізма",
        Тлумачення
    FROM Англізм
    WHERE ID = ?
    """

    cursor.execute(main_query, (anglicism_id,))
    main_row = cursor.fetchone()

    if not main_row:
        conn.close()
        return None

    variants_query = """
    SELECT "Варіянт написання"
    FROM Варіянт_написання_англізма
    WHERE "ID англізма" = ?
    """

    cursor.execute(variants_query, (anglicism_id,))
    variants_rows = cursor.fetchall()

    replacements_query = """
    SELECT
        Відповідник,
        Тлумачення,
        "Приклад вживання англізма",
        "Приклад вживання відповідника"
    FROM Відповідник
    WHERE "ID англізма" = ?
    """

    cursor.execute(replacements_query, (anglicism_id,))
    replacements_rows = cursor.fetchall()

    replacements = []

    for item in replacements_rows:

        replacements.append({
            "word": item[0],
            "definition": item[1],
            "example_anglicism": item[2],
            "example_replacement": item[3]
        })

    conn.close()

    return {
        "id": main_row[0],
        "anglicism": main_row[1],
        "part_of_speech": main_row[2],
        "original_spelling": main_row[3],
        "definition": main_row[4],
        "variants": [row[0] for row in variants_rows],
        "replacements": replacements
    }


def get_recent_anglicisms(limit=12):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT
        ID,
        Англізм
    FROM Англізм
    ORDER BY ID DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))

    rows = cursor.fetchall()

    conn.close()

    return rows


def load_word_of_the_day():

    global word_of_the_day_cache

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT
        a.ID,
        a.Англізм,
        a."Частина мови",
        a."Оригінальне написання англізма",
        a.Тлумачення,
        v.Відповідник
    FROM Англізм a
    LEFT JOIN Відповідник v
        ON a.ID = v."ID англізма"
    WHERE v.ID = (
        SELECT MIN(v2.ID)
        FROM Відповідник v2
        WHERE v2."ID англізма" = a.ID
    )
    ORDER BY RANDOM()
    LIMIT 1
    """

    cursor.execute(query)

    row = cursor.fetchone()

    conn.close()

    if not row:
        word_of_the_day_cache = None
        return

    word_of_the_day_cache = {
        "id": row[0],
        "anglicism": row[1],
        "part_of_speech": row[2],
        "original_spelling": row[3],
        "definition": row[4],
        "replacement": row[5]
    }
  
    
# =========================
# TEXT PROCESSING
# =========================


def normalize_word(word: str) -> str:
    return (
        word.lower()
        .replace("’", "'")
        .replace("ʼ", "'")
        .replace("`", "'")
        .strip()
    )


def normalize_replacement(word: str) -> str:
    return word.strip().lower()


def get_lemma(word: str) -> str:
    parsed = morph.parse(normalize_word(word))

    if parsed:
        return normalize_word(parsed[0].normal_form)

    return normalize_word(word)


def has_grammeme(tag, grammeme: str) -> bool:
    try:
        return grammeme in tag
    except ValueError:
        return False


def load_anglicisms_from_db(db_path: str) -> Dict[str, Dict]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    dictionary = {}

    query = """
    SELECT
        a.ID,
        a.Англізм,
        a."Частина мови",
        v.Відповідник
    FROM Англізм a
    LEFT JOIN Відповідник v
        ON a.ID = v."ID англізма"
    WHERE v.ID = (
        SELECT MIN(v2.ID)
        FROM Відповідник v2
        WHERE v2."ID англізма" = a.ID
    )
    """

    cursor.execute(query)

    for anglism_id, anglism, part_of_speech, replacement in cursor.fetchall():

        if not anglism or not replacement:
            continue

        item = {
            "id": anglism_id,
            "anglicism": anglism,
            "replacement": normalize_replacement(replacement),
            "part_of_speech": part_of_speech
        }

        dictionary[normalize_word(anglism)] = item
        dictionary[get_lemma(anglism)] = item

    variant_query = """
    SELECT
        v."Варіянт написання",
        a.ID,
        a.Англізм,
        a."Частина мови",
        r.Відповідник
    FROM "Варіянт_написання_англізма" v
    JOIN Англізм a
        ON v."ID англізма" = a.ID
    LEFT JOIN Відповідник r
        ON a.ID = r."ID англізма"
    WHERE r.ID = (
        SELECT MIN(r2.ID)
        FROM Відповідник r2
        WHERE r2."ID англізма" = a.ID
    )
    """

    cursor.execute(variant_query)

    for variant, anglism_id, main_anglism, part_of_speech, replacement in cursor.fetchall():

        if not variant or not replacement:
            continue

        item = {
            "id": anglism_id,
            "anglicism": main_anglism,
            "replacement": normalize_replacement(replacement),
            "part_of_speech": part_of_speech
        }

        dictionary[normalize_word(variant)] = item
        dictionary[get_lemma(variant)] = item

    conn.close()

    return dictionary


def get_all_replacements_for_anglicism(db_path: str, anglism_id: int) -> list:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
    SELECT Відповідник
    FROM Відповідник
    WHERE "ID англізма" = ?
    ORDER BY ID
    """

    cursor.execute(query, (anglism_id,))

    rows = cursor.fetchall()

    conn.close()

    return [normalize_replacement(row[0]) for row in rows if row[0]]


def find_similar_word(word: str, dictionary: Dict[str, Dict]) -> Tuple[Optional[Dict], str]:
    normalized = normalize_word(word)

    matches = difflib.get_close_matches(
        normalized,
        list(dictionary.keys()),
        n=1,
        cutoff=0.78
    )

    if matches:
        best_match = matches[0]
        return dictionary[best_match], "fuzzy"

    return None, "not_found"


def find_in_dictionary(word: str, dictionary: Dict[str, Dict]) -> Tuple[Optional[Dict], str]:
    normalized = normalize_word(word)

    if normalized in dictionary:
        return dictionary[normalized], "exact"

    lemma = get_lemma(word)

    if lemma in dictionary:
        return dictionary[lemma], "lemma"

    similar_item, similar_type = find_similar_word(word, dictionary)

    if similar_item:
        return similar_item, similar_type

    return None, "not_found"


def get_original_parse(word: str):
    parsed = morph.parse(normalize_word(word))

    if parsed:
        return parsed[0]

    return None


def collect_needed_grammemes(original_word: str):
    original_parse = get_original_parse(original_word)

    if not original_parse:
        return set()

    tag = original_parse.tag
    grammemes = set()

    if has_grammeme(tag, "NOUN"):

        for gram in [
            "nomn", "gent", "datv", "accs", "ablt", "loct",
            "sing", "plur"
        ]:

            if has_grammeme(tag, gram):
                grammemes.add(gram)

    elif has_grammeme(tag, "ADJF"):

        for gram in [
            "nomn", "gent", "datv", "accs", "ablt", "loct",
            "sing", "plur",
            "masc", "femn", "neut"
        ]:

            if has_grammeme(tag, gram):
                grammemes.add(gram)

    elif has_grammeme(tag, "VERB") or has_grammeme(tag, "INFN"):

        for gram in [
            "past", "pres", "futr",
            "sing", "plur",
            "masc", "femn", "neut",
            "1per", "2per", "3per"
        ]:

            if has_grammeme(tag, gram):
                grammemes.add(gram)

    return grammemes


def inflect_one_word(replacement_word: str, original_word: str):
    replacement_word = normalize_replacement(replacement_word)

    parsed_replacement = morph.parse(replacement_word)

    if not parsed_replacement:
        return replacement_word

    replacement_parse = parsed_replacement[0]

    grammemes = collect_needed_grammemes(original_word)

    if not grammemes:
        return replacement_word

    try:
        inflected = replacement_parse.inflect(grammemes)

        if inflected:
            return inflected.word

    except Exception:
        return replacement_word

    return replacement_word


def inflect_replacement(replacement: str, original_word: str):
    replacement = normalize_replacement(replacement)

    words = replacement.split()

    if not words:
        return replacement

    if len(words) == 1:
        return inflect_one_word(words[0], original_word)

    first_word = inflect_one_word(words[0], original_word)

    return " ".join([first_word] + words[1:])


# =========================
# AI CHOICE
# =========================


def choose_best_replacement_with_ai(sentence: str, anglism: str, replacements: list) -> str:

    if not replacements:
        return ""

    if len(replacements) == 1:
        return replacements[0]

    replacements_text = "\n".join([
        f"- {replacement}" for replacement in replacements
    ])

    prompt = f"""
У реченні є англізм. Обери з поданого списку той український відповідник, який найкраще підходить до контексту.

Не пояснюй нічого.
Поверни тільки один відповідник зі списку.
Не вигадуй нових відповідників.
Не змінюй форму відповідника, поверни його так, як він записаний у списку.

Речення:
{sentence}

Англізм:
{anglism}

Можливі відповідники:
{replacements_text}
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )

        chosen = response.output_text.strip().lower()

        for replacement in replacements:
            if chosen == replacement.lower():
                return replacement

        return replacements[0]

    except Exception:
        return replacements[0]


# =========================
# TEXT IMPROVEMENT
# =========================


def replace_anglicisms_with_markers(text: str, dictionary: Dict[str, Dict]):
    pattern = r"[А-Яа-яІіЇїЄєҐґA-Za-z0-9ʼ’'\-]+"

    input_parts = []
    replaced_parts = []
    changes = []

    last_end = 0
    index = 0

    for match in re.finditer(pattern, text):

        word = match.group(0)

        start, end = match.span()

        before = text[last_end:start]

        input_parts.append(html.escape(before))
        replaced_parts.append(before)

        item, match_type = find_in_dictionary(word, dictionary)

        if item:

            all_replacements = get_all_replacements_for_anglicism(
                DB_PATH,
                item["id"]
            )

            chosen_replacement = choose_best_replacement_with_ai(
                sentence=text,
                anglism=word,
                replacements=all_replacements
            )

            if not chosen_replacement:
                chosen_replacement = item["replacement"]

            replacement = inflect_replacement(chosen_replacement, word)

            alternatives = []

            for repl in all_replacements:

                inflected = inflect_replacement(repl, word)

                if inflected not in alternatives:
                    alternatives.append(inflected)

            input_parts.append(
                f'<span class="input-anglicism">{html.escape(word)}</span>'
            )

            marker_start = f"[[PYTOMO_{index}]]"
            marker_end = f"[[/PYTOMO_{index}]]"

            replaced_parts.append(
                f"{marker_start}{replacement}{marker_end}"
            )

            changes.append({
                "index": index,
                "original": word,
                "replacement": replacement,
                "alternatives": alternatives
            })

            index += 1

        else:
            input_parts.append(html.escape(word))
            replaced_parts.append(word)

        last_end = end

    input_parts.append(html.escape(text[last_end:]))
    replaced_parts.append(text[last_end:])

    return "".join(input_parts), "".join(replaced_parts), changes


def polish_with_ai(text_with_markers: str):

    prompt = f"""
Виправ граматику в українському реченні.
Не пояснюй нічого.
Поверни тільки виправлене речення, яке звучить природно українською. Наприклад замість "Ні вікового утиску" треба написати "Ні віковому утиску"
Виправ усі помилки, перепиши речення без помилок.

Додатково:
Перевір граматику і природність усього тексту, а не тільки окремі замінені слова.
Узгоджуй слова навколо замінених англізмів за відмінком, числом, родом і контекстом.
Наприклад, якщо після заміни виходить "робив знятку помилку", виправ на природне "робив знятку помилки".

У тексті є службові мітки виду [[PYTOMO_0]]слово або словосполучення[[/PYTOMO_0]].
Ці мітки потрібні для підсвічування замінених англізмів.
Не видаляй самі мітки і не змінюй їхні номери.
Але текст усередині міток можна граматично змінювати, якщо цього потребує речення.

Також якщо виходять тавтології, наприклад "робити знімок екрана помилки на екрані" - цього також уникай і прибирай тавтологію

Речення:
{text_with_markers}
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )

        return response.output_text.strip()

    except Exception as e:
        print("Помилка ШІ:")
        print(e)

        return text_with_markers


def build_output_html_from_markers(polished_text: str, changes: list):
    escaped_text = html.escape(polished_text)

    for change in changes:

        index = change["index"]

        pattern = re.compile(
            re.escape(f"[[PYTOMO_{index}]]") +
            r"(.*?)" +
            re.escape(f"[[/PYTOMO_{index}]]"),
            re.DOTALL
        )

        def replace_marker(match):
            inner_text = match.group(1)

            change["replacement"] = html.unescape(inner_text)

            return (
                f'<span class="replaced-word" data-index="{index}">'
                f'{inner_text}'
                f'</span>'
            )

        escaped_text = pattern.sub(replace_marker, escaped_text)

    escaped_text = re.sub(r"\[\[/?PYTOMO_\d+\]\]", "", escaped_text)

    return escaped_text


def improve_full_text(text: str):
    dictionary = load_anglicisms_from_db(DB_PATH)

    input_html, replaced_text_with_markers, changes = replace_anglicisms_with_markers(
        text,
        dictionary
    )

    polished_text = polish_with_ai(replaced_text_with_markers)

    output_html = build_output_html_from_markers(polished_text, changes)

    return input_html, output_html, changes


def improve_selected_replacement(
    original_text: str,
    original_word: str,
    new_replacement: str
):

    dictionary = load_anglicisms_from_db(DB_PATH)

    input_html, replaced_text_with_markers, changes = (
        replace_anglicisms_with_markers(
            original_text,
            dictionary
        )
    )

    for change in changes:

        if change["original"].lower() == original_word.lower():

            inflected = inflect_replacement(
                new_replacement,
                original_word
            )

            marker_start = f"[[PYTOMO_{change['index']}]]"
            marker_end = f"[[/PYTOMO_{change['index']}]]"

            pattern = re.escape(marker_start) + r".*?" + re.escape(marker_end)

            replaced_text_with_markers = re.sub(
                pattern,
                f"{marker_start}{inflected}{marker_end}",
                replaced_text_with_markers,
                count=1
            )

            change["replacement"] = inflected

            break

    polished_text = polish_with_ai(
        replaced_text_with_markers
    )

    output_html = build_output_html_from_markers(
        polished_text,
        changes
    )

    return output_html
    
    
# =========================
# DATABASE FORMATTING
# =========================

def capitalize_first(text):

    text = text.strip()

    if not text:
        return ""

    return text[0].upper() + text[1:]


def format_original_spelling(text):

    return text.strip().lower()


def format_definition(text):

    text = text.strip()

    if not text:
        return ""

    source = ""

    if "(" in text and text.endswith(")"):

        split_index = text.rfind("(")

        source = text[split_index:].strip()

        text = text[:split_index].strip()

    text = text.rstrip(".")

    text = f"‘{text}’"

    if source:
        text += f" {source}"

    return text


def format_note(text):

    text = capitalize_first(text)

    if not text:
        return ""

    if not text.endswith("."):
        text += "."

    return text


def format_example(text):

    text = text.strip()

    if not text:
        return ""

    if not text.endswith("."):
        text += "."

    return text


# =========================
# ROUTES
# =========================

@app.route("/")
def home():

    anglicisms_count = get_anglicisms_count()

    word_of_the_day = word_of_the_day_cache

    recent_anglicisms = get_recent_anglicisms()

    return render_template(
        "home.html",
        anglicisms_count=anglicisms_count,
        word_of_the_day=word_of_the_day,
        recent_anglicisms=recent_anglicisms
    )
    

@app.route("/home.html")
def home_page():

    anglicisms_count = get_anglicisms_count()

    word_of_the_day = word_of_the_day_cache

    recent_anglicisms = get_recent_anglicisms()

    return render_template(
        "home.html",
        anglicisms_count=anglicisms_count,
        word_of_the_day=word_of_the_day,
        recent_anglicisms=recent_anglicisms
    )


@app.route("/dictionary.html")
def dictionary():
    anglicisms = get_all_anglicisms()

    return render_template(
        "dictionary.html",
        anglicisms=anglicisms
    )


@app.route("/improve.html")
def improve():
    return render_template("improve.html")


@app.route("/about.html")
def about():
    return render_template("about.html")


@app.route("/contacts.html")
def contacts():
    return render_template("contacts.html")


@app.route("/suggest.html")
def suggest():
    return render_template("suggest.html")


@app.route("/admin_login.html", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()

        password = request.form.get("password", "").strip()

        for admin in ADMINS:

            if (
                email == admin["email"]
                and password == admin["password"]
            ):

                session["admin_logged_in"] = True

                return redirect(url_for("admin_database"))

        return render_template(
            "admin_login.html",
            login_error=True
        )

    return render_template("admin_login.html")


@app.route("/admin_database.html")
def admin_database():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    anglicisms = get_all_anglicisms()

    return render_template(
        "admin_database.html",
        anglicisms=anglicisms
    )


@app.route(
    "/admin_add_anglicism.html",
    methods=["GET", "POST"]
)
def admin_add_anglicism():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        conn = sqlite3.connect(DB_PATH)

        cursor = conn.cursor()

        anglicism = capitalize_first(
            request.form.get("anglicism", "")
        )

        part_of_speech = capitalize_first(
            request.form.get("part_of_speech", "")
        )

        original_spelling = format_original_spelling(
            request.form.get("original_spelling", "")
        )

        variants = request.form.get("variants", "")

        definition = format_definition(
            request.form.get("definition", "")
        )

        notes = format_note(
            request.form.get("notes", "")
        )

        cursor.execute("SELECT MAX(ID) FROM Англізм")

        last_id = cursor.fetchone()[0]

        if last_id is None:
            new_id = 1
        else:
            new_id = last_id + 1

        cursor.execute("""
            INSERT INTO Англізм (
                ID,
                Англізм,
                "Частина мови",
                "Оригінальне написання англізма",
                Тлумачення,
                Зауваження
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            new_id,
            anglicism,
            part_of_speech,
            original_spelling,
            definition,
            notes
        ))

        anglicism_id = new_id

        # =========================
        # ВАРІЯНТИ НАПИСАННЯ
        # =========================

        variants_list = [
            v.strip()
            for v in variants.split(",")
            if v.strip()
        ]

        for variant in variants_list:

            variant = capitalize_first(variant)

            if variant.lower() == anglicism.lower():
                continue

            cursor.execute("""
                SELECT MAX(ID)
                FROM Варіянт_написання_англізма
            """)

            last_variant_id = cursor.fetchone()[0]

            if last_variant_id is None:
                new_variant_id = 1
            else:
                new_variant_id = last_variant_id + 1

            cursor.execute("""
                INSERT INTO Варіянт_написання_англізма (
                    ID,
                    "ID англізма",
                    "Варіянт написання"
                )
                VALUES (?, ?, ?)
            """, (
                new_variant_id,
                anglicism_id,
                variant
            ))

        # =========================
        # ВІДПОВІДНИКИ
        # =========================

        index = 1

        while True:

            replacement = request.form.get(
                f"replacement_{index}"
            )

            if replacement is None:
                break

            replacement = capitalize_first(replacement)

            replacement_definition = format_definition(
                request.form.get(
                    f"replacement_definition_{index}",
                    ""
                )
            )

            replacement_example = format_example(
                request.form.get(
                    f"replacement_example_{index}",
                    ""
                )
            )

            anglicism_example = format_example(
                request.form.get(
                    f"anglicism_example_{index}",
                    ""
                )
            )


            cursor.execute("""
                SELECT MAX(ID)
                FROM Відповідник
            """)

            last_replacement_id = cursor.fetchone()[0]

            if last_replacement_id is None:
                new_replacement_id = 1
            else:
                new_replacement_id = last_replacement_id + 1

            cursor.execute("""
                INSERT INTO Відповідник (
                    ID,
                    "ID англізма",
                    Відповідник,
                    Тлумачення,
                    "Приклад вживання відповідника",
                    "Приклад вживання англізма"
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                new_replacement_id,
                anglicism_id,
                replacement,
                replacement_definition,
                replacement_example,
                anglicism_example
            ))

            index += 1

        conn.commit()

        conn.close()

        return redirect(url_for("admin_database"))

    return render_template(
        "admin_add_anglicism.html"
    )


@app.route("/admin_edit_anglicism.html")
def admin_edit_anglicism():
    
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    return render_template("admin_edit_anglicism.html")


@app.route("/admin_suggestions.html")
def admin_suggestions():
    
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    return render_template("admin_suggestions.html")


@app.route("/admin_edit_suggestion.html")
def admin_edit_suggestion():
    
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    return render_template("admin_edit_suggestion.html")


@app.route("/admin_messages.html")
def admin_messages():
    
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    return render_template("admin_messages.html")


@app.route("/api/anglicism/<int:anglicism_id>")
def api_anglicism(anglicism_id):

    anglicism = get_anglicism_by_id(anglicism_id)

    if not anglicism:
        return jsonify({
            "ok": False
        }), 404

    return jsonify(anglicism)
   

@app.route("/api/improve", methods=["POST"])
def api_improve():

    data = request.get_json(force=True)

    text = data.get("text", "").strip()

    if not text:

        return jsonify({
            "ok": False,
            "error": "Введіть текст для покращення."
        }), 400

    input_html, output_html, changes = improve_full_text(text)

    return jsonify({
        "ok": True,
        "input_html": input_html,
        "output_html": output_html,
        "changes": changes,
        "remaining": 10
    })


@app.route("/api/replace-option", methods=["POST"])
def api_replace_option():

    data = request.get_json(force=True)

    original_text = data.get("text", "")
    original_word = data.get("original_word", "")
    new_replacement = data.get("replacement", "")

    if not original_text or not original_word or not new_replacement:

        return jsonify({
            "ok": False
        }), 400

    output_html = improve_selected_replacement(
        original_text,
        original_word,
        new_replacement
    )

    return jsonify({
        "ok": True,
        "output_html": output_html
    })


@app.route(
    "/admin/delete/<int:anglicism_id>",
    methods=["POST"]
)
def delete_anglicism(anglicism_id):

    if not session.get("admin_logged_in"):

        return jsonify({
            "ok": False
        }), 403

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM Відповідник
        WHERE "ID англізма" = ?
    """, (anglicism_id,))

    cursor.execute("""
        DELETE FROM Варіянт_написання_англізма
        WHERE "ID англізма" = ?
    """, (anglicism_id,))

    cursor.execute("""
        DELETE FROM Англізм
        WHERE ID = ?
    """, (anglicism_id,))

    conn.commit()

    conn.close()

    return jsonify({
        "ok": True
    })


load_word_of_the_day()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )