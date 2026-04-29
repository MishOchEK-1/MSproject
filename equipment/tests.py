from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservations.models import Reservation, ReservationStatus
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

    def test_equipment_list_renders_external_photo_when_available(self):
        self.equipment.photo_url = 'https://example.com/hakko.jpg'
        self.equipment.save(update_fields=['photo_url'])

        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://example.com/hakko.jpg')

    def test_equipment_detail_shows_nearest_free_slot(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:detail', args=[self.equipment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ближайшее свободное время')

    def test_equipment_detail_shows_confirmed_reservation_in_selected_day_schedule(self):
        self.client.force_login(self.user)
        selected_day = timezone.localdate() + timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(selected_day, time(hour=14, minute=20)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )

        response = self.client.get(
            reverse('equipment:detail', args=[self.equipment.pk]),
            {'date': selected_day.strftime('%Y-%m-%d')},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '14:20-15:20')
        self.assertContains(response, f'{ReservationStatus.APPROVED.label} · {self.user.full_name}')

    def test_equipment_detail_defaults_to_nearest_day_with_reservation(self):
        self.client.force_login(self.user)
        selected_day = timezone.localdate() + timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(selected_day, time(hour=14, minute=20)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )

        response = self.client.get(reverse('equipment:detail', args=[self.equipment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, selected_day.strftime('%Y-%m-%d'))
        self.assertContains(response, '14:20-15:20')

    def test_equipment_schedule_page_is_available(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Загрузка оборудования')

    def test_equipment_schedule_shows_confirmed_reservation_window(self):
        self.client.force_login(self.user)
        selected_day = timezone.localdate() + timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(selected_day, time(hour=14, minute=20)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )

        response = self.client.get(
            reverse('equipment:schedule'),
            {'date': selected_day.strftime('%Y-%m-%d')},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '14:20-15:20')
        self.assertContains(response, f'{ReservationStatus.APPROVED.label} · {self.user.full_name}')

    def test_equipment_schedule_defaults_to_nearest_day_with_reservation(self):
        self.client.force_login(self.user)
        selected_day = timezone.localdate() + timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(selected_day, time(hour=14, minute=20)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )

        response = self.client.get(reverse('equipment:schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, selected_day.strftime('%Y-%m-%d'))
        self.assertContains(response, '14:20-15:20')

    def test_schedule_date_picker_includes_full_three_week_window(self):
        self.client.force_login(self.user)
        last_day = timezone.localdate() + timedelta(weeks=3)

        response = self.client.get(reverse('equipment:schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, last_day.strftime('%Y-%m-%d'))

    def test_equipment_list_renders_pagination_controls(self):
        for index in range(25):
            Equipment.objects.create(
                name=f'Hakko Extra {index}',
                category=self.category,
                inventory_number=f'SOL-{index + 10:03d}',
            )

        self.client.force_login(self.user)
        response = self.client.get(reverse('equipment:list'), {'q': 'Hakko'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Страница 1 из 2')

    def test_equipment_detail_ignores_cancelled_reservations_and_shows_downtime(self):
        self.client.force_login(self.user)
        selected_day = timezone.localdate() + timedelta(days=1)
        day_start = timezone.make_aware(datetime.combine(selected_day, time.min))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=day_start + timedelta(hours=9),
            end_at=day_start + timedelta(hours=10),
            status=ReservationStatus.CANCELLED,
            archived_at=timezone.now(),
        )
        EquipmentDowntime.objects.create(
            equipment=self.equipment,
            start_at=day_start + timedelta(hours=9),
            end_at=day_start + timedelta(hours=10),
            reason='Профилактика',
        )

        response = self.client.get(
            reverse('equipment:detail', args=[self.equipment.pk]),
            {'date': selected_day.strftime('%Y-%m-%d')},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Профилактика')
        self.assertNotContains(response, ReservationStatus.CANCELLED.label)

    def test_nearest_free_slot_uses_twenty_minute_step(self):
        self.client.force_login(self.user)
        self.equipment.slot_duration_minutes = 20
        self.equipment.save(update_fields=['slot_duration_minutes'])
        start_base = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        if start_base.minute % 20:
            start_base += timedelta(minutes=20 - start_base.minute % 20)
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_base,
            end_at=start_base + timedelta(minutes=20),
            status=ReservationStatus.APPROVED,
        )

        response = self.client.get(reverse('equipment:detail', args=[self.equipment.pk]))

        self.assertEqual(response.status_code, 200)
        expected_time = timezone.localtime(start_base + timedelta(minutes=20)).strftime('%d.%m.%Y %H:%M')
        self.assertContains(response, expected_time)
