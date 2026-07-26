"""Tables miroir pour les données de session test (isolation production)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0017_seed_facebook_targets'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestSocialPost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(choices=[('facebook', 'Facebook'), ('tiktok', 'TikTok')], db_index=True, max_length=20, verbose_name='Plateforme')),
                ('platform_post_id', models.CharField(blank=True, db_index=True, max_length=100, verbose_name='ID vidéo (video_id)')),
                ('source_url', models.URLField(max_length=500, verbose_name='URL source')),
                ('post_url', models.URLField(blank=True, max_length=500, verbose_name='URL publication')),
                ('author', models.CharField(blank=True, max_length=120, verbose_name='Auteur')),
                ('content', models.TextField(verbose_name='Description (caption)')),
                ('content_hash', models.CharField(db_index=True, max_length=64, verbose_name='Empreinte')),
                ('hashtags', models.JSONField(blank=True, default=list, verbose_name='Hashtags')),
                ('view_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Vues')),
                ('like_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Likes')),
                ('share_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Partages')),
                ('save_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Favoris (saves)')),
                ('comment_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Commentaires (total plateforme)')),
                ('comments_scraped_count', models.PositiveSmallIntegerField(default=0, verbose_name='Commentaires collectés')),
                ('demand_score', models.PositiveIntegerField(db_index=True, default=0, verbose_name='Score demande')),
                ('purchase_intent_count', models.PositiveSmallIntegerField(default=0, verbose_name='Intentions achat')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='Publié le')),
                ('comments', models.JSONField(blank=True, default=list, verbose_name='Commentaires (JSON)')),
                ('analysis_status', models.CharField(choices=[('pending', 'En attente'), ('processing', 'En cours'), ('done', 'Analysé'), ('failed', 'Échec')], db_index=True, default='pending', max_length=12, verbose_name='Statut analyse')),
                ('category', models.CharField(blank=True, max_length=80, verbose_name='Catégorie NLP')),
                ('extracted_product', models.CharField(blank=True, db_index=True, max_length=120, verbose_name='Produit principal')),
                ('extracted_product_slug', models.SlugField(blank=True, max_length=80, verbose_name='Slug produit')),
                ('sentiment', models.CharField(blank=True, max_length=20, verbose_name='Sentiment')),
                ('keywords', models.JSONField(blank=True, default=list, verbose_name='Mots-clés')),
                ('scraped_at', models.DateTimeField(auto_now_add=True, verbose_name='Collecté le')),
                ('analyzed_at', models.DateTimeField(blank=True, null=True, verbose_name='Analysé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour le')),
            ],
            options={
                'verbose_name': 'Publication test',
                'verbose_name_plural': 'Publications test',
                'db_table': 'intelligence_test_socialpost',
                'ordering': ['-scraped_at'],
            },
        ),
        migrations.CreateModel(
            name='TestDiscoveredQuery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(choices=[('agriculture', 'Agriculture & Forêt'), ('elevage', 'Élevage (Animaux de ferme)')], db_index=True, max_length=50, verbose_name='Domaine')),
                ('query', models.CharField(db_index=True, max_length=255, verbose_name='Requête')),
                ('query_type', models.CharField(choices=[('top', 'Top recherches'), ('rising', 'En forte hausse')], max_length=10, verbose_name='Type')),
                ('value_display', models.CharField(max_length=50, verbose_name='Valeur Google')),
                ('region', models.CharField(default='SN', max_length=5, verbose_name='Région')),
                ('discovered_at', models.DateTimeField(auto_now=True, verbose_name='Découvert le')),
            ],
            options={
                'verbose_name': 'Requête test',
                'verbose_name_plural': 'Requêtes test',
                'db_table': 'intelligence_test_discoveredquery',
                'ordering': ['-discovered_at', 'domain', 'query_type'],
            },
        ),
        migrations.CreateModel(
            name='TestTopPurchaseRecommendation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rank', models.PositiveSmallIntegerField(db_index=True, verbose_name='Rang')),
                ('product_slug', models.SlugField(max_length=80, verbose_name='Slug produit')),
                ('product_name', models.CharField(max_length=120, verbose_name='Nom produit')),
                ('category', models.CharField(blank=True, max_length=80, verbose_name='Catégorie métier')),
                ('score', models.FloatField(db_index=True, verbose_name='Score demande')),
                ('score_normalized', models.PositiveSmallIntegerField(default=0, verbose_name='Score affiché (0-100)')),
                ('purchase_intent_count', models.PositiveIntegerField(default=0, verbose_name="Intentions d'achat")),
                ('info_intent_count', models.PositiveIntegerField(default=0, verbose_name="Demandes d'info")),
                ('total_views', models.PositiveBigIntegerField(default=0, verbose_name='Vues cumulées')),
                ('trends_boost', models.FloatField(default=0, verbose_name='Bonus Google Trends')),
                ('related_posts', models.PositiveIntegerField(default=0, verbose_name='Publications liées')),
                ('evidence_text', models.CharField(blank=True, max_length=500, verbose_name='Preuve (résumé)')),
                ('computed_at', models.DateTimeField(auto_now=True, verbose_name='Calculé le')),
            ],
            options={
                'verbose_name': 'Recommandation test (Top 10)',
                'verbose_name_plural': 'Recommandations test (Top 10)',
                'db_table': 'intelligence_test_toppurchaserecommendation',
                'ordering': ['rank'],
            },
        ),
        migrations.CreateModel(
            name='TestSocialComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform_comment_id', models.CharField(blank=True, db_index=True, max_length=100, verbose_name='ID commentaire')),
                ('text', models.TextField(verbose_name='Texte du commentaire')),
                ('text_hash', models.CharField(db_index=True, max_length=64, verbose_name='Empreinte')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='Date du commentaire')),
                ('intent', models.CharField(blank=True, choices=[('intention_achat', "Intention d'achat"), ('demande_information', "Demande d'information"), ('hors_sujet', 'Hors sujet'), ('plainte', 'Plainte')], db_index=True, max_length=32, verbose_name='Intention')),
                ('extracted_product', models.CharField(blank=True, db_index=True, max_length=120, verbose_name='Produit extrait')),
                ('extracted_product_slug', models.SlugField(blank=True, max_length=80, verbose_name='Slug produit')),
                ('confidence_score', models.FloatField(blank=True, null=True, verbose_name='Confiance')),
                ('analysis_method', models.CharField(choices=[('keyword', 'Filtre mots-clés (FR/Wolof)'), ('camembert', 'CamemBERT zero-shot'), ('pending', 'En attente')], default='pending', max_length=16, verbose_name='Méthode')),
                ('is_analyzed', models.BooleanField(db_index=True, default=False, verbose_name='Analysé')),
                ('analyzed_at', models.DateTimeField(blank=True, null=True, verbose_name='Analysé le')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_comments', to='intelligence.testsocialpost', verbose_name='Publication test')),
            ],
            options={
                'verbose_name': 'Commentaire test',
                'verbose_name_plural': 'Commentaires test',
                'db_table': 'intelligence_test_socialcomment',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='testsocialpost',
            constraint=models.UniqueConstraint(fields=('platform', 'content_hash'), name='unique_test_social_post_hash'),
        ),
        migrations.AddConstraint(
            model_name='testsocialpost',
            constraint=models.UniqueConstraint(
                condition=models.Q(('platform_post_id__gt', '')),
                fields=('platform', 'platform_post_id'),
                name='unique_test_social_post_platform_id',
            ),
        ),
        migrations.AddConstraint(
            model_name='testdiscoveredquery',
            constraint=models.UniqueConstraint(fields=('domain', 'query', 'query_type', 'region'), name='unique_test_discovered_query'),
        ),
        migrations.AddConstraint(
            model_name='testtoppurchaserecommendation',
            constraint=models.UniqueConstraint(fields=('rank',), name='unique_test_top_purchase_rank'),
        ),
        migrations.AddConstraint(
            model_name='testsocialcomment',
            constraint=models.UniqueConstraint(fields=('post', 'text_hash'), name='unique_test_social_comment_hash'),
        ),
        migrations.AddConstraint(
            model_name='testsocialcomment',
            constraint=models.UniqueConstraint(
                condition=models.Q(('platform_comment_id__gt', '')),
                fields=('post', 'platform_comment_id'),
                name='unique_test_social_comment_platform_id',
            ),
        ),
    ]
