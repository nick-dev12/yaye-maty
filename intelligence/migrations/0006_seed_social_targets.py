"""Données initiales : cibles TikTok agriculture / élevage."""

from django.db import migrations


def seed_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')

    targets = [
        {
            'label': 'TikTok #agriculteur',
            'platform': 'tiktok',
            'url': 'https://www.tiktok.com/tag/agriculteur',
            'max_posts': 20,
        },
        {
            'label': 'TikTok #agriculture',
            'platform': 'tiktok',
            'url': 'https://www.tiktok.com/tag/agriculture',
            'max_posts': 20,
        },
        {
            'label': 'TikTok #elevage',
            'platform': 'tiktok',
            'url': 'https://www.tiktok.com/tag/elevage',
            'max_posts': 20,
        },
    ]

    for data in targets:
        SocialScrapeTarget.objects.get_or_create(
            url=data['url'],
            defaults=data,
        )


def unseed_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')
    urls = [
        'https://www.tiktok.com/tag/agriculteur',
        'https://www.tiktok.com/tag/agriculture',
        'https://www.tiktok.com/tag/elevage',
    ]
    SocialScrapeTarget.objects.filter(url__in=urls).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0005_social_posts'),
    ]

    operations = [
        migrations.RunPython(seed_targets, unseed_targets),
    ]
