"""Mots-clés recherche Top-Down + seed marché agricole SN."""

from django.db import migrations, models


DEFAULT_SEARCH_KEYWORDS = [
    ('tracteur dakar', 'tracteurs_machinisme', 15),
    ('materiel agricole senegal', 'tracteurs_machinisme', 15),
    ('pompe solaire senegal', 'solaire_pompage', 12),
    ('agriculture senegal', 'autre', 12),
    ('elevage senegal', 'elevage_alimentation', 12),
    ('touba agriculture', 'autre', 10),
    ('motopompe senegal', 'irrigation', 12),
    ('semence agriculture senegal', 'semences_engrais', 10),
]


def seed_search_keywords(apps, schema_editor):
    MarketSearchKeyword = apps.get_model('intelligence', 'MarketSearchKeyword')
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')

    for keyword, category, max_videos in DEFAULT_SEARCH_KEYWORDS:
        MarketSearchKeyword.objects.get_or_create(
            platform='tiktok',
            keyword=keyword,
            region='SN',
            defaults={
                'label': keyword.title(),
                'product_category': category,
                'max_videos': max_videos,
                'max_comments': 20,
                'is_active': True,
            },
        )

    SocialScrapeTarget.objects.filter(url__contains='/search?').update(is_active=False)


def unseed_search_keywords(apps, schema_editor):
    MarketSearchKeyword = apps.get_model('intelligence', 'MarketSearchKeyword')
    keywords = [row[0] for row in DEFAULT_SEARCH_KEYWORDS]
    MarketSearchKeyword.objects.filter(keyword__in=keywords).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0011_scraped_post_structure'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketSearchKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, max_length=120, verbose_name='Libellé')),
                ('keyword', models.CharField(db_index=True, max_length=200, verbose_name='Mot-clé recherche')),
                ('platform', models.CharField(choices=[('facebook', 'Facebook'), ('tiktok', 'TikTok')], db_index=True, default='tiktok', max_length=20, verbose_name='Plateforme')),
                ('product_category', models.CharField(blank=True, help_text='Slug métier optionnel (irrigation, tracteurs_machinisme…)', max_length=80, verbose_name='Catégorie produit')),
                ('region', models.CharField(db_index=True, default='SN', max_length=8, verbose_name='Région')),
                ('max_videos', models.PositiveSmallIntegerField(default=15, verbose_name='Max vidéos / recherche')),
                ('max_comments', models.PositiveSmallIntegerField(default=20, verbose_name='Max commentaires / vidéo')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Actif')),
                ('last_scraped_at', models.DateTimeField(blank=True, null=True, verbose_name='Dernier scrape')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour le')),
            ],
            options={
                'verbose_name': 'Mot-clé recherche marché',
                'verbose_name_plural': 'Mots-clés recherche marché',
                'ordering': ['-is_active', 'keyword'],
            },
        ),
        migrations.AddConstraint(
            model_name='marketsearchkeyword',
            constraint=models.UniqueConstraint(fields=('platform', 'keyword', 'region'), name='unique_market_search_keyword'),
        ),
        migrations.RunPython(seed_search_keywords, unseed_search_keywords),
    ]
