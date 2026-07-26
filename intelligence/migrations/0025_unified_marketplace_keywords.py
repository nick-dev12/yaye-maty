# Fusion mots-clés Jumia/Jiji → plateforme marketplace partagée

from django.db import migrations, models


def merge_marketplace_keywords(apps, schema_editor):
    MarketSearchKeyword = apps.get_model('intelligence', 'MarketSearchKeyword')

    legacy = list(
        MarketSearchKeyword.objects.filter(platform__in=('jumia', 'jiji')).order_by('id')
    )
    if not legacy:
        return

    groups: dict[tuple[str, str], list] = {}
    for kw in legacy:
        key = (kw.keyword.strip().lower(), kw.region)
        groups.setdefault(key, []).append(kw)

    for group in groups.values():
        primary = group[0]
        merged_videos = max(kw.max_videos for kw in group)
        merged_comments = max(kw.max_comments for kw in group)
        merged_category = next((kw.product_category for kw in group if kw.product_category), '')
        merged_label = next((kw.label for kw in group if kw.label), primary.label)
        merged_active = any(kw.is_active for kw in group)
        scraped_dates = [kw.last_scraped_at for kw in group if kw.last_scraped_at]
        merged_scraped = max(scraped_dates) if scraped_dates else None

        primary.platform = 'marketplace'
        primary.max_videos = merged_videos
        primary.max_comments = merged_comments
        primary.product_category = merged_category
        primary.label = merged_label
        primary.is_active = merged_active
        primary.last_scraped_at = merged_scraped
        primary.save()

        for duplicate in group[1:]:
            duplicate.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0024_marketplace_keyword_platforms'),
    ]

    operations = [
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='platform',
            field=models.CharField(
                choices=[
                    ('facebook', 'Facebook'),
                    ('tiktok', 'TikTok'),
                    ('marketplace', 'Jumia & Jiji'),
                    ('jumia', 'Jumia'),
                    ('jiji', 'Jiji'),
                ],
                db_index=True,
                default='tiktok',
                max_length=20,
                verbose_name='Plateforme',
            ),
        ),
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='max_videos',
            field=models.PositiveSmallIntegerField(
                default=15,
                help_text=(
                    'TikTok/Facebook : vidéos ou posts. '
                    'Marketplace : produits Jumia et annonces Jiji par mot-clé.'
                ),
                verbose_name='Volume max par collecte',
            ),
        ),
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='max_comments',
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text=(
                    'TikTok/Facebook : commentaires/vidéo. '
                    'Marketplace : avis Jumia par produit (10–20). Ignoré sur Jiji.'
                ),
                verbose_name='Commentaires / avis',
            ),
        ),
        migrations.RunPython(merge_marketplace_keywords, migrations.RunPython.noop),
    ]
