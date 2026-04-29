from datetime import datetime, time, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from reservations.services import sync_reservation_lifecycle

from .models import Equipment, EquipmentCategory, EquipmentStatus


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
        selected_day = self._get_selected_day()
        day_start = timezone.make_aware(datetime.combine(selected_day, time(hour=0, minute=0)))
        day_end = day_start + timedelta(days=1)
        reservations = equipment.reservations.filter(
            start_at__lt=day_end,
            end_at__gt=day_start,
        ).select_related('user')
        slots = []
        for hour in range(24):
            slot_start = day_start + timedelta(hours=hour)
            slot_end = slot_start + timedelta(hours=1)
            overlapping = reservations.filter(start_at__lt=slot_end, end_at__gt=slot_start).order_by('start_at').first()
            slots.append(
                {
                    'hour_label': slot_start.strftime('%H:%M'),
                    'reservation': overlapping,
                    'status': overlapping.status if overlapping else 'free',
                    'owner_label': overlapping.owner_label_for(self.request.user) if overlapping else '',
                }
            )

        window_start = timezone.now()
        window_end = window_start + timedelta(weeks=3)
        future_reservations = equipment.reservations.filter(
            start_at__gte=window_start,
            start_at__lte=window_end,
        ).order_by('start_at')
        nearest_free_slot = self._find_nearest_free_slot(equipment, window_start)

        context.update(
            {
                'selected_day': selected_day,
                'schedule_slots': slots,
                'future_reservations': future_reservations[:10],
                'nearest_free_slot': nearest_free_slot,
                'day_choices': self._build_day_choices(selected_day),
            }
        )
        return context

    def _get_selected_day(self):
        raw_date = self.request.GET.get('date')
        today = timezone.localdate()
        if not raw_date:
            return today
        try:
            selected = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return today
        max_day = today + timedelta(weeks=3)
        if selected < today:
            return today
        if selected > max_day:
            return max_day
        return selected

    def _build_day_choices(self, selected_day):
        today = timezone.localdate()
        return [today + timedelta(days=offset) for offset in range(0, 21)]

    def _find_nearest_free_slot(self, equipment, start_from):
        pointer = start_from.replace(minute=0, second=0, microsecond=0)
        horizon = start_from + timedelta(weeks=3)
        duration = timedelta(minutes=equipment.slot_duration_minutes)
        while pointer < horizon:
            candidate_end = pointer + duration
            has_conflict = equipment.reservations.filter(
                status__in=('pending', 'approved'),
                start_at__lt=candidate_end,
                end_at__gt=pointer,
            ).exists()
            blocked = equipment.downtimes.filter(
                start_at__lt=candidate_end,
                end_at__gt=pointer,
            ).exists()
            if not has_conflict and not blocked and equipment.is_bookable:
                return pointer
            pointer += timedelta(hours=1)
        return None


class EquipmentScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'equipment/equipment_schedule.html'

    def get_context_data(self, **kwargs):
        sync_reservation_lifecycle()
        context = super().get_context_data(**kwargs)
        selected_day = self._get_selected_day()
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

        day_start = timezone.make_aware(datetime.combine(selected_day, time(hour=0, minute=0)))
        day_end = day_start + timedelta(days=1)
        hour_labels = [(day_start + timedelta(hours=hour)).strftime('%H:%M') for hour in range(24)]
        schedule_rows = []

        for equipment in queryset:
            reservations = list(
                equipment.reservations.filter(
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
                reservation = next(
                    (item for item in reservations if item.start_at < slot_end and item.end_at > slot_start),
                    None,
                )
                downtime = next(
                    (item for item in downtimes if item.start_at < slot_end and item.end_at > slot_start),
                    None,
                )
                if downtime:
                    slot_type = 'blocked'
                    label = 'Недоступно'
                    detail = downtime.reason
                elif reservation:
                    slot_type = reservation.status
                    label = reservation.get_status_display()
                    detail = reservation.owner_label_for(self.request.user)
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
                'day_choices': [timezone.localdate() + timedelta(days=offset) for offset in range(21)],
                'hour_labels': hour_labels,
                'schedule_rows': schedule_rows,
            }
        )
        return context

    def _get_selected_day(self):
        raw_date = self.request.GET.get('date')
        today = timezone.localdate()
        if not raw_date:
            return today
        try:
            selected = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return today
        max_day = today + timedelta(weeks=3)
        return min(max(selected, today), max_day)
