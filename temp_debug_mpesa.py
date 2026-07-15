from payments.models import MpesaWebhookLog, MpesaTransaction
from payments.mpesa import mpesa_client
log = MpesaWebhookLog.objects.filter(body__contains='ws_CO_11072026090031389759040158').first()
print('log found:', bool(log))
if log:
    print('log id:', log.id)
    print('processed:', log.processed)
    print('body keys:', list(log.body.keys()))
    parsed = mpesa_client.process_callback(log.body)
    print('parsed:', parsed)
    try:
        txn = MpesaTransaction.objects.get(checkout_request_id=parsed.get('checkout_request_id'))
        print('txn found:', txn.id)
        print('txn status:', txn.status)
        print('result code:', txn.result_code)
        print('payment status:', txn.payment.status)
        print('order number:', txn.payment.order.order_number)
    except Exception as e:
        print('txn error:', repr(e))
