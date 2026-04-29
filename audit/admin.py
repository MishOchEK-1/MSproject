from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'action',
        'entity_type',
        'entity_id',
        'actor',
    )
    list_filter = ('action', 'entity_type')
    search_fields = ('description', 'entity_type', 'entity_label', 'actor__username', 'actor__full_name')
