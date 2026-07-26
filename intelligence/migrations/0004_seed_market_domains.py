"""Données initiales : domaines Agriculture et Élevage."""

from django.db import migrations


def seed_domains(apps, schema_editor):
    MarketDomain = apps.get_model('intelligence', 'MarketDomain')
    DiscoveryConfig = apps.get_model('intelligence', 'DiscoveryConfig')

    domains = [
        {
            'slug': 'agriculture',
            'label': 'Agriculture & Forêt',
            'cat_id': 43,
            'seed_keywords': (
                'agriculture, tracteur, engrais, semence, irrigation, pompe solaire'
            ),
        },
        {
            'slug': 'elevage',
            'label': 'Élevage (Animaux de ferme)',
            'cat_id': 1177,
            'seed_keywords': 'élevage, volaille, poulet, bétail, aliment volaille',
        },
    ]

    created = []
    for data in domains:
        domain, _ = MarketDomain.objects.get_or_create(
            slug=data['slug'],
            defaults=data,
        )
        created.append(domain)

    config, _ = DiscoveryConfig.objects.get_or_create(pk=1)
    config.selected_domains.set(created)


def unseed_domains(apps, schema_editor):
    MarketDomain = apps.get_model('intelligence', 'MarketDomain')
    MarketDomain.objects.filter(slug__in=['agriculture', 'elevage']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0003_marketdomain_discoveryconfig'),
    ]

    operations = [
        migrations.RunPython(seed_domains, unseed_domains),
    ]
