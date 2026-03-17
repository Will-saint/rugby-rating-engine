"""
Client HTTP robuste pour les scrapers Rugby Rating Engine.

Fonctionnalités :
- Cache disque par URL (raw/html_cache/) — évite de re-scraper
- Retry avec backoff exponentiel
- Logs structurés avec timestamp
- Sauvegarde snapshot HTML brut pour debug
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent.parent / "raw" / "html_cache"
CACHE_TTL_HOURS = 24  # Revalider le cache après 24h

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Backoff : (base_delay, max_delay, max_retries)
BACKOFF_SETTINGS = {
    "base_delay": 2.0,
    "max_delay": 60.0,
    "max_retries": 4,
}


# ---------------------------------------------------------------------------
# Cache disque
# ---------------------------------------------------------------------------

def _cache_key(url: str, params: dict | None = None) -> str:
    """Hash SHA256 court de l'URL+params pour le nom de fichier cache."""
    full = url + (json.dumps(params, sort_keys=True) if params else "")
    return hashlib.sha256(full.encode()).hexdigest()[:16]


def _cache_path(url: str, params: dict | None = None) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_cache_key(url, params)}.html"


def _is_cache_valid(cache_file: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not cache_file.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    return age < timedelta(hours=ttl_hours)


def _read_cache(cache_file: Path) -> str | None:
    try:
        return cache_file.read_text(encoding="utf-8")
    except Exception:
        return None


def _write_cache(cache_file: Path, content: str):
    try:
        cache_file.write_text(content, encoding="utf-8")
    except Exception as e:
        logging.warning(f"Écriture cache échouée : {e}")


# ---------------------------------------------------------------------------
# Session robuste
# ---------------------------------------------------------------------------

class RobustSession:
    """
    Session HTTP avec cache disque, retry+backoff, et logging structuré.
    """

    def __init__(
        self,
        source_name: str = "scraper",
        request_delay: float = 2.0,
        cache_ttl_hours: int = CACHE_TTL_HOURS,
        extra_headers: dict | None = None,
    ):
        self.logger = logging.getLogger(source_name)
        self.request_delay = request_delay
        self.cache_ttl = cache_ttl_hours
        self._last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if extra_headers:
            self.session.headers.update(extra_headers)

        self._stats = {"hits": 0, "misses": 0, "errors": 0, "cached": 0}

    def get(
        self,
        url: str,
        params: dict | None = None,
        force_refresh: bool = False,
        snapshot_name: str | None = None,
        timeout: int = 20,
    ) -> str | None:
        """
        GET avec cache disque + retry.
        Retourne le contenu HTML (str) ou None en cas d'échec définitif.

        force_refresh=True : ignore le cache même valide.
        snapshot_name : si fourni, sauvegarde aussi dans raw/snapshots/{name}.html
        """
        cache_file = _cache_path(url, params)

        # Vérifier cache
        if not force_refresh and _is_cache_valid(cache_file, self.cache_ttl):
            content = _read_cache(cache_file)
            if content:
                self._stats["cached"] += 1
                self.logger.debug(f"[CACHE] {url}")
                return content

        # Respecter le délai entre requêtes
        now = time.monotonic()
        wait = self.request_delay - (now - self._last_request_time)
        if wait > 0:
            time.sleep(wait)

        # Retry avec backoff exponentiel
        base = BACKOFF_SETTINGS["base_delay"]
        max_d = BACKOFF_SETTINGS["max_delay"]
        max_r = BACKOFF_SETTINGS["max_retries"]

        for attempt in range(max_r):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                self._last_request_time = time.monotonic()

                if resp.status_code == 200:
                    content = resp.text
                    _write_cache(cache_file, content)
                    self._stats["hits"] += 1
                    self.logger.info(f"[OK] {url[:80]}")

                    # Snapshot optionnel
                    if snapshot_name:
                        snap_dir = CACHE_DIR.parent / "snapshots"
                        snap_dir.mkdir(parents=True, exist_ok=True)
                        (snap_dir / f"{snapshot_name}.html").write_text(
                            content, encoding="utf-8"
                        )
                    return content

                elif resp.status_code == 429:
                    wait_t = min(base * (2 ** attempt) * 5, max_d)
                    self.logger.warning(f"[429] Rate limit — attente {wait_t:.0f}s : {url[:60]}")
                    time.sleep(wait_t)

                elif resp.status_code in (403, 406, 410):
                    self.logger.error(f"[{resp.status_code}] Accès refusé : {url[:80]}")
                    self._stats["errors"] += 1
                    return None

                elif resp.status_code == 404:
                    self.logger.warning(f"[404] Non trouvé : {url[:80]}")
                    self._stats["misses"] += 1
                    return None

                else:
                    wait_t = min(base * (2 ** attempt), max_d)
                    self.logger.warning(
                        f"[{resp.status_code}] Tentative {attempt + 1}/{max_r} — "
                        f"attente {wait_t:.0f}s : {url[:60]}"
                    )
                    time.sleep(wait_t)

            except requests.Timeout:
                wait_t = min(base * (2 ** attempt), max_d)
                self.logger.warning(f"[TIMEOUT] Tentative {attempt + 1}/{max_r} — {url[:60]}")
                time.sleep(wait_t)

            except requests.ConnectionError as e:
                wait_t = min(base * (2 ** attempt) * 2, max_d)
                self.logger.warning(f"[CONNECTION] {e} — attente {wait_t:.0f}s")
                time.sleep(wait_t)

            except Exception as e:
                self.logger.error(f"[ERR] {e} : {url[:60]}")
                self._stats["errors"] += 1
                return None

        self.logger.error(f"[FAIL] Toutes tentatives épuisées : {url[:80]}")
        self._stats["errors"] += 1
        return None

    def stats_summary(self) -> str:
        s = self._stats
        total = s["hits"] + s["misses"] + s["errors"] + s["cached"]
        return (
            f"Requêtes: {total} total | "
            f"{s['cached']} en cache | "
            f"{s['hits']} OK | "
            f"{s['misses']} 404 | "
            f"{s['errors']} erreurs"
        )

    def clear_cache(self, url: str | None = None, params: dict | None = None):
        """Vide le cache pour une URL ou tout le cache."""
        if url:
            p = _cache_path(url, params)
            if p.exists():
                p.unlink()
                self.logger.info(f"Cache supprimé : {url[:60]}")
        else:
            for f in CACHE_DIR.glob("*.html"):
                f.unlink()
            self.logger.info("Cache complet supprimé")
