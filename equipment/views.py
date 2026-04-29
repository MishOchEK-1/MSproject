from datetime import datetime, time, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from reservations.models import Reservation, ReservationStatus
from reservations.services import sync_reservation_lifecycle

from .models import Equipment, EquipmentCategory, EquipmentDowntime, EquipmentStatus

BOOKING_STEP_MINUTES = 20
SCHEDULE_WINDOW_DAYS = 22


def align_to_booking_step(moment):
    aligned = moment.replace(second=0, microsecond=0)
    remainder = aligned.minute % BOOKING_STEP_MINUTES
    if remainder:
        aligned += timedelta(minutes=BOOKING_STEP_MINUTES - remainder)
    return aligned


def format_reservation_window(reservation):
    local_start = timezone.localtime(reservation.start_at)
    local_end = timezone.localtime(reservation.end_at)
    return f'{local_start:%H:%M}-{local_end:%H:%M}'


def format_reservation_summary(reservation, viewer, *, include_status=True, include_window=True):
    parts = []
    if include_status:
        parts.append(reservation.get_status_display())
    if include_window:
        parts.append(format_reservation_window(reservation))
    parts.append(reservation.owner_label_for(viewer))
    return ' · '.join(parts)


def get_schedule_window_dates():
    today = timezone.localdate()
    return today, today + timedelta(weeks=3)


def get_schedule_window_bounds():
    today, max_day = get_schedule_window_dates()
    window_start = timezone.make_aware(datetime.combine(today, time.min))
    window_end = timezone.make_aware(datetime.combine(max_day + timedelta(days=1), time.min))
    return today, max_day, window_start, window_end


def clamp_schedule_day(raw_date, fallback_day):
    today, max_day = get_schedule_window_dates()
    if not raw_date:
        return fallback_day
    try:
        selected = datetime.strptime(raw_date, '%Y-%m-%d').date()
    except ValueError:
        return fallback_day
    return min(max(selected, today), max_day)


def get_schedule_day_choices():
    today, _ = get_schedule_window_dates()
    return [today + timedelta(days=offset) for offset in range(SCHEDULE_WINDOW_DAYS)]


def get_first_activity_day(*, reservation_qs, downtime_qs):
    today, _, window_start, window_end = get_schedule_window_bounds()
    candidates = []

    reservation = (
        reservation_qs.filter(
            status__in=Reservation.ACTIVE_STATUSES,
            start_at__lt=window_end,
            end_at__gt=window_start,
        )
        .order_by('start_at')
        .first()
    )
    if reservation:
        candidates.append(timezone.localtime(max(reservation.start_at, window_start)).date())

    downtime = (
        downtime_qs.filter(
            start_at__lt=window_end,
            end_at__gt=window_start,
        )
        .order_by('start_at')
        .first()
    )
    if downtime:
        candidates.append(timezone.localtime(max(downtime.start_at, window_start)).date())

    return min(candidates) if candidates else today


class EquipmentListView(LoginRequiredMixin, ListView):
    model = Equipment
    template_name = 'equipment/equipment_list.html'
    context_object_name = 'equipment_items'
    paginate_by = 20

    def get_queryset(self):
        sync_reservation_lifecycle()
        queryset = Equipment.objects.select_related('category').all()
        query = self.request.GET.get('q', '').strip()
        category = self.request.GET.get('category', '').strip()
        status = self.request.GET.get('status', '').strip()

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(inventory_number__icontains=query)
                | Q(description__icontains=query)
                | Q(category__name__icontains=query)
            )
        if category:
            queryset = queryset.filter(category_id=category)
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = EquipmentCategory.objects.all()
        context['status_choices'] = EquipmentStatus.choices
        return context


class EquipmentDetailView(LoginRequiredMixin, DetailView):
    model = Equipment
    template_name = 'equipment/equipment_detail.html'
    context_object_name = 'equipment'

    def get_object(self, queryset=None):
        sync_reservation_lifecycle()
        return super().get_object(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        equipment = self.object
        selected_day = self._get_selected_day(equipment)
        day_start = timezone.make_aware(datetime.combine(selected_day, time(hour=0, minute=0)))
        day_end = day_start + timedelta(days=1)
        reservations = list(
            equipment.reservations.filter(
                status__in=Reservation.ACTIVE_STATUSES,
                start_at__lt=day_end,
                end_at__gt=day_start,
            ).select_related('user').order_by('start_at')
        )
        downtimes = list(
            equipment.downtimes.filter(
                start_at__lt=day_end,
                end_at__gt=day_start,
            ).order_by('start_at')
        )
        slots = []
        for hour in range(24):
            slot_start = day_start + timedelta(hours=hour)
            slot_end = slot_start + timedelta(hours=1)
            slot_reservations = [
                item for item in reservations if item.start_at < slot_end and item.end_at > slot_start
            ]
            slot_downtime = next(
                (item for item in downtimes if item.start_at < slot_end and item.end_at > slot_start),
                None,
            )
            slots.append(self._build_schedule_slot(slot_start, slot_reservations, slot_downtime))

        window_start = timezone.now()
        window_end = window_start + timedelta(weeks=3)
        future_reservations = equipment.reservations.filter(
            status__in=Reservation.ACTIVE_STATUSES,
            end_at__gte=window_start,
            start_at__lte=window_end,
        ).order_by('start_at')
        future_reservation_items = [
            {
                'reservation': item,
                'owner_label': item.owner_label_for(self.request.user),
            }
            for item in future_reservations[:10]
        ]
        nearest_free_slot = self._find_nearest_free_slot(equipment, window_start)

        context.update(
            {
                'selected_day': selected_day,
                'schedule_slots': slots,
                'future_reservations': future_reservation_items,
                'nearest_free_slot': nearest_free_slot,
                'day_choices': self._build_day_choices(),
            }
        )
        return context

    def _get_selected_day(self, equipment):
        fallback_day = get_first_activity_day(
            reservation_qs=equipment.reservations.all(),
            downtime_qs=equipment.downtimes.all(),
        )
        return clamp_schedule_day(self.request.GET.get('date'), fallback_day)

    def _build_day_choices(self):
        return get_schedule_day_choices()

    def _build_schedule_slot(self, slot_start, slot_reservations, slot_downtime):
        if slot_downtime:
            return {
                'hour_label': slot_start.strftime('%H:%M'),
                'status': 'blocked',
                'headline': 'Недоступно',
                'detail_lines': [slot_downtime.reason],
            }

        if not slot_reservations:
            return {
                'hour_label': slot_start.strftime('%H:%M'),
                'status': 'free',
                'headline': 'Свободно',
                'detail_lines': [],
            }

        detail_lines = [
            format_reservation_summary(item, self.request.user, include_window=len(slot_reservations) > 1)
            for item in slot_reservations
        ]
        approved_exists = any(item.status == ReservationStatus.APPROVED for item in slot_reservations)
        headline = (
            format_reservation_window(slot_reservations[0])
            if len(slot_reservations) == 1
            else f'Броней в часе: {len(slot_reservations)}'
        )
        return {
            'hour_label': slot_start.strftime('%H:%M'),
            'status': ReservationStatus.APPROVED if approved_exists else ReservationStatus.PENDING,
            'headline': headline,
            'detail_lines': detail_lines,
        }

    def _find_nearest_free_slot(self, equipment, start_from):
        pointer = align_to_booking_step(start_from)
        horizon = start_from + timedelta(weeks=3)
        duration = timedelta(minutes=equipment.slot_duration_minutes)
        while pointer < horizon:
            candidate_end = pointer + duration
            has_conflict = equipment.reservations.filter(
                status__in=Reservation.ACTIVE_STATUSES,
                start_at__lt=candidate_end,
                end_at__gt=pointer,
            ).exists()
            blocked = equipment.downtimes.filter(
                start_at__lt=candidate_end,
                end_at__gt=pointer,
            ).exists()
            if not has_conflict and not blocked and equipment.is_bookable:
                return pointer
            pointer += timedelta(minutes=BOOKING_STEP_MINUTES)
        return None


class EquipmentScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'equipment/equipment_schedule.html'

    def get_context_data(self, **kwargs):
        sync_reservation_lifecycle()
        context = super().get_context_data(**kwargs)
        queryset = Equipment.objects.select_related('category').all()
        query = self.request.GET.get('q', '').strip()
        category = self.request.GET.get('category', '').strip()
        status = self.request.GET.get('status', '').strip()

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(inventory_number__icontains=query)
                | Q(category__name__icontains=query)
            )
        if category:
            queryset = queryset.filter(category_id=category)
        if status:
            queryset = queryset.filter(status=status)
        selected_day = self._get_selected_day(queryset)

        day_start = timezone.make_aware(datetime.combine(selected_day, time(hour=0, minute=0)))
        day_end = day_start + timedelta(days=1)
        hour_labels = [(day_start + timedelta(hours=hour)).strftime('%H:%M') for hour in range(24)]
        schedule_rows = []

        for equipment in queryset:
            reservations = list(
                equipment.reservations.filter(
                    status__in=Reservation.ACTIVE_STATUSES,
                    start_at__lt=day_end,
                    end_at__gt=day_start,
                ).select_related('user').order_by('start_at')
            )
            downtimes = list(equipment.downtimes.filter(start_at__lt=day_end, end_at__gt=day_start))
            row_slots = []
            busy_hours = 0
            for hour in range(24):
                slot_start = day_start + timedelta(hours=hour)
                slot_end = slot_start + timedelta(hours=1)
                slot_reservations = [
                    item for item in reservations if item.start_at < slot_end and item.end_at > slot_start
                ]
                downtime = next(
                    (item for item in downtimes if item.start_at < slot_end and item.end_at > slot_start),
                    None,
                )
                if downtime:
                    slot_type = 'blocked'
                    label = 'Недоступно'
                    detail = downtime.reason
                elif slot_reservations:
                    approved_exists = any(item.status == ReservationStatus.APPROVED for item in slot_reservations)
                    slot_type = ReservationStatus.APPROVED if approved_exists else ReservationStatus.PENDING
                    label = (
                        format_reservation_window(slot_reservations[0])
                        if len(slot_reservations) == 1
                        else f'{len(slot_reservations)} брони'
                    )
                    detail = '; '.join(
                        format_reservation_summary(item, self.request.user, include_window=len(slot_reservations) > 1)
                        for item in slot_reservations
                    )
                    busy_hours += 1
                else:
                    slot_type = 'free'
                    label = 'Свободно'
                    detail = ''
                row_slots.append(
                    {
                        'type': slot_type,
                        'label': label,
                        'detail': detail,
                    }
                )
            schedule_rows.append(
                {
                    'equipment': equipment,
                    'slots': row_slots,
                    'busy_hours': busy_hours,
                }
            )

        context.update(
            {
                'categories': EquipmentCategory.objects.all(),
                'status_choices': EquipmentStatus.choices,
                'selected_day': selected_day,
                'day_choices': get_schedule_day_choices(),
                'hour_labels': hour_labels,
                'schedule_rows': schedule_rows,
            }
        )
        return context

    def _get_selected_day(self, equipment_queryset):
        fallback_day = get_first_activity_day(
            reservation_qs=Reservation.objects.filter(equipment__in=equipment_queryset),
            downtime_qs=EquipmentDowntime.objects.filter(equipment__in=equipment_queryset),
        )
        return clamp_schedule_day(self.request.GET.get('date'), fallback_day)
