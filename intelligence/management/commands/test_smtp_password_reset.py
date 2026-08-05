"""
Test SMTP + envoi d'un e-mail de réinitialisation mot de passe.

Usage :
  python manage.py test_smtp_password_reset webgeniuses12@gmail.com
  python manage.py test_smtp_password_reset webgeniuses12@gmail.com --ensure-account
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Vérifie la configuration SMTP et envoie un e-mail de réinitialisation.'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            nargs='?',
            default='',
            help='Adresse e-mail du compte à réinitialiser',
        )
        parser.add_argument(
            '--ensure-account',
            action='store_true',
            help='Associe l\'e-mail au compte « yayematy » si aucun compte ne correspond (test dev).',
        )

    def handle(self, *args, **options):
        target = (options['email'] or '').strip().lower()
        if not target:
            raise CommandError(
                'Indiquez une adresse e-mail : '
                'python manage.py test_smtp_password_reset user@exemple.com'
            )

        if not settings.EMAIL_HOST_PASSWORD:
            raise CommandError(
                'EMAIL_HOST_PASSWORD est vide dans .env — '
                'ajoutez le mot de passe du compte service@yayematy.com.'
            )

        self.stdout.write(
            f'Hôte SMTP : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
            f'(SSL={settings.EMAIL_USE_SSL})'
        )
        self.stdout.write(f'Expéditeur : {settings.DEFAULT_FROM_EMAIL}')

        try:
            send_mail(
                subject='Test SMTP YAYEMATY MARKET',
                message=(
                    'Connexion SMTP opérationnelle.\n'
                    'Un e-mail de réinitialisation suit si le compte existe.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[target],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f'Échec envoi SMTP : {exc}') from exc

        self.stdout.write(self.style.SUCCESS(f'OK Test SMTP envoye a {target}'))

        User = get_user_model()
        users = User.objects.filter(email__iexact=target)
        if not users.exists() and options['ensure_account']:
            user = User.objects.filter(username='yayematy').first()
            if user:
                user.email = target
                user.save(update_fields=['email'])
                users = User.objects.filter(email__iexact=target)
                self.stdout.write(self.style.WARNING(
                    f'Compte "{user.username}" associe a {target} (test).'
                ))

        if not users.exists():
            self.stdout.write(self.style.WARNING(
                f'Aucun compte avec l\'e-mail {target} — '
                'e-mail de réinitialisation non envoyé. '
                'Utilisez --ensure-account ou inscrivez-vous avec cet e-mail.'
            ))
            return

        form = PasswordResetForm(data={'email': target})
        if not form.is_valid():
            raise CommandError(f'Formulaire reset invalide : {form.errors}')

        form.save(
            domain_override=settings.EMAIL_RESET_DOMAIN,
            use_https=settings.EMAIL_RESET_USE_HTTPS,
            from_email=settings.DEFAULT_FROM_EMAIL,
            email_template_name='accounts/email/password_reset_email.txt',
            html_email_template_name='accounts/email/password_reset_email.html',
            subject_template_name='accounts/email/password_reset_subject.txt',
        )
        self.stdout.write(self.style.SUCCESS(
            f'OK E-mail de reinitialisation mot de passe envoye a {target}'
        ))
