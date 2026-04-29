from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView, ListView, TemplateView

from equipment.models import Equipment, EquipmentStatus

from .forms import (
    ReservationCancelForm,
    ReservationCreateForm,
    ReservationDecisionForm,
    ReservationExtensionForm,
)
from .models import Reservation, ReservationStatus
from .services import (
    approve_reservation,
    cancel_reservation,
    create_reservation,
    extend_reservation,
    reject_reservation,
    sync_reservation_lifecycle,
)


class ReservationListView(LoginRequiredMixin, ListView):
    model = Reservation
    template_name = 'reservations/reservation_list.html'
    context_object_name = 'reservations'

    def get_queryset(self):
        sync_reservation_lifecycle()
        return Reservation.objects.filter(user=self.request.user).select_related('equipment').order_by('-start_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['upcoming'] = [r for r in context['reservations'] if r.status in Reservation.ACTIVE_STATUSES]
        context['history'] = [r for r in context['reservations'] if r.status not in Reservation.ACTIVE_STATUSES]
        return context


class ReservationCreateView(LoginRequiredMixin, FormView):
    form_class = ReservationCreateForm
    template_name = 'reservations/reservation_form.html'

    def dispatch(self, request, *args, **kwargs):
        sync_reservation_lifecycle()
        self.equipment = get_object_or_404(Equipment, pk=self.kwargs['equipment_id'])
        if not self.equipment.is_bookable:
            messages.error(request, 'Это оборудование сейчас недоступно для бронирования.')
            return redirect('equipment:detail', pk=self.equipment.pk)
        if not request.user.can_book_equipment(self.equipment):
            messages.error(request, 'Для бронирования этого оборудования требуется пройденный инструктаж.')
            return redirect('equipment:detail', pk=self.equipment.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['duration_minutes'].initial = self.equipment.slot_duration_minutes
        return form

    def form_valid(self, form):
        try:
            reservation = create_reservation(
                user=self.request.user,
                equipment=self.equipment,
                start_at=form.cleaned_data['start_at'],
                duration_minutes=form.cleaned_data['duration_minutes'],
                request_comment=form.cleaned_data['request_comment'],
            )
        except ValidationError as exc:
            for error_list in exc.message_dict.values():
                for error in error_list:
                    form.add_error(None, error)
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, 'Не удалось создать бронь. Проверьте выбранное время и попробуйте снова.')
            return self.form_invalid(form)

        if reservation.status == ReservationStatus.PENDING:
            messages.success(self.request, 'Заявка отправлена на подтверждение персоналу.')
        else:
            messages.success(self.request, 'Бронь создана и подтверждена автоматически.')
        return redirect('reservations:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['equipment'] = self.equipment
        return context


class ReservationCancelView(LoginRequiredMixin, FormView):
    form_class = ReservationCancelForm
    template_name = 'reservations/reservation_cancel.html'

    def dispatch(self, request, *args, **kwargs):
        sync_reservation_lifecycle()
        self.reservation = get_object_or_404(
            Reservation.objects.select_related('equipment', 'user'),
            pk=self.kwargs['pk'],
        )
        if not self.reservation.can_be_cancelled_by(request.user):
            return HttpResponseForbidden('Недостаточно прав для отмены этой брони.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        reason = form.cleaned_data['cancellation_reason'].strip()
        if self.request.user != self.reservation.user and not reason:
            form.add_error('cancellation_reason', 'Для экстренной отмены персоналом нужен комментарий.')
            return self.form_invalid(form)

        cancel_reservation(reservation=self.reservation, actor=self.request.user, reason=reason)
        messages.success(self.request, 'Бронь отменена.')
        return redirect('reservations:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reservation'] = self.reservation
        return context


class ReservationExtendView(LoginRequiredMixin, FormView):
    form_class = ReservationExtensionForm
    template_name = 'reservations/reservation_extend.html'

    def dispatch(self, request, *args, **kwargs):
        sync_reservation_lifecycle()
        self.reservation = get_object_or_404(
            Reservation.objects.select_related('equipment', 'user'),
            pk=self.kwargs['pk'],
            user=request.user,
        )
        if self.reservation.status not in Reservation.ACTIVE_STATUSES:
            messages.error(request, 'Продлить можно только активную бронь.')
            return redirect('reservations:list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            extend_reservation(
                reservation=self.reservation,
                actor=self.request.user,
                extra_minutes=form.cleaned_data['extra_minutes'],
            )
        except ValidationError as exc:
            for error_list in exc.message_dict.values():
                for error in error_list:
                    form.add_error(None, error)
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, 'Не удалось продлить бронь. Возможно, дальше уже есть другая запись.')
            return self.form_invalid(form)

        messages.success(self.request, 'Бронь продлена.')
        return redirect('reservations:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reservation'] = self.reservation
        return context


class StaffReservationAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_review_reservations


class StaffReservationDashboardView(StaffReservationAccessMixin, TemplateView):
    template_name = 'reservations/staff_dashboard.html'

    def get_context_data(self, **kwargs):
        sync_reservation_lifecycle()
        context = super().get_context_data(**kwargs)
        pending = Reservation.objects.filter(status=ReservationStatus.PENDING).select_related('equipment', 'user')
        problem_statuses = [
            ReservationStatus.REJECTED,
            ReservationStatus.EXPIRED,
            ReservationStatus.CANCELLED,
        ]
        problem_reservations = Reservation.objects.filter(status__in=problem_statuses).select_related('equipment', 'user')[:20]
        maintenance_equipment = Equipment.objects.exclude(status=EquipmentStatus.AVAILABLE)
        context.update(
            {
                'pending_reservations': pending,
                'problem_reservations': problem_reservations,
                'maintenance_equipment': maintenance_equipment,
            }
        )
        return context


class ReservationApproveView(StaffReservationAccessMixin, FormView):
    form_class = ReservationDecisionForm
    template_name = 'reservations/reservation_decision.html'

    def dispatch(self, request, *args, **kwargs):
        self.reservation = get_object_or_404(Reservation, pk=self.kwargs['pk'], status=ReservationStatus.PENDING)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            approve_reservation(
                reservation=self.reservation,
                reviewer=self.request.user,
                staff_comment=form.cleaned_data['staff_comment'],
            )
        except ValidationError as exc:
            for error_list in exc.message_dict.values():
                for error in error_list:
                    form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, 'Заявка подтверждена.')
        return redirect('reservations:staff-dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reservation'] = self.reservation
        context['decision_mode'] = 'approve'
        return context


class ReservationRejectView(StaffReservationAccessMixin, FormView):
    form_class = ReservationDecisionForm
    template_name = 'reservations/reservation_decision.html'

    def dispatch(self, request, *args, **kwargs):
        self.reservation = get_object_or_404(Reservation, pk=self.kwargs['pk'], status=ReservationStatus.PENDING)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        rejection_reason = form.cleaned_data['rejection_reason'].strip()
        if not rejection_reason:
            form.add_error('rejection_reason', 'Причина отказа обязательна.')
            return self.form_invalid(form)

        try:
            reject_reservation(
                reservation=self.reservation,
                reviewer=self.request.user,
                rejection_reason=rejection_reason,
                staff_comment=form.cleaned_data['staff_comment'],
            )
        except ValidationError as exc:
            for error_list in exc.message_dict.values():
                for error in error_list:
                    form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, 'Заявка отклонена.')
        return redirect('reservations:staff-dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reservation'] = self.reservation
        context['decision_mode'] = 'reject'
        return context
