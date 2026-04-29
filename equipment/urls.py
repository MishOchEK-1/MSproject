from django.urls import path

from .views import EquipmentDetailView, EquipmentListView


app_name = 'equipment'

urlpatterns = [
    path('', EquipmentListView.as_view(), name='list'),
    path('<int:pk>/', EquipmentDetailView.as_view(), name='detail'),
]
