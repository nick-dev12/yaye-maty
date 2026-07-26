"""Mots-clés de recherche Top-Down — intention commerciale TikTok/Facebook."""



from django.db import models



from intelligence.scrapers.constants import (

    PLATFORM_FACEBOOK,

    PLATFORM_JIJI,

    PLATFORM_JUMIA,

    PLATFORM_MARKETPLACE,

    PLATFORM_TIKTOK,

)





class MarketSearchKeyword(models.Model):

    """

    Mot-clé de recherche marché (stratégie Top-Down).



    Phase 1 : récolte des URLs vidéo depuis la page recherche TikTok.

    Phase 2 : extraction profonde (métriques + commentaires → NLP hybride).

    """



    class Platform(models.TextChoices):

        FACEBOOK = PLATFORM_FACEBOOK, 'Facebook'

        TIKTOK = PLATFORM_TIKTOK, 'TikTok'

        MARKETPLACE = PLATFORM_MARKETPLACE, 'Jumia & Jiji'

        JUMIA = PLATFORM_JUMIA, 'Jumia'

        JIJI = PLATFORM_JIJI, 'Jiji'



    label = models.CharField('Libellé', max_length=120, blank=True)

    keyword = models.CharField('Mot-clé recherche', max_length=200, db_index=True)

    platform = models.CharField(

        'Plateforme',

        max_length=20,

        choices=Platform.choices,

        default=Platform.TIKTOK,

        db_index=True,

    )

    product_category = models.CharField(

        'Catégorie produit',

        max_length=80,

        blank=True,

        help_text='Slug métier optionnel (irrigation, tracteurs_machinisme…)',

    )

    region = models.CharField('Région', max_length=8, default='SN', db_index=True)

    max_videos = models.PositiveSmallIntegerField(

        'Volume max par collecte',

        default=15,

        help_text=(

            'TikTok/Facebook : vidéos ou posts. '

            'Marketplace : produits Jumia et annonces Jiji par mot-clé.'

        ),

    )

    max_comments = models.PositiveSmallIntegerField(

        'Commentaires / avis',

        default=20,

        help_text=(

            'TikTok/Facebook : commentaires/vidéo. '

            'Marketplace : avis Jumia par produit (10–20). Ignoré sur Jiji.'

        ),

    )

    is_active = models.BooleanField('Actif', default=True, db_index=True)

    last_scraped_at = models.DateTimeField('Dernier scrape', null=True, blank=True)

    listing_page_offset = models.PositiveSmallIntegerField(
        'Page listing Jumia (rotation)',
        default=1,
        help_text='Page de départ pour la prochaine collecte Jumia (évite de re-scraper les mêmes listings).',
    )

    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)



    class Meta:

        verbose_name = 'Mot-clé recherche marché'

        verbose_name_plural = 'Mots-clés recherche marché'

        ordering = ['-is_active', 'keyword']

        constraints = [

            models.UniqueConstraint(

                fields=['platform', 'keyword', 'region'],

                name='unique_market_search_keyword',

            ),

        ]



    def __str__(self):

        return self.display_label



    @property

    def display_label(self) -> str:

        if self.label:

            return self.label

        if self.is_marketplace:

            return f'{self.keyword} (Jumia & Jiji)'

        return f'{self.keyword} ({self.get_platform_display()})'



    def build_search_url(self, *, target: str | None = None) -> str:

        """URL cible de collecte selon la plateforme Paramètres."""

        from urllib.parse import quote



        if self.is_marketplace:

            resolved = target or PLATFORM_JUMIA

            if resolved == PLATFORM_JIJI:

                return self.build_jiji_url()

            return self.build_jumia_url()



        if self.platform == self.Platform.JUMIA:

            return self.build_jumia_url()



        if self.platform == self.Platform.JIJI:

            return self.build_jiji_url()



        query = quote(self.keyword.strip())

        if self.platform == self.Platform.TIKTOK:

            return f'https://www.tiktok.com/search?q={query}'

        return f'https://www.facebook.com/search/top?q={query}'



    def build_jumia_url(self) -> str:

        from intelligence.services.marketplace_catalog_utils import resolve_jumia_category_path



        path = resolve_jumia_category_path(

            self.keyword,

            product_category=self.product_category,

        )

        return f'https://www.jumia.sn{path}'



    def build_jiji_url(self) -> str:

        from urllib.parse import quote



        from intelligence.services.marketplace_catalog_utils import resolve_jiji_category_path



        path = resolve_jiji_category_path(

            self.keyword,

            product_category=self.product_category,

        )

        base = 'https://jiji.sn'

        return f'{base}{path}' if path else f'{base}/search?query={quote(self.keyword.strip())}'



    @property

    def is_marketplace(self) -> bool:

        return self.platform in (

            self.Platform.MARKETPLACE,

            self.Platform.JUMIA,

            self.Platform.JIJI,

        )



    @property

    def is_social(self) -> bool:

        return self.platform in (self.Platform.TIKTOK, self.Platform.FACEBOOK)



    def save(self, *args, **kwargs):

        if not self.label:

            self.label = self.keyword[:120]

        super().save(*args, **kwargs)


