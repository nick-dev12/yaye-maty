"""Backend SMTP — contourne le mismatch certificat cPanel (mail.yayematy.com)."""

from __future__ import annotations

import ssl

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend


class EmailBackend(SmtpEmailBackend):
    """
    Utilise un contexte SSL non vérifié si ``EMAIL_SSL_INSECURE=True``.

    Nécessaire lorsque le certificat du serveur est émis pour ``yayematy.com``
    mais que l'hôte SMTP est ``mail.yayematy.com`` (cPanel courant).
    """

    def _ssl_context(self) -> ssl.SSLContext:
        if getattr(settings, 'EMAIL_SSL_INSECURE', False):
            return ssl._create_unverified_context()
        return ssl.create_default_context()

    def open(self):
        if self.connection:
            return False

        connection_params = {'timeout': self.timeout}
        if self.use_ssl:
            connection_params['context'] = self._ssl_context()
        try:
            import smtplib

            if self.use_ssl:
                self.connection = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    **connection_params,
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host,
                    self.port,
                    **connection_params,
                )
                if self.use_tls:
                    self.connection.starttls(context=self._ssl_context())

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if self.fail_silently:
                return False
            raise
