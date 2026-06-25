from datetime import time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ReservationStatus(models.TextChoices):
    PENDING = 'pending', 'На подтверждении'
    APPROVED = 'approved', 'Подтверждена'
    REJECTED = 'rejected', 'Отклонена'
    CANCELLED = 'cancelled', 'Отменена'
    COMPLETED = 'completed', 'Завершена'
    EXPIRED = 'expired', 'Истекла'


class Reservation(models.Model):
    ACTIVE_STATUSES = (ReservationStatus.PENDING, ReservationStatus.APPROVED)
    MAX_DURATION_MINUTES = 24 * 60
    START_STEP_MINUTES = 20
    EARLIEST_START_TIME = time(hour=9, minute=0)
    LATEST_START_TIME = time(hour=19, minute=0)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name='Пользователь',
    )
    equipment = models.ForeignKey(
        'equipment.Equipment',
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name='Оборудование',
    )
    start_at = models.DateTimeField('Начало брони')
    end_at = models.DateTimeField('Окончание брони')
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,
    )
    request_comment = models.TextField(
        'Комментарий к заявке',
        blank=True,
    )
    staff_comment = models.TextField(
        'Комментарий персонала',
        blank=True,
    )
    rejection_reason = models.TextField(
        'Причина отказа',
        blank=True,
    )
    cancellation_reason = models.TextField(
        'Причина отмены',
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_reservations',
        verbose_name='Проверил',
    )
    reviewed_at = models.DateTimeField(
        'Проверено',
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField(
        'Истекает',
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        'Завершено',
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(
        'Архивировано',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        ordering = ['start_at', 'equipment__name']
        indexes = [
            models.Index(fields=['equipment', 'start_at', 'end_at']),
            models.Index(fields=['status', 'start_at']),
            models.Index(fields=['user', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F('start_at')),
                name='reservation_end_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.equipment.name}: {self.start_at:%d.%m.%Y %H:%M}'

    @property
    def duration(self):
        return self.end_at - self.start_at

    @property
    def duration_minutes(self):
        return int(self.duration.total_seconds() // 60)

    @property
    def requires_manual_approval(self):
        return not self.user.can_book_without_approval

    @classmethod
    def get_min_duration_minutes(cls, equipment):
        if equipment is None:
            return 20
        return equipment.slot_duration_minutes

    @classmethod
    def validate_duration_minutes(cls, duration_minutes, equipment=None):
        min_duration_minutes = cls.get_min_duration_minutes(equipment)

        if duration_minutes < min_duration_minutes:
            raise ValidationError(
                f'Минимальная длительность брони для этого оборудования - {min_duration_minutes} минут.'
            )

        if duration_minutes > cls.MAX_DURATION_MINUTES:
            raise ValidationError('Максимальная длительность брони - 24 часа.')

        if duration_minutes > min_duration_minutes and duration_minutes % 10 != 0:
            raise ValidationError('Если длительность больше базового слота, она должна быть кратна 10 минутам.')

    @classmethod
    def normalize_start_at(cls, start_at):
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
        return timezone.localtime(start_at)

    @classmethod
    def can_start_at(cls, start_at):
        local_start = cls.normalize_start_at(start_at)
        local_time = local_start.timetz().replace(tzinfo=None)
        return cls.EARLIEST_START_TIME <= local_time <= cls.LATEST_START_TIME

    @classmethod
    def is_start_step_aligned(cls, start_at):
        local_start = cls.normalize_start_at(start_at)
        return (
            local_start.minute % cls.START_STEP_MINUTES == 0
            and local_start.second == 0
            and local_start.microsecond == 0
        )

    @classmethod
    def validate_start_at(cls, start_at):
        if not cls.can_start_at(start_at):
            raise ValidationError('Начать бронь можно только с 09:00 до 19:00. Завершение может быть позже 19:00.')
        if not cls.is_start_step_aligned(start_at):
            raise ValidationError(
                f'Время старта должно быть с шагом {cls.START_STEP_MINUTES} минут: 09:00, 09:20, 09:40 и далее.'
            )

    def can_be_cancelled_by(self, user):
        if not user or not user.is_authenticated:
            return False
        if user.pk == self.user_id:
            return self.status in self.ACTIVE_STATUSES
        return user.can_force_cancel_reservations

    def owner_label_for(self, viewer):
        if viewer and getattr(viewer, 'is_authenticated', False) and viewer.can_view_reservation_owner(self):
            return self.user.full_name or self.user.username
        return 'Скрыто'

    def clean(self):
        errors = {}
        now = timezone.now()

        if self.start_at and self.end_at and self.start_at >= self.end_at:
            errors['end_at'] = 'Окончание брони должно быть позже начала.'

        if self.start_at and self.end_at:
            duration = self.end_at - self.start_at
            duration_minutes = int(duration.total_seconds() // 60)
            try:
                self.validate_duration_minutes(duration_minutes, self.equipment if self.equipment_id else None)
            except ValidationError as exc:
                errors['end_at'] = exc.messages[0]

        if self.start_at:
            try:
                self.validate_start_at(self.start_at)
            except ValidationError as exc:
                errors['start_at'] = exc.messages[0]

        if self.start_at and self.start_at > now + timedelta(weeks=3):
            errors['start_at'] = 'Бронь нельзя создать более чем на 3 недели вперед.'

        if self.status == ReservationStatus.REJECTED and not self.rejection_reason.strip():
            errors['rejection_reason'] = 'Для отклоненной заявки нужно указать причину отказа.'

        if self.equipment_id and self.start_at and self.end_at and self.status in self.ACTIVE_STATUSES:
            if not self.equipment.is_bookable:
                errors['equipment'] = 'Это оборудование сейчас недоступно для бронирования.'

            overlap_queryset = Reservation.objects.filter(
                equipment=self.equipment,
                status__in=self.ACTIVE_STATUSES,
            ).exclude(pk=self.pk)
            if overlap_queryset.filter(
                start_at__lt=self.end_at,
                end_at__gt=self.start_at,
            ).exists():
                errors['equipment'] = 'Это оборудование уже забронировано на выбранное время.'

            if self.equipment.downtimes.filter(
                start_at__lt=self.end_at,
                end_at__gt=self.start_at,
            ).exists():
                errors['equipment'] = 'Оборудование недоступно в выбранный период.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == ReservationStatus.PENDING and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)
