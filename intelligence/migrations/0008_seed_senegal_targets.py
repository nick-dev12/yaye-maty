"""Cibles TikTok orientées Sénégal — désactive les hashtags génériques."""

from django.db import migrations


def seed_senegal_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')

    legacy_urls = (
        'https://www.tiktok.com/tag/agriculteur',
        'https://www.tiktok.com/tag/agriculture',
        'https://www.tiktok.com/tag/elevage',
    )
    SocialScrapeTarget.objects.filter(url__in=legacy_urls).update(is_active=False)

    from urllib.parse import quote

    targets = [
        ('TikTok #AgricultureSenegal', 'https://www.tiktok.com/tag/agriculturesenegal', 15),
        ('TikTok #ElevageSenegal', 'https://www.tiktok.com/tag/elevagesenegal', 15),
        ('TikTok #AgriSN', 'https://www.tiktok.com/tag/agrisn', 15),
        ('TikTok #SenegalAgriculture', 'https://www.tiktok.com/tag/senegalagriculture', 15),
        ('TikTok #AgriculteurSenegal', 'https://www.tiktok.com/tag/agriculteursenegal', 15),
        ('TikTok recherche « agriculture senegal »', f'https://www.tiktok.com/search?q={quote("agriculture senegal")}', 12),
        ('TikTok recherche « tracteur dakar »', f'https://www.tiktok.com/search?q={quote("tracteur dakar")}', 12),
        ('TikTok recherche « materiel agricole senegal »', f'https://www.tiktok.com/search?q={quote("materiel agricole senegal")}', 12),
        ('TikTok recherche « pompe solaire senegal »', f'https://www.tiktok.com/search?q={quote("pompe solaire senegal")}', 12),
        ('TikTok recherche « elevage senegal »', f'https://www.tiktok.com/search?q={quote("elevage senegal")}', 12),
        ('TikTok recherche « touba agriculture »', f'https://www.tiktok.com/search?q={quote("touba agriculture")}', 10),
    ]

    for label, url, max_posts in targets:
        SocialScrapeTarget.objects.update_or_create(
            url=url,
            defaults={
                'label': label,
                'platform': 'tiktok',
                'region': 'SN',
                'max_posts': max_posts,
                'scrape_comments': True,
                'max_comments': 20,
                'is_active': True,
            },
        )


def unseed_senegal_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')

    senegal_urls = [
        'https://www.tiktok.com/tag/agriculturesenegal',
        'https://www.tiktok.com/tag/elevagesenegal',
        'https://www.tiktok.com/tag/agrisn',
        'https://www.tiktok.com/tag/senegalagriculture',
        'https://www.tiktok.com/tag/agriculteursenegal',
    ]
    SocialScrapeTarget.objects.filter(url__in=senegal_urls).delete()

    legacy_urls = (
        'https://www.tiktok.com/tag/agriculteur',
        'https://www.tiktok.com/tag/agriculture',
        'https://www.tiktok.com/tag/elevage',
    )
    SocialScrapeTarget.objects.filter(url__in=legacy_urls).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0007_social_engagement'),
    ]

    operations = [
        migrations.RunPython(seed_senegal_targets, unseed_senegal_targets),
    ]
