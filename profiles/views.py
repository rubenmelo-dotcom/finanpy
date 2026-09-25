from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView

from profiles.forms import (
    ProfileForm,
    StyledPasswordChangeForm,
    UserUpdateForm,
)
from profiles.models import Profile


class ProfileDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'profiles/profile_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.request.user.profile
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = 'profiles/profile_form.html'
    success_url = reverse_lazy('profiles:detail')

    def get_object(self, queryset=None):
        return self.request.user.profile

    def get_context_data(self, **kwargs):
        if 'user_form' not in kwargs:
            kwargs['user_form'] = UserUpdateForm(
                instance=self.request.user
            )
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        user_form = UserUpdateForm(
            data=request.POST, instance=request.user
        )
        forms_valid = [form.is_valid(), user_form.is_valid()]
        if all(forms_valid):
            user_form.save()
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso.')
            return redirect(self.get_success_url())
        return self.render_to_response(
            self.get_context_data(form=form, user_form=user_form)
        )


class UserPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = 'profiles/password_change.html'
    success_url = reverse_lazy('profiles:detail')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Senha alterada com sucesso.')
        return response
