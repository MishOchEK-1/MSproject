from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    USER_CREATED = 'user_created', 'Пользователь создан'
    USER_ROLE_CHANGED = 'user_role_changed', 'Роль пользователя изменена'
    TRAINING_STATUS_CHANGED = 'training_status_changed', 'Статус инструктажа изменен'
    EQUIPMENT_CREATED = 'equipment_created', 'Оборудование создано'
    EQUIPMENT_STATUS_CHANGED = 'equipment_status_changed', 'Статус оборудования изменен'
    RESERVATION_CREATED = 'reservation_created', 'Бронирование создано'
    RESERVATION_APPROVED = 'reservation_approved', 'Бронирование подтверждено'
    RESERVATION_REJECTED = 'reservation_rejected', 'Бронирование отклонено'
    RESERVATION_CANCELLED = 'reservation_cancelled', 'Бронирование отменено'
    NOTIFICATION_CREATED = 'notification_created', 'Уведомление создано'


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='Инициатор',
    )
    action = models.CharField(
        'Действие',
        max_length=50,
        choices=AuditAction.choices,
    )
    entity_type = models.CharField('Тип сущности', max_length=50)
    entity_id = models.PositiveBigIntegerField('ID сущности')
    entity_label = models.CharField('Название сущности', max_length=255, blank=True)
    description = models.TextField('Описание')
    payload = models.JSONField('Дополнительные данные', default=dict, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Журнал аудита'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f'{self.get_action_display()} - {self.entity_type}#{self.entity_id}'
