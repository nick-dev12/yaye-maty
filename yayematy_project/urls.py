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
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('inscription/', views.register_view, name='register'),
    path('tableau-de-bord/', views.dashboard_view, name='dashboard'),
    path('parametres/', views.settings_view, name='settings'),
    path('intelligence/', include('intelligence.urls')),
    path('deconnexion/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
]
