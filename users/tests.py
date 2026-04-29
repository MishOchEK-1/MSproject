from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from equipment.models import Equipment, EquipmentCategory
from reservations.models import Reservation, ReservationStatus

from .models import User, UserRole
from .permissions import (
    can_cancel_reservation,
    can_manage_training_status,
    can_manage_user_role,
    can_review_reservation,
    can_view_reservation_owner,
    can_view_schedule,
    reservation_requires_manual_approval,
)


class UserModelTests(TestCase):
    def test_user_role_defaults_to_guest(self):
        user = User.objects.create_user(
            username='guest-user',
            password='secure-pass-123',
            email='guest@example.com',
            full_name='Guest User',
            phone='+70000000000',
        )

        self.assertEqual(user.role, UserRole.GUEST)
        self.assertFalse(user.has_completed_training)

    def test_staff_role_syncs_django_staff_flags(self):
        user = User.objects.create_user(
            username='staff-user',
            password='secure-pass-123',
            email='staff@edu.omsk.ru',
            full_name='Staff User',
            phone='+70000000010',
            role=UserRole.STAFF,
        )

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.can_book_without_approval)

    def test_admin_role_syncs_superuser_flags(self):
        user = User.objects.create_user(
            username='admin-user',
            password='secure-pass-123',
            email='admin@edu.omsk.ru',
            full_name='Admin User',
            phone='+70000000011',
            role=UserRole.ADMIN,
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.can_manage_users)

    def test_student_requires_corporate_email(self):
        user = User(
            username='student-user',
            email='student@gmail.com',
            full_name='Student User',
            phone='+70000000012',
            role=UserRole.STUDENT,
        )

        with self.assertRaisesMessage(Exception, 'Для персонала и студентов нужна корпоративная почта вуза.'):
            user.full_clean()

    def test_guest_without_training_cannot_book_equipment_that_requires_it(self):
        user = User.objects.create_user(
            username='guest-no-training',
            password='secure-pass-123',
            email='guest2@example.com',
            full_name='Guest Without Training',
            phone='+70000000013',
        )
        category = EquipmentCategory.objects.create(name='3D-принтеры')
        equipment = Equipment.objects.create(
            name='Prusa XL',
            category=category,
            inventory_number='3DP-XL-01',
            requires_training=True,
        )

        self.assertFalse(user.can_book_equipment(equipment))


class PermissionRulesTests(TestCase):
    def setUp(self):
        self.category = EquipmentCategory.objects.create(name='Рабочие столы')
        self.equipment = Equipment.objects.create(
            name='Table 1',
            category=self.category,
            inventory_number='TB-001',
            requires_training=True,
        )
        self.guest = User.objects.create_user(
            username='guest-user-2',
            password='secure-pass-123',
            email='guest3@example.com',
            full_name='Guest User Two',
            phone='+70000000014',
            role=UserRole.GUEST,
        )
        self.student = User.objects.create_user(
            username='student-user-2',
            password='secure-pass-123',
            email='student2@edu.omsk.ru',
            full_name='Student User Two',
            phone='+70000000015',
            role=UserRole.STUDENT,
            has_completed_training=True,
        )
        self.staff = User.objects.create_user(
            username='staff-user-2',
            password='secure-pass-123',
            email='staff2@edu.omsk.ru',
            full_name='Staff User Two',
            phone='+70000000016',
            role=UserRole.STAFF,
        )
        self.admin = User.objects.create_user(
            username='admin-user-2',
            password='secure-pass-123',
            email='admin2@edu.omsk.ru',
            full_name='Admin User Two',
            phone='+70000000017',
            role=UserRole.ADMIN,
        )
        start_at = timezone.now() + timedelta(days=5)
        self.reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.PENDING,
        )

    def test_schedule_is_visible_only_for_authenticated_users(self):
        anonymous = AnonymousUser()

        self.assertFalse(can_view_schedule(anonymous))
        self.assertTrue(can_view_schedule(self.guest))

    def test_only_staff_or_owner_can_view_reservation_owner(self):
        self.assertTrue(can_view_reservation_owner(self.student, self.reservation))
        self.assertTrue(can_view_reservation_owner(self.staff, self.reservation))
        self.assertFalse(can_view_reservation_owner(self.guest, self.reservation))

    def test_staff_and_admin_can_review_reservations(self):
        self.assertFalse(can_review_reservation(self.guest, self.reservation))
        self.assertTrue(can_review_reservation(self.staff, self.reservation))
        self.assertTrue(can_review_reservation(self.admin, self.reservation))

    def test_only_admin_can_manage_user_roles(self):
        self.assertFalse(can_manage_user_role(self.staff, self.student))
        self.assertTrue(can_manage_user_role(self.admin, self.student))

    def test_staff_and_admin_can_manage_training_status(self):
        self.assertFalse(can_manage_training_status(self.student, self.guest))
        self.assertTrue(can_manage_training_status(self.staff, self.guest))
        self.assertTrue(can_manage_training_status(self.admin, self.guest))

    def test_manual_approval_rule_depends_on_role(self):
        self.assertTrue(reservation_requires_manual_approval(self.guest))
        self.assertTrue(reservation_requires_manual_approval(self.student))
        self.assertFalse(reservation_requires_manual_approval(self.staff))

    def test_owner_or_staff_can_cancel_reservation(self):
        self.assertTrue(can_cancel_reservation(self.student, self.reservation))
        self.assertTrue(can_cancel_reservation(self.staff, self.reservation))
        self.assertFalse(can_cancel_reservation(self.guest, self.reservation))


class AuthenticationFlowTests(TestCase):
    def test_registration_creates_guest_and_logs_user_in(self):
        response = self.client.post(
            reverse('users:register'),
            {
                'full_name': 'New Guest',
                'email': 'newguest@example.com',
                'phone': '+70000000018',
                'organization': 'Outside Org',
                'visit_purpose': 'Хочу воспользоваться оборудованием',
                'password1': 'VerySecurePassword123',
                'password2': 'VerySecurePassword123',
            },
        )

        self.assertRedirects(response, reverse('users:profile'))
        user = User.objects.get(email='newguest@example.com')
        self.assertEqual(user.role, UserRole.GUEST)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_login_accepts_email_and_password(self):
        user = User.objects.create_user(
            username='login-user',
            password='secure-pass-456',
            email='login@example.com',
            full_name='Login User',
            phone='+70000000019',
        )

        response = self.client.post(
            reverse('users:login'),
            {
                'email': user.email,
                'password': 'secure-pass-456',
            },
        )

        self.assertRedirects(response, reverse('users:profile'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('users:profile'))

        self.assertRedirects(
            response,
            f"{reverse('users:login')}?next={reverse('users:profile')}",
        )

    def test_profile_update_changes_allowed_fields_only(self):
        user = User.objects.create_user(
            username='edit-user',
            password='secure-pass-789',
            email='edit@example.com',
            full_name='Edit User',
            phone='+70000000020',
            role=UserRole.GUEST,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('users:profile-edit'),
            {
                'full_name': 'Updated User',
                'email': 'edit@example.com',
                'phone': '+70000000021',
                'organization': 'Updated Org',
                'visit_purpose': 'Updated reason',
                'role': UserRole.ADMIN,
            },
        )

        self.assertRedirects(response, reverse('users:profile'))
        user.refresh_from_db()
        self.assertEqual(user.full_name, 'Updated User')
        self.assertEqual(user.phone, '+70000000021')
        self.assertEqual(user.role, UserRole.GUEST)


class TrainingManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='training-staff',
            password='secure-pass-123',
            email='training-staff@edu.omsk.ru',
            full_name='Training Staff',
            phone='+70000000060',
            role=UserRole.STAFF,
        )
        self.guest = User.objects.create_user(
            username='training-guest',
            password='secure-pass-123',
            email='training-guest@example.com',
            full_name='Training Guest',
            phone='+70000000061',
            role=UserRole.GUEST,
            has_completed_training=False,
        )

    def test_staff_can_open_training_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('users:training-dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Training Guest')

    def test_staff_can_update_training_status(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('users:training-update', args=[self.guest.pk]),
            {'has_completed_training': 'on'},
        )

        self.assertRedirects(response, reverse('users:training-dashboard'))
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.has_completed_training)

    def test_guest_cannot_access_training_dashboard(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse('users:training-dashboard'))

        self.assertEqual(response.status_code, 403)
