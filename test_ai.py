from openai import OpenAI

# Встав сюди НОВИЙ API-ключ
OPENAI_API_KEY = ""

client = OpenAI(api_key=OPENAI_API_KEY)

sentence = "Я жертвую кожен день. Ні вікового утиск та мови ненависті в цій компанії. Я не потерплю ненависницьких коментарів. Ми передали всі гроші добровільній компанії"

prompt = f"""
Виправ граматику в українському реченні.
Не пояснюй нічого.
Поверни тільки виправлене речення, яке звучить природно українською. Наприклад замість "Ні вікового утиску" треба написати "Ні віковому утиску"
Виправ усі помилки, перепиши речення без помилок

Речення:
{sentence}
"""

try:
    response = client.responses.create(
        model="gpt-4o-mini",
        input=prompt
    )

    print("Було:")
    print(sentence)

    print("\nСтало:")
    print(response.output_text)

except Exception as e:
    print("Помилка:")
    print(e)