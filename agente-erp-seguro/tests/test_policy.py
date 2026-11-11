from app.actions import ConfirmOrder, CreateLead, CreatePurchaseOrder, CreateSaleOrder, OrderLine
from app.config import Settings
from app.policy import Decision, evaluate

S = Settings()


def sale(qty, price):
    return CreateSaleOrder(customer="Acme", lines=[OrderLine(product="x", quantity=qty, unit_price=price)])


def purchase(qty, price):
    return CreatePurchaseOrder(supplier="Levante", lines=[OrderLine(product="x", quantity=qty, unit_price=price)])


def test_lead_is_auto():
    a = CreateLead(name="Lead de prueba")
    assert evaluate(a, a.amount, S).decision is Decision.AUTO


def test_small_sale_is_auto_large_needs_approval():
    assert evaluate(sale(2, 100), 200, S).decision is Decision.AUTO
    assert evaluate(sale(10, 250), 2500, S).decision is Decision.APPROVAL


def test_purchase_limit_is_stricter_than_sale():
    assert evaluate(purchase(1, 600), 600, S).decision is Decision.APPROVAL
    assert evaluate(sale(1, 600), 600, S).decision is Decision.AUTO


def test_hard_limit_denies_everything():
    a = sale(1000, 100)  # 100.000 > 50.000
    assert evaluate(a, a.amount, S).decision is Decision.DENY


def test_confirm_always_needs_approval():
    a = ConfirmOrder(order_model="sale.order", order_id=1)
    assert evaluate(a, 10.0, S).decision is Decision.APPROVAL


def test_zero_price_line_needs_approval():
    a = sale(1, 0)
    assert evaluate(a, a.amount, S).decision is Decision.APPROVAL
