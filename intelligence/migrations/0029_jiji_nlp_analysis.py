"""Champs NLP pour annonces Jiji (prod + test)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0028_rename_intelligenc_jiji_kw_idx_intelligenc_matched_e005b1_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='jijilisting',
            name='analysis_method',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('keyword', 'Mot-clé local'),
                    ('camembert', 'CamemBERT'),
                    ('hybrid', 'Hybride'),
                ],
                db_index=False,
                default='pending',
                max_length=16,
                verbose_name='Méthode analyse',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='analysis_status',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('processing', 'En cours'),
                    ('done', 'Terminé'),
                    ('failed', 'Échec'),
                    ('skipped', 'Hors périmètre agricole'),
                ],
                db_index=True,
                default='pending',
                max_length=16,
                verbose_name='Statut NLP',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='analyzed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Analysé le'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='aspects',
            field=models.JSONField(blank=True, default=dict, verbose_name='Aspects détectés'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='confidence_score',
            field=models.FloatField(blank=True, null=True, verbose_name='Confiance NLP'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='extracted_product',
            field=models.CharField(
                blank=True, db_index=True, max_length=120, verbose_name='Produit extrait',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='intent',
            field=models.CharField(
                blank=True,
                choices=[
                    ('intention_achat', "Intention d'achat"),
                    ('demande_information', "Demande d'information"),
                    ('plainte', 'Plainte'),
                    ('hors_sujet', 'Hors sujet'),
                ],
                db_index=True,
                max_length=32,
                verbose_name='Intention détectée',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='is_agricultural',
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="False si l'annonce est hors périmètre équipement agricole.",
                verbose_name='Pertinent agricole',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='is_analyzed',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Analysé'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='keywords_detected',
            field=models.JSONField(blank=True, default=list, verbose_name='Mots-clés détectés'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='nlp_analyzed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='NLP le'),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='nlp_category',
            field=models.CharField(
                blank=True, db_index=True, max_length=64, verbose_name='Catégorie NLP',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='relevance_score',
            field=models.FloatField(
                blank=True, db_index=True, null=True, verbose_name='Pertinence agricole',
            ),
        ),
        migrations.AddField(
            model_name='jijilisting',
            name='sentiment',
            field=models.CharField(
                blank=True,
                choices=[
                    ('positive', 'Positif'),
                    ('neutral', 'Neutre'),
                    ('negative', 'Négatif'),
                ],
                db_index=True,
                max_length=16,
                verbose_name='Sentiment annonce',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='analysis_method',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('keyword', 'Mot-clé local'),
                    ('camembert', 'CamemBERT'),
                    ('hybrid', 'Hybride'),
                ],
                default='pending',
                max_length=16,
                verbose_name='Méthode analyse',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='analysis_status',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('processing', 'En cours'),
                    ('done', 'Terminé'),
                    ('failed', 'Échec'),
                    ('skipped', 'Hors périmètre agricole'),
                ],
                db_index=True,
                default='pending',
                max_length=16,
                verbose_name='Statut NLP',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='analyzed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Analysé le'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='aspects',
            field=models.JSONField(blank=True, default=dict, verbose_name='Aspects détectés'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='confidence_score',
            field=models.FloatField(blank=True, null=True, verbose_name='Confiance NLP'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='extracted_product',
            field=models.CharField(
                blank=True, db_index=True, max_length=120, verbose_name='Produit extrait',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='intent',
            field=models.CharField(
                blank=True,
                choices=[
                    ('intention_achat', "Intention d'achat"),
                    ('demande_information', "Demande d'information"),
                    ('plainte', 'Plainte'),
                    ('hors_sujet', 'Hors sujet'),
                ],
                db_index=True,
                max_length=32,
                verbose_name='Intention détectée',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='is_agricultural',
            field=models.BooleanField(db_index=True, default=True, verbose_name='Pertinent agricole'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='is_analyzed',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Analysé'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='keywords_detected',
            field=models.JSONField(blank=True, default=list, verbose_name='Mots-clés détectés'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='nlp_analyzed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='NLP le'),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='nlp_category',
            field=models.CharField(
                blank=True, db_index=True, max_length=64, verbose_name='Catégorie NLP',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='relevance_score',
            field=models.FloatField(
                blank=True, db_index=True, null=True, verbose_name='Pertinence agricole',
            ),
        ),
        migrations.AddField(
            model_name='testjijilisting',
            name='sentiment',
            field=models.CharField(
                blank=True,
                choices=[
                    ('positive', 'Positif'),
                    ('neutral', 'Neutre'),
                    ('negative', 'Négatif'),
                ],
                db_index=True,
                max_length=16,
                verbose_name='Sentiment annonce',
            ),
        ),
        migrations.AddIndex(
            model_name='jijilisting',
            index=models.Index(fields=['is_analyzed', '-relevance_score'], name='intel_jiji_nlp_idx'),
        ),
        migrations.AddIndex(
            model_name='jijilisting',
            index=models.Index(fields=['is_agricultural', '-views_count'], name='intel_jiji_agri_idx'),
        ),
    ]
