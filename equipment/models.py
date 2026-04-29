from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EquipmentCategory(models.Model):
    name = models.CharField('Название категории', max_length=100, unique=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Категория оборудования'
        verbose_name_plural = 'Категории оборудования'
        ordering = ['name']

    def __str__(self):
        return self.name


class EquipmentStatus(models.TextChoices):
    AVAILABLE = 'available', 'Доступно'
    MAINTENANCE = 'maintenance', 'На обслуживании'
    OUT_OF_ORDER = 'out_of_order', 'Неисправно'
    INACTIVE = 'inactive', 'Неактивно'


class Equipment(models.Model):
    name = models.CharField('Название', max_length=150)
    category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.PROTECT,
        related_name='equipment_items',
        verbose_name='Категория',
    )
    inventory_number = models.CharField(
        'Инвентарный номер',
        max_length=100,
        unique=True,
    )
    description = models.TextField('Описание', blank=True)
    photo = models.FileField('Фото', upload_to='equipment/', blank=True)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=EquipmentStatus.choices,
        default=EquipmentStatus.AVAILABLE,
    )
    slot_duration_minutes = models.PositiveSmallIntegerField(
        'Длительность слота, мин',
        default=60,
        validators=[MinValueValidator(20), MaxValueValidator(1440)],
    )
    requires_training = models.BooleanField(
        'Требуется инструктаж',
        default=True,
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Оборудование'
        verbose_name_plural = 'Оборудование'
        ordering = ['category__name', 'name']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f'{self.name} ({self.inventory_number})'

    @property
    def is_bookable(self):
        return self.status == EquipmentStatus.AVAILABLE


class EquipmentDowntime(models.Model):
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name='downtimes',
        verbose_name='Оборудование',
    )
    start_at = models.DateTimeField('Начало недоступности')
    end_at = models.DateTimeField('Окончание недоступности')
    reason = models.TextField('Причина')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_downtimes',
        verbose_name='Кем создано',
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        verbose_name = 'Период недоступности оборудования'
        verbose_name_plural = 'Периоды недоступности оборудования'
        ordering = ['-start_at']
        indexes = [
            models.Index(fields=['equipment', 'start_at', 'end_at']),
        ]

    def __str__(self):
        return f'{self.equipment.name}: {self.start_at:%d.%m.%Y %H:%M} - {self.end_at:%d.%m.%Y %H:%M}'

    def clean(self):
        if self.start_at >= self.end_at:
            raise ValidationError('Период недоступности должен заканчиваться позже начала.')
