import os
import time
from dotenv import load_dotenv
from openai import OpenAI, APIError, APITimeoutError, RateLimitError, AuthenticationError
from . import schema

load_dotenv()

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL")

TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "600"))
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
TOKEN_BUDGET = int(os.getenv("LLM_TOKEN_BUDGET", "3000"))

_client = None

class LLMError(Exception):
    """Помилка роботи з моделлю, зрозуміла веб-рівню."""
    pass

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=TIMEOUT)
    return _client

def estimate_tokens(text: str) -> int:
    """Орієнтовна оцінка: 1 токен ≈ 3-4 символи для кирилиці/латиниці."""
    return len(text) // 3

def fit_budget(history: list[dict], budget: int) -> list[dict]:
    """Залишає лише ті повідомлення з кінця історії, які вміщуються в бюджет."""
    fitted_history = []
    current_tokens = 0
    
    # Йдемо з кінця (найновіші повідомлення важливіші)
    for turn in reversed(history):
        # Якщо це словник (JSON), беремо лише текст, щоб зекономити токени
        content = turn["content"]
        if turn["role"] == "assistant" and isinstance(content, str) and "{" in content:
            try:
                parsed = json.loads(content)
                content = parsed.get("reply", content)
            except:
                pass
                
        turn_text = f"{turn['role']}: {content}"
        tokens = estimate_tokens(turn_text)
        
        if current_tokens + tokens > budget:
            break
            
        fitted_history.insert(0, turn)
        current_tokens += tokens
        
    return fitted_history

def build_messages(message: str, history: list[dict], context: str) -> list[dict]:
    sys_instruction = f"""Ти — помічник служби підтримки інтернет-магазину.
Твоя мета — допомагати клієнтам, спираючись ТІЛЬКИ на правила магазину нижче.

ПРАВИЛА МАГАЗИНУ:
{context}

ОБМЕЖЕННЯ:
1. Якщо відповіді немає в правилах, скажи про це і запропонуй перевести на оператора.
2. Не вигадуй факти, ціни чи умови.
3. Якщо клієнт не назвав номер замовлення (6 цифр), але він потрібен — запитай.
4. Якщо клієнт назвав номер замовлення раніше в розмові — запам'ятай його.

ПРИКЛАДИ РОБОТИ:
- Клієнт: "Як скасувати замовлення?"
  Відповідь: (ґрунтується на правилах, тема: Замовлення)
- Клієнт: "Доставляєте в Польщу?"
  Відповідь: (правил немає, тема: Доставка, перевести на оператора: так)
"""
    msgs = [{"role": "system", "content": sys_instruction}]
    
    # Додаємо обрізану історію
    for turn in history:
        # Для контексту асистента передаємо лише текстову відповідь, а не весь JSON
        content = turn["content"]
        if turn["role"] == "assistant" and "{" in content:
            try:
                content = json.loads(content).get("reply", content)
            except:
                pass
        msgs.append({"role": turn["role"], "content": content})
        
    msgs.append({"role": "user", "content": message})
    return msgs

def ask(message: str, history: list[dict], context: str) -> dict:
    client = get_client()
    
    # Рахуємо резерв для запиту (системний промпт + нове повідомлення + запас на відповідь)
    reserved_tokens = estimate_tokens(context) + estimate_tokens(message) + MAX_TOKENS + 500
    history_budget = max(0, TOKEN_BUDGET - reserved_tokens)
    
    fitted_history = fit_budget(history, history_budget)
    messages = build_messages(message, fitted_history, context)
    
    start_time = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "AssistantResponse",
                    "schema": schema.output_schema(),
                    "strict": False
                }
            }
        )
    except AuthenticationError:
        raise LLMError("Помилка авторизації: перевірте API ключ.")
    except APITimeoutError:
        raise LLMError("Таймаут: сервіс задовго не відповідає.")
    except RateLimitError:
        raise LLMError("Перевищено ліміт запитів до API.")
    except APIError as e:
        raise LLMError(f"Помилка провайдера: {e}")
        
    elapsed = time.perf_counter() - start_time
    raw_content = response.choices[0].message.content or ""
    
    # Валідація схеми
    try:
        validated_data = schema.validate(raw_content)
    except ValueError as e:
        raise LLMError(f"Збій валідації відповіді: {e}")
        
    usage = response.usage
    return {
        "result": validated_data,
        "model": MODEL,
        "elapsed": elapsed,
        "usage": {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens
        } if usage else {}
    }