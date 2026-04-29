from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory
from reservations.models import Reservation
from users.models import User

from .models import Notification, NotificationType


class NotificationModelTests(TestCase):
    def test_mark_as_read_sets_timestamp(self):
        user = User.objects.create_user(
            username='notify-user',
            password='secure-pass-123',
            email='notify@example.com',
            full_name='Notify User',
            phone='+70000000003',
        )
        category = EquipmentCategory.objects.create(name='Верстаки')
        equipment = Equipment.objects.create(
            name='Workbench 1',
            category=category,
            inventory_number='WB-001',
        )
        reservation = Reservation.objects.create(
            user=user,
            equipment=equipment,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
        )
        notification = Notification.objects.create(
            recipient=user,
            notification_type=NotificationType.RESERVATION_CREATED,
            title='Новая заявка',
            message='Заявка отправлена на подтверждение.',
            reservation=reservation,
        )

        notification.mark_as_read()

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)


class NotificationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notify-list-user',
            password='secure-pass-123',
            email='notify-list@example.com',
            full_name='Notify List User',
            phone='+70000000050',
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            notification_type=NotificationType.RESERVATION_CREATED,
            title='Есть новое уведомление',
            message='Тестовое уведомление',
        )

    def test_notification_center_requires_login(self):
        response = self.client.get(reverse('notifications:list'))

        self.assertEqual(response.status_code, 302)

    def test_user_can_open_notification_center(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('notifications:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Есть новое уведомление')

    def test_user_can_mark_notification_as_read(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('notifications:read', args=[self.notification.pk]))

        self.assertRedirects(response, reverse('notifications:list'))
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
