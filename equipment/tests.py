from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from .models import Equipment, EquipmentCategory, EquipmentDowntime


class EquipmentModelTests(TestCase):
    def test_slot_duration_must_be_at_least_twenty_minutes(self):
        category = EquipmentCategory.objects.create(name='3D принтеры')
        equipment = Equipment(
            name='Prusa MK4',
            category=category,
            inventory_number='3DP-001',
            slot_duration_minutes=10,
        )

        with self.assertRaisesMessage(Exception, 'Убедитесь, что это значение больше либо равно 20.'):
            equipment.full_clean()

    def test_downtime_requires_end_after_start(self):
        category = EquipmentCategory.objects.create(name='Лазерные станки')
        equipment = Equipment.objects.create(
            name='Laser 1',
            category=category,
            inventory_number='LS-001',
        )
        downtime = EquipmentDowntime(
            equipment=equipment,
            start_at=timezone.now(),
            end_at=timezone.now() - timedelta(hours=1),
            reason='Плановое обслуживание',
        )

        with self.assertRaisesMessage(Exception, 'Период недоступности должен заканчиваться позже начала.'):
            downtime.full_clean()
