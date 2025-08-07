import os
from openai import OpenAI
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

# Проверяем, загрузился ли ключ
api_key = os.getenv("OPENAI_API_KEY")
print(f"Loaded API Key: {api_key[:5]}..." if api_key else "API Key not found!")

# Создание клиента OpenAI с использованием API-ключа
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Пример запроса к GPT
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "Ты — AI-помощник."},
        {"role": "user", "content": "Привет, кто ты?"},
    ]
)

# Вывод ответа
print(response.choices[0].message.content)
