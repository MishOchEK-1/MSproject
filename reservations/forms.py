from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Reservation


class ReservationCreateForm(forms.Form):
    start_at = forms.DateTimeField(
        label='Начало брони',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    duration_minutes = forms.IntegerField(
        label='Длительность, мин',
        min_value=20,
        max_value=1440,
        initial=60,
        widget=forms.NumberInput(attrs={'step': 10}),
    )
    request_comment = forms.CharField(
        label='Комментарий для подтверждения',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    def __init__(self, *args, equipment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipment = equipment
        min_duration_minutes = Reservation.get_min_duration_minutes(equipment)
        self.fields['duration_minutes'].min_value = min_duration_minutes
        self.fields['duration_minutes'].initial = min_duration_minutes
        self.fields['duration_minutes'].widget.attrs['min'] = min_duration_minutes
        self.fields['duration_minutes'].widget.attrs['step'] = 10

    def clean_start_at(self):
        start_at = self.cleaned_data['start_at']
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
        return start_at

    def clean_duration_minutes(self):
        duration_minutes = self.cleaned_data['duration_minutes']
        Reservation.validate_duration_minutes(duration_minutes, self.equipment)
        return duration_minutes

    def get_end_at(self):
        return self.cleaned_data['start_at'] + timedelta(minutes=self.cleaned_data['duration_minutes'])


class ReservationExtensionForm(forms.Form):
    extra_minutes = forms.IntegerField(
        label='Продлить на, мин',
        min_value=10,
        max_value=1440,
        initial=10,
        widget=forms.NumberInput(attrs={'step': 10}),
    )

    def __init__(self, *args, reservation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reservation = reservation
        self.fields['extra_minutes'].initial = 10
        self.fields['extra_minutes'].widget.attrs['min'] = 10
        self.fields['extra_minutes'].widget.attrs['step'] = 10

    def clean_extra_minutes(self):
        extra_minutes = self.cleaned_data['extra_minutes']
        if self.reservation is None:
            return extra_minutes

        total_duration_minutes = self.reservation.duration_minutes + extra_minutes
        Reservation.validate_duration_minutes(total_duration_minutes, self.reservation.equipment)
        return extra_minutes


class ReservationCancelForm(forms.Form):
    cancellation_reason = forms.CharField(
        label='Причина отмены',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )


class ReservationDecisionForm(forms.Form):
    staff_comment = forms.CharField(
        label='Комментарий персонала',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    rejection_reason = forms.CharField(
        label='Причина отказа',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
