import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
c = OpenAI(base_url=os.getenv("LLM_BASE_URL"), api_key=os.getenv("LLM_API_KEY"), timeout=30, max_retries=0)

tool = [{"type": "function", "function": {"name": "ping", "description": "test",
         "parameters": {"type": "object", "properties": {}}}}]

ids = [m.id.replace("models/", "") for m in c.models.list()]
ids = [i for i in ids if "gemini" in i and "embed" not in i and "image" not in i and "tts" not in i]
print("Кандидатов:", len(ids))

for i in ids:
    try:
        c.chat.completions.create(model=i, messages=[{"role": "user", "content": "Call ping"}],
                                  tools=tool, max_tokens=50)
        print("РАБОТАЕТ:", i)
    except Exception as e:
        print("нет:", i, "-", type(e).__name__)