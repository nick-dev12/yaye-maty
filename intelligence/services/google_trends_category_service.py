"""
Résolution automatique des catégories Google Trends à partir du libellé saisi.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import get_close_matches
from functools import lru_cache

from pytrends.request import TrendReq

logger = logging.getLogger(__name__)


class GoogleTrendsCategoryService:
    """Associe un nom de domaine à l'ID catégorie Google Trends."""

    @classmethod
    def resolve_category(cls, label: str) -> tuple[int, str] | None:
        """
        Retourne (cat_id, nom_catégorie) pour un libellé utilisateur.

        Ex. « Agriculture & Forêt » → (46, « Agriculture et sylviculture »)
        """
        normalized_label = cls._normalize(label)
        if not normalized_label:
            return None

        categories = cls._get_flat_categories()

        for cat_id, name in categories:
            if cls._normalize(name) == normalized_label:
                return cat_id, name

        for cat_id, name in categories:
            norm_name = cls._normalize(name)
            if normalized_label in norm_name or norm_name in normalized_label:
                return cat_id, name

        best_id = None
        best_name = None
        best_score = 0
        label_tokens = set(normalized_label.split())
        primary_token = normalized_label.split()[0] if normalized_label else ''

        for cat_id, name in categories:
            norm_name = cls._normalize(name)
            name_tokens = set(norm_name.split())
            overlap = len(label_tokens & name_tokens)
            if overlap == 0:
                continue
            if primary_token and primary_token not in norm_name:
                continue
            if overlap > best_score:
                best_score = overlap
                best_id = cat_id
                best_name = name

        if best_score > 0 and best_id is not None:
            return best_id, best_name

        lookup = {cls._normalize(name): (cat_id, name) for cat_id, name in categories}
        matches = get_close_matches(normalized_label, lookup.keys(), n=1, cutoff=0.55)
        if matches:
            return lookup[matches[0]]

        return None

    @classmethod
    def generate_seed_keywords(cls, label: str) -> str:
        """Dérive des mots-clés de départ à partir du nom du domaine."""
        clean = re.sub(r'[()&/]', ',', label)
        parts = [part.strip() for part in re.split(r'[,;]', clean) if part.strip()]
        seeds: list[str] = []

        for part in parts:
            words = [
                word.lower()
                for word in re.findall(r'[\wÀ-ÿ]+', part, flags=re.UNICODE)
                if len(word) > 2
            ]
            if words:
                seeds.append(words[0])

        if not seeds:
            words = [
                word.lower()
                for word in re.findall(r'[\wÀ-ÿ]+', label, flags=re.UNICODE)
                if len(word) > 2
            ]
            seeds = words[:3] or [label.strip().lower()]

        unique_seeds: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            if seed not in seen:
                seen.add(seed)
                unique_seeds.append(seed)

        return ', '.join(unique_seeds)

    @classmethod
    @lru_cache(maxsize=1)
    def _get_flat_categories(cls) -> tuple[tuple[int, str], ...]:
        try:
            pytrends = TrendReq(hl='fr-FR', tz=0)
            tree = pytrends.categories()
            flat: list[tuple[int, str]] = []
            cls._flatten_tree(tree, flat)
            return tuple(flat)
        except Exception as exc:
            logger.exception('Impossible de charger les catégories Google Trends : %s', exc)
            return tuple()

    @classmethod
    def _flatten_tree(cls, node, output: list[tuple[int, str]]) -> None:
        if isinstance(node, dict):
            if 'id' in node and 'name' in node:
                output.append((int(node['id']), str(node['name'])))
            children = node.get('children')
            if children:
                cls._flatten_tree(children, output)
        elif isinstance(node, list):
            for child in node:
                cls._flatten_tree(child, output)

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize('NFKD', text)
        normalized = normalized.encode('ascii', 'ignore').decode('ascii')
        normalized = normalized.lower()
        normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
        return ' '.join(normalized.split())
