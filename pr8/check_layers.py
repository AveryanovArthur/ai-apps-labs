from app import tools
ctx = tools.Context("C-1001")
tests = [
    ("назва",   "refund_money", '{"order_id":"10458"}'),
    ("JSON",    "get_order", '{order_id: 10458'),
    ("схема",   "get_order", '{"order_id":"abc"}'),
    ("схема",   "get_order", '{"order_id":"10458","customer_id":"C-1002"}'),
    ("власник", "get_order", '{"order_id":"10466"}'),
    ("нормалізація", "get_order", '{"order_id":"№ 10 458"}'),
]
for layer, name, args in tests:
    r = tools.call(name, args, ctx)
    print(layer, "->", r.status, "|", r.reason)