from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from audit.models import AuditAction
from audit.services import log_action
from reservations.models import Reservation

from .forms import EmailAuthenticationForm, UserProfileForm, UserRegistrationForm, UserTrainingStatusForm
from .models import User


class UserRegistrationView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:profile')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend=settings.AUTHENTICATION_BACKENDS[0])
        messages.success(self.request, 'Профиль создан. Вы вошли в систему как гость.')
        return response


class UserLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('users:profile')


class UserLogoutView(LogoutView):
    next_page = reverse_lazy('index')


class UserProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'users/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        recent_notifications = user.notifications.select_related('reservation__equipment', 'actor')[:5]
        upcoming_reservations = user.reservations.select_related('equipment').filter(
            status__in=Reservation.ACTIVE_STATUSES,
        ).order_by('start_at')[:5]
        context.update(
            {
                'recent_notifications': recent_notifications,
                'upcoming_reservations': upcoming_reservations,
            }
        )
        return context


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = UserProfileForm
    template_name = 'users/profile_edit.html'
    success_url = reverse_lazy('users:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Профиль обновлен.')
        return super().form_valid(form)


class TrainingManagementAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_manage_training


class TrainingDashboardView(TrainingManagementAccessMixin, ListView):
    model = User
    template_name = 'users/training_dashboard.html'
    context_object_name = 'users_list'
    paginate_by = 30

    def get_queryset(self):
        queryset = User.objects.order_by('full_name')
        query = self.request.GET.get('q', '').strip()
        role = self.request.GET.get('role', '').strip()
        training = self.request.GET.get('training', '').strip()

        if query:
            queryset = queryset.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
        if role:
            queryset = queryset.filter(role=role)
        if training == 'passed':
            queryset = queryset.filter(has_completed_training=True)
        if training == 'not-passed':
            queryset = queryset.filter(has_completed_training=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_choices'] = User._meta.get_field('role').choices
        context['training_filter'] = self.request.GET.get('training', '')
        return context


class TrainingStatusUpdateView(TrainingManagementAccessMixin, UpdateView):
    model = User
    form_class = UserTrainingStatusForm
    template_name = 'users/training_update.html'
    success_url = reverse_lazy('users:training-dashboard')

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs['pk'])

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            actor=self.request.user,
            action=AuditAction.TRAINING_STATUS_CHANGED,
            entity=self.object,
            description=f'Изменен статус инструктажа пользователя {self.object.full_name}.',
            payload={'has_completed_training': self.object.has_completed_training},
        )
        messages.success(self.request, 'Статус инструктажа обновлен.')
        return response
