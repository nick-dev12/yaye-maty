"""Modèle SocialComment — commentaires analysés par NLP hybride."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0008_seed_senegal_targets'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocialComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Texte')),
                ('text_hash', models.CharField(db_index=True, max_length=64, verbose_name='Empreinte')),
                ('intent', models.CharField(blank=True, choices=[('intention_achat', "Intention d'achat"), ('demande_information', "Demande d'information"), ('hors_sujet', 'Hors sujet'), ('plainte', 'Plainte')], db_index=True, max_length=32, verbose_name='Intention')),
                ('confidence_score', models.FloatField(blank=True, null=True, verbose_name='Confiance')),
                ('analysis_method', models.CharField(choices=[('keyword', 'Filtre mots-clés (FR/Wolof)'), ('camembert', 'CamemBERT zero-shot'), ('pending', 'En attente')], default='pending', max_length=16, verbose_name='Méthode')),
                ('is_analyzed', models.BooleanField(db_index=True, default=False, verbose_name='Analysé')),
                ('analyzed_at', models.DateTimeField(blank=True, null=True, verbose_name='Analysé le')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_comments', to='intelligence.socialpost', verbose_name='Publication')),
            ],
            options={
                'verbose_name': 'Commentaire social',
                'verbose_name_plural': 'Commentaires sociaux',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='socialcomment',
            constraint=models.UniqueConstraint(fields=('post', 'text_hash'), name='unique_social_comment_hash'),
        ),
    ]
