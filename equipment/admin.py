from django.contrib import admin

from .models import Equipment, EquipmentCategory, EquipmentDowntime


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class EquipmentDowntimeInline(admin.TabularInline):
    model = EquipmentDowntime
    extra = 0


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'inventory_number',
        'category',
        'status',
        'slot_duration_minutes',
        'requires_training',
    )
    list_filter = ('category', 'status', 'requires_training')
    search_fields = ('name', 'inventory_number', 'description')
    inlines = [EquipmentDowntimeInline]


@admin.register(EquipmentDowntime)
class EquipmentDowntimeAdmin(admin.ModelAdmin):
    list_display = ('equipment', 'start_at', 'end_at', 'created_by')
    list_filter = ('equipment__category', 'equipment')
    search_fields = ('equipment__name', 'reason')
