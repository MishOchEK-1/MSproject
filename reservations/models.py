from datetime import timedelta

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

    def clean(self):
        errors = {}
        now = timezone.now()

        if self.start_at and self.end_at and self.start_at >= self.end_at:
            errors['end_at'] = 'Окончание брони должно быть позже начала.'

        if self.start_at and self.end_at:
            duration = self.end_at - self.start_at
            if duration < timedelta(minutes=20):
                errors['end_at'] = 'Минимальная длительность брони - 20 минут.'
            if duration > timedelta(hours=24):
                errors['end_at'] = 'Максимальная длительность брони - 24 часа.'

        if self.start_at and self.start_at > now + timedelta(weeks=3):
            errors['start_at'] = 'Бронь нельзя создать более чем на 3 недели вперед.'

        if self.status == ReservationStatus.REJECTED and not self.rejection_reason.strip():
            errors['rejection_reason'] = 'Для отклоненной заявки нужно указать причину отказа.'

        if self.equipment_id and self.start_at and self.end_at:
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
