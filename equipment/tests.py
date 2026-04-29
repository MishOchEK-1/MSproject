from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User, UserRole
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


class EquipmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='equipment-user',
            password='secure-pass-123',
            email='equipment@example.com',
            full_name='Equipment User',
            phone='+70000000030',
            role=UserRole.GUEST,
        )
        self.category = EquipmentCategory.objects.create(name='Паяльные станции')
        self.equipment = Equipment.objects.create(
            name='Hakko 1',
            category=self.category,
            inventory_number='SOL-001',
            description='Паяльная станция с тонким жалом.',
        )

    def test_equipment_list_requires_login(self):
        response = self.client.get(reverse('equipment:list'))

        self.assertEqual(response.status_code, 302)

    def test_equipment_list_is_available_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hakko 1')

    def test_equipment_detail_shows_nearest_free_slot(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:detail', args=[self.equipment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ближайшее свободное время')
