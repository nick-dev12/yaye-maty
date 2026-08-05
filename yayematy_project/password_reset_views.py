"""Vues réinitialisation mot de passe — SMTP YAYEMATY."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy


class YayematyPasswordResetView(PasswordResetView):
    """Demande de lien de réinitialisation par e-mail."""

    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'accounts/email/password_reset_email.txt'
    html_email_template_name = 'accounts/email/password_reset_email.html'
    subject_template_name = 'accounts/email/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        form.save(
            use_https=settings.EMAIL_RESET_USE_HTTPS,
            domain_override=settings.EMAIL_RESET_DOMAIN,
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject_template_name=self.subject_template_name,
            email_template_name=self.email_template_name,
            html_email_template_name=self.html_email_template_name,
            request=self.request,
        )
        return redirect(self.get_success_url())


class YayematyPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class YayematyPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class YayematyPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'
