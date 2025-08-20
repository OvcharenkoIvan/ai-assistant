# bot/gpt/translate_service.py
from openai import OpenAI
from bot.core.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

async def translate_text(text: str, target_language: str = "Russian") -> str:
    """
    Универсальная функция перевода через GPT.
    :param text: текст для перевода
    :param target_language: язык перевода (по умолчанию Russian)
    :return: переведённый текст
    """
    if not text.strip():
        return ""
    
    prompt = f"Переведи следующий текст на {target_language}, сохрани факты:\n{text}"
    
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты профессиональный переводчик."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content
