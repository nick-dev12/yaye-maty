"""Données initiales : cibles Facebook agriculture Sénégal."""

from django.db import migrations


def seed_facebook_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')

    from intelligence.scrapers.facebook_targets import FACEBOOK_DEFAULT_TARGETS

    for data in FACEBOOK_DEFAULT_TARGETS:
        SocialScrapeTarget.objects.update_or_create(
            url=data['url'],
            defaults={
                'label': data['label'],
                'platform': 'facebook',
                'region': 'SN',
                'max_posts': data.get('max_posts', 15),
                'scrape_comments': data.get('scrape_comments', False),
                'max_comments': 0,
                'is_active': data.get('is_active', True),
            },
        )


def unseed_facebook_targets(apps, schema_editor):
    SocialScrapeTarget = apps.get_model('intelligence', 'SocialScrapeTarget')
    from intelligence.scrapers.facebook_targets import FACEBOOK_DEFAULT_TARGETS

    urls = [item['url'] for item in FACEBOOK_DEFAULT_TARGETS]
    SocialScrapeTarget.objects.filter(platform='facebook', url__in=urls).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0016_socialcomment_extracted_product_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_facebook_targets, unseed_facebook_targets),
    ]
