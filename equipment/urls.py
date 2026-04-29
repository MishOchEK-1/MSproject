from django.urls import path

from .views import EquipmentDetailView, EquipmentListView, EquipmentScheduleView


app_name = 'equipment'

urlpatterns = [
    path('', EquipmentListView.as_view(), name='list'),
    path('schedule/', EquipmentScheduleView.as_view(), name='schedule'),
    path('<int:pk>/', EquipmentDetailView.as_view(), name='detail'),
]
