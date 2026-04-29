from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    RESERVATION_CREATED = 'reservation_created', 'Новая заявка'
    RESERVATION_APPROVED = 'reservation_approved', 'Заявка подтверждена'
    RESERVATION_REJECTED = 'reservation_rejected', 'Заявка отклонена'
    RESERVATION_CANCELLED = 'reservation_cancelled', 'Бронь отменена'
    RESERVATION_COMPLETED = 'reservation_completed', 'Бронь завершена'


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        verbose_name='Инициатор',
    )
    notification_type = models.CharField(
        'Тип уведомления',
        max_length=40,
        choices=NotificationType.choices,
    )
    title = models.CharField('Заголовок', max_length=255)
    message = models.TextField('Сообщение')
    reservation = models.ForeignKey(
        'reservations.Reservation',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
        verbose_name='Бронирование',
    )
    is_read = models.BooleanField('Прочитано', default=False)
    read_at = models.DateTimeField('Прочитано в', null=True, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type', 'created_at']),
        ]

    def __str__(self):
        return self.title

    def mark_as_read(self, *, save=True):
        self.is_read = True
        self.read_at = self.read_at or timezone.now()
        if save:
            self.save(update_fields=['is_read', 'read_at'])
