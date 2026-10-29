import json
from shop import service
from app import tools
full = json.dumps(service.get_order("10458"), ensure_ascii=False)
cut = json.dumps(tools._public_order(service.get_order("10458")), ensure_ascii=False)
print("повний запис:", len(full), "символів; вибрані поля:", len(cut))