from django.urls import path

from .views import (
    ReservationApproveView,
    ReservationCancelView,
    ReservationCreateView,
    ReservationExtendView,
    ReservationListView,
    ReservationRejectView,
    StaffReservationDashboardView,
)


app_name = 'reservations'

urlpatterns = [
    path('', ReservationListView.as_view(), name='list'),
    path('equipment/<int:equipment_id>/create/', ReservationCreateView.as_view(), name='create'),
    path('<int:pk>/cancel/', ReservationCancelView.as_view(), name='cancel'),
    path('<int:pk>/extend/', ReservationExtendView.as_view(), name='extend'),
    path('staff/dashboard/', StaffReservationDashboardView.as_view(), name='staff-dashboard'),
    path('<int:pk>/approve/', ReservationApproveView.as_view(), name='approve'),
    path('<int:pk>/reject/', ReservationRejectView.as_view(), name='reject'),
]
