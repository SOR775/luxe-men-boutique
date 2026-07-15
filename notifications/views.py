from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, View

from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = 'notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class NotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notif = Notification.objects.filter(user=request.user, pk=pk).first()
        if notif:
            notif.is_read = True
            notif.save(update_fields=['is_read'])
            if notif.target_url:
                return redirect(notif.target_url)
        return redirect(reverse('notifications:list'))


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return redirect(reverse('notifications:list'))


class NotificationRecentAPIView(LoginRequiredMixin, View):
    """Return recent notifications as JSON for the navbar dropdown."""

    def get(self, request):
        qs = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
        data = []
        for n in qs:
            payload = n.payload.copy()
            payload.update({
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            })
            data.append(payload)
        return JsonResponse({'notifications': data})


class NotificationMarkReadAPIView(LoginRequiredMixin, View):
    """Mark a notification as read (expects POST with `id`)."""

    def post(self, request):
        try:
            import json
            body = json.loads(request.body.decode('utf-8') or '{}')
            nid = body.get('id')
            if not nid:
                return JsonResponse({'success': False, 'error': 'missing id'}, status=400)

            notif = Notification.objects.filter(user=request.user, id=nid).first()
            if not notif:
                return JsonResponse({'success': False, 'error': 'not found'}, status=404)

            if not notif.is_read:
                notif.is_read = True
                notif.save(update_fields=['is_read'])

            return JsonResponse({'success': True})
        except Exception:
            return JsonResponse({'success': False}, status=500)

