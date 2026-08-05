"""
URL configuration for yayematy_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views
from .password_reset_views import (
    YayematyPasswordResetCompleteView,
    YayematyPasswordResetConfirmView,
    YayematyPasswordResetDoneView,
    YayematyPasswordResetView,
)

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('inscription/', views.register_view, name='register'),
    path(
        'mot-de-passe/oublie/',
        YayematyPasswordResetView.as_view(),
        name='password_reset',
    ),
    path(
        'mot-de-passe/oublie/envoye/',
        YayematyPasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'mot-de-passe/reinitialiser/<uidb64>/<token>/',
        YayematyPasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'mot-de-passe/reinitialise/',
        YayematyPasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
    path('tableau-de-bord/', views.dashboard_view, name='dashboard'),
    path('profil/', views.profile_view, name='profile'),
    path('parametres/', views.settings_view, name='settings'),
    path('intelligence/', include('intelligence.urls')),
    path('deconnexion/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('admin/', admin.site.urls),
]

# Pages locales non versionnées (dossier local_dev/ gitignoré)
if settings.DEBUG:
    try:
        from local_dev.urls import urlpatterns as _local_urlpatterns
        urlpatterns += _local_urlpatterns
    except ImportError:
        pass
