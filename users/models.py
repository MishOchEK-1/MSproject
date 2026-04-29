from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class UserRole(models.TextChoices):
    GUEST = 'guest', 'Гость'
    STUDENT = 'student', 'Студент'
    STAFF = 'staff', 'Персонал'
    ADMIN = 'admin', 'Администратор'


class User(AbstractUser):
    email = models.EmailField('Email', unique=True)
    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=32)
    role = models.CharField(
        'Роль',
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.GUEST,
    )
    organization = models.CharField(
        'Организация',
        max_length=255,
        blank=True,
    )
    visit_purpose = models.TextField(
        'Цель визита',
        blank=True,
    )
    has_completed_training = models.BooleanField(
        'Прошел инструктаж',
        default=False,
    )

    REQUIRED_FIELDS = ['email', 'full_name', 'phone']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.full_name or self.username

    def clean(self):
        super().clean()

        if self.role in {UserRole.STAFF, UserRole.ADMIN} and self.email:
            if not self.email.lower().endswith('@edu.omsk.ru'):
                raise ValidationError(
                    {'email': 'Для персонала и студентов нужна корпоративная почта вуза.'}
                )

        if self.role == UserRole.STUDENT and self.email:
            if not self.email.lower().endswith('@edu.omsk.ru'):
                raise ValidationError(
                    {'email': 'Для персонала и студентов нужна корпоративная почта вуза.'}
                )

    def save(self, *args, **kwargs):
        self._sync_django_access_flags()
        super().save(*args, **kwargs)

    def _sync_django_access_flags(self):
        if self.role == UserRole.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role == UserRole.STAFF:
            self.is_staff = True
            self.is_superuser = False
        else:
            self.is_staff = False
            self.is_superuser = False

    @property
    def is_makerspace_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_makerspace_staff(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}

    @property
    def can_book_without_approval(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}

    @property
    def can_manage_users(self):
        return self.role == UserRole.ADMIN

    @property
    def can_manage_training(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}

    @property
    def can_review_reservations(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}

    @property
    def can_force_cancel_reservations(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}

    def can_view_reservation_owner(self, reservation):
        if not self.is_authenticated:
            return False
        if self.role in {UserRole.STAFF, UserRole.ADMIN}:
            return True
        return reservation.user_id == self.pk

    def can_view_schedule(self):
        return self.is_authenticated

    def can_book_equipment(self, equipment):
        if not self.is_authenticated:
            return False
        if self.role in {UserRole.STAFF, UserRole.ADMIN}:
            return True
        if not equipment.requires_training:
            return True
        return self.has_completed_training
