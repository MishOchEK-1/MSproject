from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        return (
            Notification.objects.filter(recipient=self.request.user)
            .select_related('actor', 'reservation__equipment')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_notifications'] = [item for item in context['notifications'] if not item.is_read]
        context['read_notifications'] = [item for item in context['notifications'] if item.is_read]
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        notification = get_object_or_404(Notification, pk=kwargs['pk'], recipient=request.user)
        notification.mark_as_read()
        messages.success(request, 'Уведомление отмечено как прочитанное.')
        return redirect('notifications:list')


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        unread = Notification.objects.filter(recipient=request.user, is_read=False)
        for notification in unread:
            notification.mark_as_read()
        messages.success(request, 'Все уведомления отмечены как прочитанные.')
        return redirect('notifications:list')
