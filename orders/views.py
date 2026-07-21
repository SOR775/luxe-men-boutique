"""
orders/views.py — Cart & Checkout Views
"""
import json
from decimal import Decimal
from uuid import UUID

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError

from products.models import Product, ProductVariant
from notifications.models import Notification
from .forms import CouponForm
from .models import Cart, CartItem, Order, OrderItem, OrderEvent, Coupon, ReturnRequest, ShippingRate


# ─── Cart Helpers ─────────────────────────────────────────────────────────────

def get_or_create_cart(request) -> Cart:
    """Get the active cart for the current user or session."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key)
        return cart


def redirect_to_cart():
    return redirect('/cart/')


def get_cart_promo_context(cart):
    free_shipping_threshold = Decimal('5000.00')
    subtotal = cart.subtotal or Decimal('0')
    remaining = max(free_shipping_threshold - subtotal, Decimal('0'))
    progress = min(100, int((subtotal / free_shipping_threshold) * 100)) if free_shipping_threshold else 100
    promo_message = None
    if remaining > 0:
        promo_message = f'Add KES {remaining:.2f} more for free shipping.'
    else:
        promo_message = 'You unlocked free shipping!'

    return {
        'promo_message': promo_message,
        'free_shipping_remaining': remaining,
        'free_shipping_progress': progress,
    }


def get_cart_financial_context(cart, shipping_region='Nairobi'):
    """Return estimated shipping, tax and total for cart summary."""
    subtotal = cart.subtotal or Decimal('0')

    if subtotal >= Decimal('5000.00'):
        shipping_cost = Decimal('0.00')
    elif shipping_region and shipping_region.lower() == 'nairobi':
        shipping_cost = Decimal('250.00')
    else:
        shipping_cost = Decimal('400.00')

    tax_rate = Decimal('0.16')
    tax_amount = subtotal * tax_rate
    estimated_total = subtotal + shipping_cost + tax_amount

    return {
        'shipping_cost': shipping_cost,
        'tax_amount': round(tax_amount, 2),
        'estimated_total': round(estimated_total, 2),
    }


def get_cart_recommendations(cart, limit=3):
    """Suggest complementary products from the same category as items already in the cart."""
    if not cart or not getattr(cart, 'pk', None):
        return []

    cart_product_ids = set(
        CartItem.objects.filter(cart=cart).values_list('variant__product_id', flat=True)
    )
    category_ids = set(
        CartItem.objects.filter(cart=cart).values_list('variant__product__category_id', flat=True)
    )

    if not category_ids:
        return []

    products = (
        Product.objects.filter(
            category_id__in=category_ids,
            visibility=Product.Visibility.PUBLISHED,
        )
        .exclude(id__in=cart_product_ids)
        .exclude(variants__isnull=True)
        .distinct()
        .order_by('-is_featured', '-is_trending', '-created_at')[:limit]
    )
    return list(products)


# ─── Cart Views ───────────────────────────────────────────────────────────────

class CartView(View):
    template_name = 'orders/cart.html'

    def get(self, request):
        cart = get_or_create_cart(request)
        items = cart.items.select_related(
            'variant', 'variant__product'
        ).prefetch_related('variant__product__images')

        shipping_region = request.GET.get('shipping_region') or request.session.get('shipping_region') or 'Nairobi'
        if shipping_region:
            request.session['shipping_region'] = shipping_region
        promo_context = get_cart_promo_context(cart)
        financial_context = get_cart_financial_context(cart, shipping_region)

        # Apply coupon (if present in session) to cart totals so discounts show on cart page
        coupon = None
        discount = Decimal('0')
        coupon_id = request.session.get('coupon_id')
        if coupon_id:
            try:
                coupon = Coupon.objects.get(pk=coupon_id)
                discount = coupon.compute_discount(cart.subtotal)
            except Coupon.DoesNotExist:
                coupon = None

        # Adjust estimated total to reflect coupon discount
        shipping_cost = financial_context.get('shipping_cost', Decimal('0'))
        estimated_total = (cart.subtotal or Decimal('0')) - discount + shipping_cost
        financial_context.update({
            'discount': discount,
            'coupon': coupon,
            'estimated_total': round(estimated_total, 2),
        })
        recommendations = get_cart_recommendations(cart)

        # saved for later (session-backed)
        saved_for_later = get_saved_for_later(request)

        return render(request, self.template_name, {
            'cart': cart,
            'items': items,
            'recommendations': recommendations,
            'saved_for_later': saved_for_later,
            'shipping_region': shipping_region,
            **promo_context,
            **financial_context,
        })


def get_saved_for_later(request):
    """Return a list of ProductVariant objects that the user saved for later (session-backed)."""
    try:
        saved = request.session.get('saved_for_later', []) or []
        # ensure list
        if isinstance(saved, str):
            saved = [saved]
        from products.models import ProductVariant
        variants = list(ProductVariant.objects.filter(id__in=saved, is_active=True)) if saved else []
        return variants
    except Exception:
        return []


class SaveForLaterView(View):
    """Move a cart item to the session-backed saved-for-later list."""

    def post(self, request, item_id):
        item = get_object_or_404(CartItem, pk=item_id)
        variant = item.variant
        variant_id = str(variant.id)
        product_name = variant.product.name
        product_slug = variant.product.slug
        # remove item from cart
        item.delete()

        saved = request.session.get('saved_for_later', []) or []
        if variant_id not in saved:
            saved.append(variant_id)
            request.session['saved_for_later'] = saved
            request.session.modified = True

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'action': 'saved_for_later',
                'variant_id': variant_id,
                'product_name': product_name,
                'product_slug': product_slug,
            })

        messages.success(request, 'Item saved for later.')
        return redirect_to_cart()


class MoveSavedToCartView(View):
    """Move a saved variant back into the active cart."""

    def post(self, request, variant_id):
        from products.models import ProductVariant
        try:
            variant = ProductVariant.objects.get(pk=variant_id, is_active=True)
        except ProductVariant.DoesNotExist:
            messages.error(request, 'This item is no longer available.')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'not_found'})
            return redirect_to_cart()

        cart = get_or_create_cart(request)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        # remove from saved list
        saved = request.session.get('saved_for_later', []) or []
        variant_str = str(variant.id)
        if variant_str in saved:
            saved.remove(variant_str)
            request.session['saved_for_later'] = saved
            request.session.modified = True

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'action': 'moved_to_cart', 'variant_id': variant_str})

        messages.success(request, 'Moved item back to your cart.')
        return redirect_to_cart()


class RemoveSavedFromListView(View):
    def post(self, request, variant_id):
        saved = request.session.get('saved_for_later', []) or []
        variant_str = str(variant_id)
        if variant_str in saved:
            saved.remove(variant_str)
            request.session['saved_for_later'] = saved
            request.session.modified = True

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'action': 'removed_saved', 'variant_id': variant_str})

        messages.info(request, 'Removed saved item.')
        return redirect_to_cart()


class AddToCartView(View):
    """Add a product variant to the cart (supports AJAX)."""

    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'

        if request.content_type and 'application/json' in request.content_type.lower():
            try:
                raw_body_text = request.body.decode('utf-8')
                parsed_data = json.loads(raw_body_text)
                data = parsed_data if isinstance(parsed_data, dict) else {}
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, ValueError):
                data = {}
        else:
            data = request.POST

        variant_id = (data.get('variant_id') or '').strip()
        product_id = (data.get('product_id') or '').strip()
        quantity_value = data.get('quantity', 1)
        try:
            quantity = int(quantity_value)
        except (TypeError, ValueError):
            quantity = 1
        if quantity < 1:
            quantity = 1

        variant = None
        if variant_id:
            try:
                variant = ProductVariant.objects.get(pk=variant_id, is_active=True)
            except (ProductVariant.DoesNotExist, ValidationError, ValueError):
                variant = None

        if not variant and product_id:
            try:
                product = Product.objects.get(pk=UUID(product_id))
            except (ValidationError, ValueError, TypeError, Product.DoesNotExist):
                product = None
            if product:
                variant = product.variants.filter(is_active=True).order_by('sku').first()

        if not variant:
            message = 'This product is currently unavailable.'
            if is_ajax:
                return JsonResponse({'success': False, 'status': 'error', 'message': message}, status=200)
            messages.error(request, message)
            return redirect(request.META.get('HTTP_REFERER') or 'products:shop')

        cart    = get_or_create_cart(request)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)
        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity
        cart_item.save()

        if is_ajax:
            return JsonResponse({
                'success': True,
                'status': 'success',
                'message': f'"{variant.product.name}" added to cart.',
                'cart_total_items': cart.total_items,
                'total_items': cart.total_items,
            })

        messages.success(request, f'"{variant.product.name}" added to your cart.')
        return redirect_to_cart()


class UpdateCartView(View):
    """Update quantity or remove a cart item."""

    def post(self, request, item_id):
        item     = get_object_or_404(CartItem, pk=item_id)
        quantity = int(request.POST.get('quantity', 0))

        if quantity <= 0:
            item.delete()
            messages.info(request, 'Item removed from cart.')
        else:
            item.quantity = quantity
            item.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            cart = get_or_create_cart(request)
            return JsonResponse({'success': True, 'subtotal': str(cart.subtotal)})

        return redirect_to_cart()


class RemoveFromCartView(View):
    def post(self, request, item_id):
        item = get_object_or_404(CartItem, pk=item_id)
        item.delete()
        messages.info(request, 'Item removed from cart.')
        return redirect_to_cart()


class ApplyCouponView(View):
    def post(self, request):
        code = request.POST.get('coupon_code', '').strip().upper()
        cart = get_or_create_cart(request)

        try:
            coupon = Coupon.objects.get(code=code)
            if coupon.is_valid():
                if cart.subtotal < coupon.minimum_order_amount:
                    messages.error(request, f'Minimum order of KES {coupon.minimum_order_amount} required.')
                else:
                    request.session['coupon_id'] = str(coupon.id)
                    discount = coupon.compute_discount(cart.subtotal)
                    messages.success(request, f'Coupon "{code}" applied! You save KES {discount}.')
            else:
                messages.error(request, 'This coupon is expired or invalid.')
        except Coupon.DoesNotExist:
            messages.error(request, f'Coupon "{code}" not found.')

        return redirect_to_cart()


class AdminCouponListView(LoginRequiredMixin, TemplateView):
    template_name = 'orders/admin/coupon_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['coupons'] = Coupon.objects.order_by('-created_at')
        return context


class AdminCouponCreateView(LoginRequiredMixin, View):
    template_name = 'orders/admin/coupon_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = CouponForm()
        return render(request, self.template_name, {'form': form, 'is_edit': False})

    def post(self, request):
        form = CouponForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon created successfully.')
            return redirect('orders:admin_coupons')
        return render(request, self.template_name, {'form': form, 'is_edit': False})


class AdminCouponEditView(LoginRequiredMixin, View):
    template_name = 'orders/admin/coupon_form.html'

    def dispatch(self, request, pk, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        self.coupon = get_object_or_404(Coupon, pk=pk)
        return super().dispatch(request, pk, *args, **kwargs)

    def get(self, request, pk):
        form = CouponForm(instance=self.coupon)
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'coupon': self.coupon})

    def post(self, request, pk):
        form = CouponForm(request.POST, instance=self.coupon)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon updated successfully.')
            return redirect('orders:admin_coupons')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'coupon': self.coupon})


# ─── Checkout Views ───────────────────────────────────────────────────────────

class CheckoutView(View):
    template_name = 'orders/checkout.html'

    def get_cart_context(self, request):
        cart    = get_or_create_cart(request)
        items   = cart.items.select_related('variant__product')
        coupon  = None
        discount = Decimal('0')
        coupon_id = request.session.get('coupon_id')
        if coupon_id:
            try:
                coupon   = Coupon.objects.get(pk=coupon_id)
                discount = coupon.compute_discount(cart.subtotal)
            except Coupon.DoesNotExist:
                pass

        shipping_rates = ShippingRate.objects.filter(is_active=True).select_related('zone')
        return {
            'cart': cart,
            'items': items,
            'coupon': coupon,
            'discount': discount,
            'shipping_rates': shipping_rates,
        }

    def get(self, request):
        cart = get_or_create_cart(request)
        if cart.total_items == 0:
            messages.warning(request, 'Your cart is empty.')
            return redirect_to_cart()
        context = self.get_cart_context(request)
        # Pre-fill from user profile
        if request.user.is_authenticated:
            default_address = request.user.addresses.filter(is_default=True).first()
            context['default_address'] = default_address
            context['default_phone'] = request.user.phone or ''
        else:
            context['default_phone'] = ''
        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request):
        cart = get_or_create_cart(request)
        if cart.total_items == 0:
            return redirect_to_cart()

        # Gather shipping details
        shipping_name    = request.POST.get('full_name', '')
        shipping_phone   = request.POST.get('phone', '')
        shipping_email   = request.POST.get('email', request.user.email if request.user.is_authenticated else '')
        shipping_address = request.POST.get('address', '')
        shipping_city    = request.POST.get('city', '')
        shipping_rate_id = request.POST.get('shipping_rate')
        customer_notes   = request.POST.get('notes', '')
        delivery_latitude = request.POST.get('delivery_latitude', '').strip() or None
        delivery_longitude = request.POST.get('delivery_longitude', '').strip() or None
        delivery_location_note = request.POST.get('delivery_location_note', '').strip()

        shipping_rate = None
        shipping_cost = Decimal('0')
        if shipping_rate_id:
            try:
                shipping_rate = ShippingRate.objects.get(pk=shipping_rate_id)
                if shipping_rate.free_above and cart.subtotal >= shipping_rate.free_above:
                    shipping_cost = Decimal('0')
                else:
                    shipping_cost = shipping_rate.price
            except ShippingRate.DoesNotExist:
                pass

        # Coupon
        coupon = None
        discount = Decimal('0')
        coupon_id = request.session.get('coupon_id')
        if coupon_id:
            try:
                coupon   = Coupon.objects.get(pk=coupon_id)
                discount = coupon.compute_discount(cart.subtotal)
                coupon.times_used += 1
                coupon.save(update_fields=['times_used'])
            except Coupon.DoesNotExist:
                pass

        subtotal = cart.subtotal
        total    = subtotal - discount + shipping_cost

        # Create Order
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_email=shipping_email,
            shipping_address=shipping_address,
            shipping_city=shipping_city,
            shipping_rate=shipping_rate,
            delivery_latitude=Decimal(delivery_latitude) if delivery_latitude else None,
            delivery_longitude=Decimal(delivery_longitude) if delivery_longitude else None,
            delivery_location_note=delivery_location_note,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            discount_amount=discount,
            total=total,
            coupon=coupon,
            customer_notes=customer_notes,
        )

        # Migrate cart items → order items
        for cart_item in cart.items.select_related('variant__product'):
            variant = cart_item.variant
            OrderItem.objects.create(
                order=order,
                variant=variant,
                product_name=variant.product.name,
                variant_detail=str(variant),
                sku=variant.sku,
                unit_price=variant.final_price,
                quantity=cart_item.quantity,
                line_total=cart_item.line_total,
            )

        # Create first order event
        OrderEvent.objects.create(
            order=order,
            message='Order placed successfully.',
            created_by=request.user if request.user.is_authenticated else None,
        )

        if request.user.is_authenticated:
            try:
                Notification.create(
                    user=request.user,
                    title=f'Order #{order.order_number} confirmed',
                    message='Your order has been placed successfully. We will notify you when it ships.',
                    target_url=reverse('orders:order_detail', kwargs={'order_number': order.order_number}),
                    level=Notification.Level.SUCCESS,
                    send_sms=True,
                )
            except Exception:
                pass

        # Clear cart and session coupon
        cart.items.all().delete()
        if 'coupon_id' in request.session:
            del request.session['coupon_id']

        # Redirect to payment selection
        return redirect('payments:select', order_id=order.id)


# ─── Order Views ──────────────────────────────────────────────────────────────

class OrderDetailView(LoginRequiredMixin, View):
    template_name = 'orders/order_detail.html'

    def get(self, request, order_number):
        order_queryset = Order.objects.select_related('escrow').prefetch_related('items', 'events', 'payments')
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)

        order = get_object_or_404(order_queryset, order_number=order_number)
        escrow = getattr(order, 'escrow', None)
        return render(request, self.template_name, {
            'order': order,
            'items': order.items.all(),
            'events': order.events.all(),
            'escrow': escrow,
        })


class OrderListView(LoginRequiredMixin, View):
    template_name = 'orders/order_list.html'

    def get(self, request):
        orders = Order.objects.filter(user=request.user).select_related('escrow').order_by('-created_at')
        return render(request, self.template_name, {'orders': orders})


class AdminOrderListView(LoginRequiredMixin, View):
    template_name = 'orders/admin_order_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        orders = Order.objects.select_related('escrow', 'user').order_by('-created_at')
        return render(request, self.template_name, {'orders': orders})


class AdminBulkOrderActionsView(LoginRequiredMixin, View):
    template_name = 'orders/admin_bulk_actions.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.db.models import Q

        orders = Order.objects.select_related('user').order_by('-created_at')
        search_query = request.GET.get('q', '').strip()
        if search_query:
            orders = orders.filter(
                Q(order_number__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(shipping_email__icontains=search_query)
            )
        status_filter = request.GET.get('status', '').strip()
        if status_filter:
            orders = orders.filter(status=status_filter)

        return render(request, self.template_name, {
            'orders': orders[:200],
            'search_query': search_query,
            'status_filter': status_filter,
            'statuses': Order.Status.choices,
        })

    def post(self, request):
        action = request.POST.get('action')
        order_ids = request.POST.getlist('order_ids')
        orders = Order.objects.filter(order_number__in=order_ids)
        changed = 0

        if not order_ids:
            messages.error(request, 'No orders selected for bulk action.')
            return redirect('orders:admin_bulk_actions')

        for order in orders:
            if action == 'mark_shipped' and order.status not in [Order.Status.SHIPPED, Order.Status.COMPLETED, Order.Status.CANCELLED]:
                order.status = Order.Status.SHIPPED
            elif action == 'mark_delivered' and order.status not in [Order.Status.DELIVERED, Order.Status.COMPLETED, Order.Status.CANCELLED]:
                order.status = Order.Status.DELIVERED
            elif action == 'mark_returned' and order.status not in [Order.Status.RETURNED, Order.Status.REFUNDED, Order.Status.CANCELLED]:
                order.status = Order.Status.RETURNED
            elif action == 'cancel_order' and order.status not in [Order.Status.CANCELLED, Order.Status.COMPLETED]:
                order.status = Order.Status.CANCELLED
            else:
                continue

            order.save(update_fields=['status', 'updated_at'])
            OrderEvent.objects.create(
                order=order,
                message=f'Order status updated to {order.get_status_display()} by staff.',
                created_by=request.user,
            )
            if order.user:
                try:
                    Notification.create(
                        user=order.user,
                        title=f'Order {order.order_number} status updated',
                        message=f'Your order status is now {order.get_status_display()}.',
                        target_url=reverse('orders:order_detail', kwargs={'order_number': order.order_number}),
                        level=Notification.Level.INFO,
                        send_sms=False,
                    )
                except Exception:
                    pass
            changed += 1

        if changed:
            messages.success(request, f'Bulk action completed for {changed} orders.')
        else:
            messages.info(request, 'No orders were updated.')
        return redirect('orders:admin_bulk_actions')


class AdminOrderInvoiceView(LoginRequiredMixin, View):
    template_name = 'orders/admin_order_invoice.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_number):
        order = get_object_or_404(Order.objects.select_related('user', 'escrow').prefetch_related('items'), order_number=order_number)
        return render(request, self.template_name, {'order': order, 'items': order.items.all()})


class AdminRMAListView(LoginRequiredMixin, TemplateView):
    template_name = 'orders/admin_rma_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['returns'] = ReturnRequest.objects.select_related('order', 'user').order_by('-created_at')
        return context


class AdminRMAUpdateView(LoginRequiredMixin, View):
    template_name = 'orders/admin_rma_update.html'

    def dispatch(self, request, pk, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        self.return_request = get_object_or_404(ReturnRequest.objects.select_related('order', 'user'), pk=pk)
        return super().dispatch(request, pk, *args, **kwargs)

    def get(self, request, pk):
        return render(request, self.template_name, {'return_request': self.return_request})

    def post(self, request, pk):
        new_status = request.POST.get('status')
        admin_response = request.POST.get('admin_response', '').strip()

        if new_status in dict(ReturnRequest.Status.choices):
            self.return_request.status = new_status
        self.return_request.admin_response = admin_response
        self.return_request.save(update_fields=['status', 'admin_response', 'updated_at'])

        if self.return_request.status == ReturnRequest.Status.COMPLETED:
            self.return_request.complete(actor=request.user)

        OrderEvent.objects.create(
            order=self.return_request.order,
            message=f'Return request {self.return_request.get_status_display()} by staff.',
            created_by=request.user,
        )

        try:
            Notification.create(
                user=self.return_request.user,
                title=f'Return request {self.return_request.get_status_display()}',
                message=f'Your return request for order {self.return_request.order.order_number} is now {self.return_request.get_status_display()}.',
                target_url=reverse('orders:order_detail', kwargs={'order_number': self.return_request.order.order_number}),
                level=Notification.Level.INFO,
                send_sms=False,
            )
        except Exception:
            pass

        messages.success(request, 'RMA status updated successfully.')
        return redirect('orders:admin_rma')


class AdminRevenueeDashboardView(LoginRequiredMixin, View):
    """Admin dashboard showing all system revenue from paid orders."""
    template_name = 'orders/admin_revenue_dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.db.models import Sum, Q, F, Count
        
        # Get all orders that have been paid/completed
        orders = Order.objects.filter(
            status__in=[Order.Status.PAID, Order.Status.ESCROW, Order.Status.COMPLETED, Order.Status.SHIPPED, Order.Status.DELIVERED]
        ).select_related('user', 'escrow', 'shipping_rate').prefetch_related('items').order_by('-created_at')
        
        # Financial summary
        total_revenue = orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
        total_orders = orders.count()
        total_items_sold = orders.aggregate(total=Count('items'))['total'] or 0
        avg_order_value = (total_revenue / total_orders) if total_orders > 0 else Decimal('0')
        
        # Status breakdown
        status_breakdown = {
            'paid': orders.filter(status=Order.Status.PAID).count(),
            'escrow': orders.filter(status=Order.Status.ESCROW).count(),
            'shipped': orders.filter(status=Order.Status.SHIPPED).count(),
            'delivered': orders.filter(status=Order.Status.DELIVERED).count(),
            'completed': orders.filter(status=Order.Status.COMPLETED).count(),
        }
        
        # Search/filter
        search_query = request.GET.get('q', '').strip()
        if search_query:
            orders = orders.filter(
                Q(order_number__icontains=search_query) |
                Q(shipping_email__icontains=search_query) |
                Q(shipping_phone__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(shipping_name__icontains=search_query) |
                Q(shipping_city__icontains=search_query)
            )
        
        # Status filter
        status_filter = request.GET.get('status', '').strip()
        if status_filter:
            orders = orders.filter(status=status_filter)
        
        return render(request, self.template_name, {
            'orders': orders[:100],  # Limit to 100 most recent
            'total_revenue': total_revenue,
            'total_orders': total_orders,
            'total_items_sold': total_items_sold,
            'avg_order_value': round(avg_order_value, 2),
            'status_breakdown': status_breakdown,
            'search_query': search_query,
            'status_filter': status_filter,
        })


class OrderReceiptView(LoginRequiredMixin, View):
    """View a printable receipt for an order."""
    template_name = 'orders/receipt.html'

    def get(self, request, order_number):
        order_queryset = Order.objects.all()
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)

        order = get_object_or_404(order_queryset, order_number=order_number)
        payments = list(order.payments.select_related('order').all())
        payment = payments[0] if payments else None
        payment_reference = order.order_number
        payment_method_display = 'Pending confirmation'

        if payment:
            payment_method_display = payment.get_method_display()
            if payment.reference:
                payment_reference = payment.reference
            elif payment.mpesa_transactions.exists():
                receipt_txn = payment.mpesa_transactions.order_by('-created_at').first()
                if receipt_txn and receipt_txn.mpesa_receipt_number:
                    payment_reference = receipt_txn.mpesa_receipt_number

        return render(request, self.template_name, {
            'order': order,
            'items': order.items.all(),
            'payment': payment,
            'payment_reference': payment_reference,
            'payment_method_display': payment_method_display,
            'barcode_value': order.order_number,
        })


class OrderDeleteView(LoginRequiredMixin, View):
    """Allow users to delete pending orders."""

    def post(self, request, order_number):
        order_queryset = Order.objects.all()
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)

        order = get_object_or_404(order_queryset, order_number=order_number)
        
        # Only allow deletion of pending orders
        if order.status != Order.Status.PENDING:
            messages.error(
                request,
                f'Cannot delete order in {order.get_status_display()} status. '
                f'Only pending orders can be deleted.'
            )
            return redirect('orders:order_detail', order_number=order_number)
        
        order_number_for_msg = order.order_number
        order.delete()
        messages.success(request, f'Order #{order_number_for_msg} has been deleted.')
        return redirect('orders:order_list')


class OrderEditView(LoginRequiredMixin, View):
    """Allow users to edit pending orders by moving items back to cart."""
    template_name = 'orders/edit_order.html'

    def get(self, request, order_number):
        order_queryset = Order.objects.all()
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)

        order = get_object_or_404(order_queryset, order_number=order_number)
        
        # Only allow editing of pending orders
        if order.status != Order.Status.PENDING:
            messages.error(
                request,
                f'Cannot edit order in {order.get_status_display()} status. '
                f'Only pending orders can be edited.'
            )
            return redirect('orders:order_detail', order_number=order_number)
        
        return render(request, self.template_name, {
            'order': order,
            'items': order.items.all(),
        })

    def post(self, request, order_number):
        order_queryset = Order.objects.all()
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)

        order = get_object_or_404(order_queryset, order_number=order_number)
        
        # Only allow editing of pending orders
        if order.status != Order.Status.PENDING:
            messages.error(request, 'Cannot edit this order.')
            return redirect('orders:order_detail', order_number=order_number)
        
        action = request.POST.get('action', '').strip()
        item_id = request.POST.get('item_id', '').strip()
        
        if action == 'remove_item':
            # Remove a single item from order and restore to cart
            try:
                item = order.items.get(id=item_id)
                cart = get_or_create_cart(request)
                
                # Add back to cart
                cart_item, created = CartItem.objects.get_or_create(
                    cart=cart,
                    variant=item.variant,
                    defaults={'quantity': item.quantity}
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save()
                
                # Remove from order
                item.delete()
                messages.success(request, f'Item removed from order and added to cart.')
            except OrderItem.DoesNotExist:
                messages.error(request, 'Item not found.')
            
            return redirect('orders:edit_order', order_number=order_number)
        
        elif action == 'restore_all_to_cart':
            # Move all order items back to cart and delete the order
            cart = get_or_create_cart(request)
            
            for item in order.items.all():
                cart_item, created = CartItem.objects.get_or_create(
                    cart=cart,
                    variant=item.variant,
                    defaults={'quantity': item.quantity}
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save()
            
            order_number_for_msg = order.order_number
            order.delete()
            messages.success(
                request,
                f'All items from order #{order_number_for_msg} have been added back to your cart.'
            )
            return redirect('/cart/')
        
        return redirect('orders:edit_order', order_number=order_number)

