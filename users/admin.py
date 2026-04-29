from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            'Профиль Maker Space',
            {
                'fields': (
                    'full_name',
                    'phone',
                    'role',
                    'organization',
                    'visit_purpose',
                    'has_completed_training',
                ),
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            'Профиль Maker Space',
            {
                'fields': (
                    'email',
                    'full_name',
                    'phone',
                    'role',
                    'organization',
                    'visit_purpose',
                    'has_completed_training',
                ),
            },
        ),
    )
    list_display = (
        'username',
        'email',
        'full_name',
        'role',
        'has_completed_training',
        'is_staff',
    )
    list_filter = ('role', 'has_completed_training', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'full_name', 'phone', 'organization')
