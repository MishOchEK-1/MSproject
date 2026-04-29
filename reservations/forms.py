from datetime import timedelta

from django import forms
from django.utils import timezone


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
    )
    request_comment = forms.CharField(
        label='Комментарий для подтверждения',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    def clean_start_at(self):
        start_at = self.cleaned_data['start_at']
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
        return start_at

    def get_end_at(self):
        return self.cleaned_data['start_at'] + timedelta(minutes=self.cleaned_data['duration_minutes'])


class ReservationExtensionForm(forms.Form):
    extra_minutes = forms.IntegerField(
        label='Продлить на, мин',
        min_value=20,
        max_value=1440,
        initial=60,
    )


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
