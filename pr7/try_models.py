import base64
import io
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=os.getenv("LLM_API_KEY"),
    timeout=40,
    max_retries=0,
)

try:
    names = sorted(m.id for m in client.models.list())
    print("Доступні моделі:")
    for name in names:
        print("  ", name)
except Exception as exc:
    print("Не вдалося отримати список моделей:", type(exc).__name__, exc)
    names = []

img = Image.new("RGB", (360, 120), "white")
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.load_default(size=64)
except TypeError:
    font = ImageFont.load_default()
draw.text((30, 25), "No 4719", font=font, fill="black")
buf = io.BytesIO()
img.save(buf, format="PNG")
encoded = base64.b64encode(buf.getvalue()).decode("ascii")

candidates = sys.argv[1:] or [os.getenv("LLM_MODEL"), "gemini-3.5-flash-lite", "gemini-3.5-flash"]
print()
for model in dict.fromkeys(c for c in candidates if c):
    short = model.split("/")[-1]
    started = time.perf_counter()
    try:
        answer = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Яке число на зображенні? Лише цифри."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ]}],
            max_tokens=200,
            temperature=0,
        )
        text = (answer.choices[0].message.content or "").strip()
        print(f"[ OK ] {short}: {time.perf_counter() - started:.1f} с, відповідь {text!r}")
    except Exception as exc:
        print(f"[ !! ] {short}: {time.perf_counter() - started:.1f} с, {type(exc).__name__}: {str(exc)[:150]}")