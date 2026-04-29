from django.contrib.auth.models import AbstractUser
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

    @property
    def is_makerspace_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_makerspace_staff(self):
        return self.role in {UserRole.STAFF, UserRole.ADMIN}
