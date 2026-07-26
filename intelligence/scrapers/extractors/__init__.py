from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.extractors.facebook import FacebookExtractor
from intelligence.scrapers.extractors.tiktok import TikTokExtractor

EXTRACTOR_REGISTRY = {
    'tiktok': TikTokExtractor,
    'facebook': FacebookExtractor,
}


def get_extractor(platform: str):
    extractor_cls = EXTRACTOR_REGISTRY.get(platform)
    if not extractor_cls:
        raise ValueError(f'Aucun extracteur pour la plateforme : {platform}')
    return extractor_cls()
