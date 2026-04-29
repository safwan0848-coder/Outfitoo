from user_side.orders.models import Order
from user_side.wallet.refund_utils import calculate_coupon_adjusted_refund

order = Order.objects.last()
print(f"Order: {order.order_number}, Gross: {order.total_amount}, Discount: {order.discount_amount}")
for item in order.items.all():
    print(f"Item: {item.product.name}, Price: {item.price}, Qty: {item.quantity}")
    refund_1 = calculate_coupon_adjusted_refund(order, item.price, 1, order_item=item)
    refund_2 = calculate_coupon_adjusted_refund(order, item.price, 2, order_item=item)
    print(f"Refund for 1 qty: {refund_1}")
    print(f"Refund for 2 qty: {refund_2}")
