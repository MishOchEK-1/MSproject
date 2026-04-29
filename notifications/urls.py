from django.urls import path

from .views import NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView


app_name = 'notifications'

urlpatterns = [
    path('', NotificationListView.as_view(), name='list'),
    path('<int:pk>/read/', NotificationMarkReadView.as_view(), name='read'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='read-all'),
]
