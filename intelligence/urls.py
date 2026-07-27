from django.urls import path

from . import views

app_name = 'intelligence'

urlpatterns = [
    path('', views.intelligence_index_view, name='index'),
    path('archives/', views.intelligence_archives_view, name='archives'),
    path('domaines/', views.intelligence_domains_view, name='domaines'),
    path('collecte/', views.collecte_view, name='collecte'),
    path('collecte/test/', views.collecte_test_view, name='collecte_test'),
    path('collecte/test/donnees/', views.collecte_test_donnees_view, name='collecte_test_donnees'),
    path('collecte/api/lancer/', views.collecte_api_lancer_view, name='collecte_api_lancer'),
    path(
        'collecte/api/statut/<str:task_id>/',
        views.collecte_api_statut_view,
        name='collecte_api_statut',
    ),
    path('collecte/api/arreter/', views.collecte_api_arreter_view, name='collecte_api_arreter'),
    path('collecte/api/reset-session/', views.collecte_api_reset_session_view, name='collecte_api_reset_session'),
    path('collecte/api/celery/status/', views.collecte_api_celery_status_view, name='collecte_api_celery_status'),
    path('collecte/api/celery/start/', views.collecte_api_celery_start_view, name='collecte_api_celery_start'),
    path('collecte/api/celery/stop/', views.collecte_api_celery_stop_view, name='collecte_api_celery_stop'),
    path('api/raw-data/', views.api_raw_data_view, name='api_raw_data'),
    path('api/analyzed-data/', views.api_analyzed_data_view, name='api_analyzed_data'),
    path('api/social-posts/', views.api_social_posts_view, name='api_social_posts'),
    path('api/keywords/', views.api_keywords_view, name='api_keywords'),
    path('api/raw-jumia-reviews/', views.api_raw_jumia_reviews_view, name='api_raw_jumia_reviews'),
    path(
        'api/analyzed-jumia-reviews/',
        views.api_analyzed_jumia_reviews_view,
        name='api_analyzed_jumia_reviews',
    ),
    path('api/raw-jiji-listings/', views.api_raw_jiji_listings_view, name='api_raw_jiji_listings'),
    path(
        'api/analyzed-jiji-listings/',
        views.api_analyzed_jiji_listings_view,
        name='api_analyzed_jiji_listings',
    ),
]
