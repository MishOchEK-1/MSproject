from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'equipment',
        'user',
        'status',
        'start_at',
        'end_at',
        'reviewed_by',
    )
    list_filter = ('status', 'equipment__category', 'equipment')
    search_fields = (
        'equipment__name',
        'equipment__inventory_number',
        'user__username',
        'user__full_name',
        'request_comment',
    )
