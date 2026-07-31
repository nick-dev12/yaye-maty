"""

Service Top-Down — recherche TikTok par intention commerciale.



Phase 1 : récolte des URLs vidéo les plus pertinentes.

Phase 2 : forage profond (métriques + commentaires → NLP hybride).

"""



from __future__ import annotations



import logging

from dataclasses import dataclass, field



from django.utils import timezone



from intelligence.collection_config import get_collection_config

from intelligence.models import MarketSearchKeyword

from intelligence.scrapers.extractors.tiktok import TikTokExtractor

from intelligence.scrapers.tiktok_scrape_schema import clamp_max_comments

from intelligence.scrapers.human_behavior import random_sleep

from intelligence.scrapers.post_id_utils import extract_post_id
from intelligence.scrapers.social_scraper import SocialScraper

from intelligence.services.django_orm_safe import run_orm_safe
from intelligence.services.social_dedup_service import SocialDedupService

from intelligence.services.social_post_service import SocialPostService



logger = logging.getLogger(__name__)





@dataclass

class SearchTopDownResult:

    """Résultat d'un scrape Top-Down sur un mot-clé."""



    keyword_id: int

    keyword: str

    search_url: str

    success: bool

    message: str

    urls_harvested: int = 0

    skipped_urls: int = 0

    extracted: int = 0

    created: int = 0

    updated: int = 0

    skipped: int = 0

    errors: list[str] = field(default_factory=list)





class SearchTopDownService:

    """Orchestre le scraping Top-Down par mot-clé de recherche."""



    def __init__(self, scraper: SocialScraper | None = None):

        self.scraper = scraper or SocialScraper()



    def run_keyword(

        self,

        keyword: MarketSearchKeyword,

        *,

        headless: bool | None = None,

        scheduled: bool = False,

        max_videos_session: int | None = None,

    ) -> SearchTopDownResult:

        """Exécute Phase 1 + Phase 2 pour un mot-clé actif."""

        if keyword.platform != MarketSearchKeyword.Platform.TIKTOK:

            return SearchTopDownResult(

                keyword_id=keyword.pk,

                keyword=keyword.keyword,

                search_url=keyword.build_search_url(),

                success=False,

                message=f'Plateforme {keyword.platform} non supportée en Top-Down.',

            )



        config = get_collection_config() if scheduled else {}

        video_delay = (

            (config.get('SOCIAL_VIDEO_DELAY_MIN', 12.0), config.get('SOCIAL_VIDEO_DELAY_MAX', 45.0))

            if scheduled

            else (2.0, 4.5)

        )

        session_cap = max_videos_session

        if session_cap is None and scheduled:

            session_cap = int(config.get('MAX_VIDEOS_PER_KEYWORD_SESSION') or 15)

        harvest_limit = min(keyword.max_videos, session_cap) if session_cap else keyword.max_videos

        search_url = keyword.build_search_url()
        known_ids: set[str] = set()
        if scheduled:
            known_ids = run_orm_safe(SocialDedupService.known_ids_for_platform, keyword.platform)

        bundle = self.scraper.browser_factory.open(keyword.platform, headless=headless)

        extractor = TikTokExtractor()

        extracted = []

        urls: list[str] = []

        skipped_urls = 0



        try:

            page = bundle.page

            logger.info(

                'Top-Down [%s] — %s (max %s vidéo(s)/session, %s commentaires/vidéo, scheduled=%s)',

                keyword.keyword,

                search_url,

                harvest_limit,

                clamp_max_comments(keyword.max_comments),

                scheduled,

            )



            raw_urls = extractor.harvest_search_video_urls(

                page,

                search_url,

                max_urls=max(harvest_limit * 3, harvest_limit),

                skip_post_ids=known_ids,

                prefer_recent=scheduled,

            )

            urls = SocialDedupService.filter_urls_with_known_ids(
                keyword.platform, raw_urls, known_ids,
            )[:harvest_limit]

            skipped_urls = max(0, len(raw_urls) - len(urls))



            for video_url in urls:
                if SocialDedupService.is_url_in_known_ids(keyword.platform, video_url, known_ids):
                    skipped_urls += 1
                    continue

                post = extractor.extract_video_detail(

                    page,

                    video_url,

                    max_comments=clamp_max_comments(keyword.max_comments),

                )

                if post:

                    if keyword.product_category:

                        post.metadata['product_category'] = keyword.product_category

                    extracted.append(post)
                    post_id = extract_post_id(keyword.platform, video_url)
                    if post_id:
                        known_ids.add(post_id)



                random_sleep(video_delay[0], video_delay[1])



            self.scraper.session_manager.save_storage_state(bundle.context, keyword.platform)



        except Exception as exc:

            logger.exception('Échec Top-Down mot-clé %s : %s', keyword.pk, exc)

            return SearchTopDownResult(

                keyword_id=keyword.pk,

                keyword=keyword.keyword,

                search_url=search_url,

                success=False,

                message=str(exc),

                urls_harvested=len(urls),

                skipped_urls=skipped_urls,

            )

        finally:

            bundle.close()



        def _persist_top_down_results() -> dict:
            stats = SocialPostService.save_extracted_posts(
                platform=keyword.platform,
                source_url=search_url,
                extracted=extracted,
                skip_if_exists=scheduled,
            )
            from intelligence.services.collection_model_router import CollectionModelRouter

            if (
                not CollectionModelRouter().is_test
                and keyword.pk is not None
            ):
                keyword.last_scraped_at = timezone.now()
                keyword.save(update_fields=['last_scraped_at', 'updated_at'])
            return stats

        save_stats = run_orm_safe(_persist_top_down_results)



        return SearchTopDownResult(

            keyword_id=keyword.pk,

            keyword=keyword.keyword,

            search_url=search_url,

            success=True,

            message='Scrape Top-Down terminé.',

            urls_harvested=len(urls),

            skipped_urls=skipped_urls,

            extracted=save_stats['total'],

            created=save_stats['created'],

            updated=save_stats['updated'],

            skipped=save_stats['skipped'],

        )



    def run_active_keywords(

        self,

        *,

        headless: bool | None = None,

        scheduled: bool = False,

    ) -> list[SearchTopDownResult]:

        from intelligence.services.active_keyword_service import ActiveKeywordService

        keywords = ActiveKeywordService.list_for_social()

        results: list[SearchTopDownResult] = []

        config = get_collection_config() if scheduled else {}



        for keyword in keywords:
            if keyword.platform != MarketSearchKeyword.Platform.TIKTOK:
                continue
            results.append(self.run_keyword(keyword, headless=headless, scheduled=scheduled))

            if scheduled:

                random_sleep(

                    config.get('SOCIAL_KEYWORD_DELAY_MIN', 30.0),

                    config.get('SOCIAL_KEYWORD_DELAY_MAX', 90.0),

                )

            else:

                random_sleep(5.0, 10.0)



        return results


