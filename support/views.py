import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView

from notifications.models import Notification
from orders.models import Order
from .models import CallbackRequest, SupportMessage, SupportTicket

User = get_user_model()


def get_chatbot_reply(message_text, user=None):
    text = (message_text or '').strip().lower()
    if not text:
        return None

    if any(keyword in text for keyword in ['human support', 'live help', 'agent', 'speak to a person']):
        return 'This sounds like something our support team should look into directly so we can resolve it properly. Connecting you now — they will follow up shortly.'

    if any(token in text for token in ['order number', 'order no', 'order id', 'tracking number', 'email', 'test@example.com']):
        return 'Thanks for sharing that detail. I have shared it with our support team and they can use it to help you faster.'

    order_match = None
    if user is not None:
        order_number_matches = [
            re.search(r'\b(?:lm|order(?:\s*(?:number|no|id))?)\b[^0-9]{0,3}(\d{4,})\b', text, re.IGNORECASE),
            re.search(r'\b(?:my\s+)?order\s+number\s+(?:is|=|:)?\s*(\d{4,})\b', text, re.IGNORECASE),
            re.search(r'\b(?:my\s+)?order\s+(\d{4,})\b', text, re.IGNORECASE),
            re.search(r'\b(?:order|lm)\s*#?\s*(\d{4,})\b', text, re.IGNORECASE),
        ]
        for match in order_number_matches:
            if match:
                digits = match.group(1)
                order_number = f'LM{digits}'
                order_match = Order.objects.filter(user=user, order_number__iexact=order_number).first()
                if order_match is not None:
                    break

    if order_match is not None:
        status_label = dict(Order.Status.choices).get(order_match.status, order_match.status.title())
        payment_label = dict(Order.PaymentStatus.choices).get(order_match.payment_status, order_match.payment_status.title())
        return f"I checked your account and found order {order_match.order_number}. Its current status is {status_label} and payment status is {payment_label}."

    if any(keyword in text for keyword in ['order', 'delivery', 'tracking', 'where is my order', 'shipping']):
        return 'I can help with order tracking and delivery questions. Please share your order number or the email you used for the purchase.'

    if any(keyword in text for keyword in ['return', 'refund', 'exchange']):
        return 'You can request a return or exchange within a few days of delivery. Share your order number and I can help guide you through the next step.'

    if any(keyword in text for keyword in ['payment', 'paid', 'charge', 'card', 'mpesa', 'm-pesa']):
        return 'We accept secure card payments and M-Pesa. If your payment failed, please check your card details or try again shortly.'

    if any(keyword in text for keyword in ['size', 'fit', 'slim fit', 'regular fit', 'true to size']):
        return 'We can help with sizing and fit. Tell me the product you are looking at and your usual size, and I will guide you from there.'

    if any(keyword in text for keyword in ['coupon', 'discount', 'promo', 'offer']):
        return 'We often run promotions and discount codes. If you have a code, share it and I can help check whether it is still valid.'

    if any(keyword in text for keyword in ['contact', 'email', 'support']):
        return 'You can also reach us through the contact page or by replying here. If this is urgent, ask for human support and we will escalate it.'

    return 'I want to make sure I get this right for you — could you rephrase that, or would you like me to connect you with our support team directly?'


@method_decorator(staff_member_required, name='dispatch')
class SupportTicketListView(ListView):
    model = SupportTicket
    template_name = 'support/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 25


@method_decorator(staff_member_required, name='dispatch')
class SupportTicketAdminListView(ListView):
    model = SupportTicket
    template_name = 'support/ticket_list_admin.html'
    context_object_name = 'tickets'
    paginate_by = 25

    def get_queryset(self):
        return SupportTicket.objects.filter(status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.PENDING]).order_by('-updated_at')


@method_decorator(staff_member_required, name='dispatch')
class SupportTicketDetailView(DetailView):
    model = SupportTicket
    template_name = 'support/ticket_detail.html'
    context_object_name = 'ticket'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ticket_messages'] = self.object.messages.select_related('sender').all()
        return context


@login_required
def create_support_ticket(request):
    if request.method == 'POST':
        subject = (request.POST.get('subject') or 'General support').strip()
        description = (request.POST.get('message') or '').strip()
        if not description:
            messages.error(request, 'Please write your question before sending.')
            return redirect('products:shop')

        ticket = SupportTicket.objects.create(
            user=request.user if request.user.is_authenticated else None,
            email=request.user.email if request.user.is_authenticated else request.POST.get('email', ''),
            subject=subject,
            description=description,
            status=SupportTicket.Status.OPEN,
        )
        SupportMessage.objects.create(ticket=ticket, sender=request.user if request.user.is_authenticated else None, body=description, is_from_customer=True)

        needs_human_support = 'human support' in description.lower() or 'live help' in description.lower() or 'agent' in description.lower()
        staff_users = list(User.objects.filter(is_active=True, is_staff=True).iterator())

        auto_reply_body = (
            'Thanks for contacting Luxe Men. We have received your request and will help you shortly. '
            'If you need a live human support specialist, please type “human support”.'
        )

        if needs_human_support:
            SupportMessage.objects.create(
                ticket=ticket,
                sender=None,
                body='We are escalating this to a human support specialist. Please hold while we connect you.',
                is_from_customer=False,
            )
            for admin in staff_users:
                Notification.create(
                    admin,
                    title='Urgent human support request',
                    message=f'A customer requested urgent human support: {ticket.subject}',
                    target_url=reverse('support:ticket_detail', kwargs={'pk': ticket.pk}),
                    level='warning',
                )
            messages.success(request, 'A human support specialist has been notified. Please stay on this chat.')
        else:
            SupportMessage.objects.create(
                ticket=ticket,
                sender=None,
                body=auto_reply_body,
                is_from_customer=False,
            )
            if staff_users:
                for admin in staff_users:
                    Notification.create(
                        admin,
                        title='New support ticket',
                        message=f'A new support conversation was started: {ticket.subject}',
                        target_url=reverse('support:ticket_detail', kwargs={'pk': ticket.pk}),
                        level='info',
                    )
                messages.success(request, 'Your support chat has started. A team member will reply shortly.')
            else:
                SupportMessage.objects.create(
                    ticket=ticket,
                    sender=None,
                    body='No support agent is currently available. Your message has been received and we will follow up as soon as possible.',
                    is_from_customer=False,
                )
                messages.success(request, 'No support agent is currently available. We have queued your request and will follow up shortly.')
        return redirect('support:ticket_thread', pk=ticket.pk)
    return redirect('products:shop')


@login_required
def ticket_thread(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if not (request.user.is_staff or ticket.user_id == request.user.id):
        return render(request, '404.html', status=404)

    if request.method == 'POST':
        body = (request.POST.get('message') or '').strip()
        if body:
            is_from_customer = not request.user.is_staff
            SupportMessage.objects.create(ticket=ticket, sender=request.user, body=body, is_from_customer=is_from_customer)
            if request.user.is_staff:
                ticket.status = SupportTicket.Status.PENDING
                ticket.last_response_at = timezone.now()
                ticket.save(update_fields=['status', 'last_response_at'])
            else:
                reply_body = get_chatbot_reply(body, request.user)
                if reply_body:
                    SupportMessage.objects.create(
                        ticket=ticket,
                        sender=None,
                        body=reply_body,
                        is_from_customer=False,
                    )
                for admin in User.objects.filter(is_active=True, is_staff=True).iterator():
                    Notification.create(
                        admin,
                        title='New customer reply',
                        message=f'A customer replied to support ticket: {ticket.subject}',
                        target_url=reverse('support:ticket_detail', kwargs={'pk': ticket.pk}),
                        level='info',
                    )
            messages.success(request, 'Message sent.')
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
            if is_ajax:
                reply_body = None
                if not request.user.is_staff:
                    reply_body = get_chatbot_reply(body, request.user)
                return JsonResponse({'success': True, 'message': 'Message sent.', 'reply_body': reply_body})
        return redirect('support:ticket_thread', pk=ticket.pk)

    thread_messages = ticket.messages.select_related('sender').all()
    suggestions = [
        'Where is my order?',
        'How do I return an item?',
        'What payment methods do you accept?',
        'How do I contact a human?',
    ]
    return render(request, 'support/thread.html', {'ticket': ticket, 'thread_messages': thread_messages, 'suggestions': suggestions})


@staff_member_required
@require_POST
def staff_reply(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    body = (request.POST.get('message') or '').strip()
    if body:
        SupportMessage.objects.create(ticket=ticket, sender=request.user, body=body, is_from_customer=False)
        ticket.status = SupportTicket.Status.PENDING
        ticket.last_response_at = timezone.now()
        ticket.save(update_fields=['status', 'last_response_at'])
        messages.success(request, 'Reply sent.')
    return redirect('support:ticket_detail', pk=ticket.pk)


@staff_member_required
@require_POST
def close_ticket(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    ticket.status = SupportTicket.Status.CLOSED
    ticket.last_response_at = timezone.now()
    ticket.save(update_fields=['status', 'last_response_at'])
    messages.success(request, 'Ticket closed.')
    return redirect('support:ticket_detail', pk=ticket.pk)


@method_decorator(staff_member_required, name='dispatch')
class CallbackRequestListView(ListView):
    model = CallbackRequest
    template_name = 'support/callback_request_list.html'
    context_object_name = 'callback_requests'
    paginate_by = 25

