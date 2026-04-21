"""
Surveillance des nouvelles annonces sur lacartedescolocs.fr
-----------------------------------------------------------
Usage:
  python monitor.py --discover       Affiche les filtres et annonces disponibles
  python monitor.py --preview-json   Sortie JSON des annonces actuelles (GUI)
  python monitor.py                  Mode surveillance (compare + alerte si nouvelles)
"""

import sys
import json
import io
import time
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from bs4 import BeautifulSoup

# Forcer UTF-8 sur Windows pour les print()
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
CONFIG_FILE  = DATA_DIR / "config.json"
SEEN_FILE    = DATA_DIR / "seen_listings.json"
HISTORY_FILE = DATA_DIR / "alert_history.json"

BASE_URL     = "https://www.lacartedescolocs.fr"
API_URL      = f"{BASE_URL}/listing_search/list_results"
DEFAULT_URL  = "https://www.lacartedescolocs.fr/logements/fr/ile-de-france/paris"

DEFAULT_FILTERS = {
    "offset":   0,
    "sortBy":   "published_at DESC",
    "currency": "EUR",
}

PAGE_SIZE = 30
MAX_PAGES = 4   # max 120 annonces par vérification

# ── Réseau ────────────────────────────────────────────────────────────────────

def get_page_context(url: str) -> dict:
    resp = requests.get(url, impersonate="chrome", timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    page_data = soup.find(id="page_data")
    if not page_data:
        raise RuntimeError(
            "Impossible de trouver #page_data dans la page. "
            "L'URL est-elle valide ? (ex: .../logements/fr/ile-de-france/paris)"
        )
    vp_full   = json.loads(page_data.get("data-viewport-json", "{}"))
    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    return {
        "viewport": _trim_viewport(vp_full),
        "csrf":     csrf_meta["content"] if csrf_meta else "",
        "cookies":  resp.cookies,
    }


def _trim_viewport(vp: dict) -> dict:
    keys = [
        "canonical_path", "district", "city", "county",
        "administrative", "postal_code", "country_code",
        "sw_lat", "sw_lon", "ne_lat", "ne_lon", "bounds",
    ]
    return {k: vp.get(k) for k in keys}


def fetch_listings(ctx: dict, extra_filters: dict | None = None) -> tuple[list, int]:
    """Une page d'annonces (30 max)."""
    filters = {**DEFAULT_FILTERS, **(extra_filters or {})}
    payload = {
        "listing_search": {
            "viewport":                ctx["viewport"],
            "filters":                 filters,
            "company_name_normalized": None,
        }
    }
    headers = {
        "Content-Type":     "application/json",
        "Accept":           "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token":     ctx["csrf"],
        "Referer":          BASE_URL,
        "Origin":           BASE_URL,
    }
    resp = requests.post(
        API_URL,
        impersonate="chrome",
        headers=headers,
        json=payload,
        cookies=ctx["cookies"],
        timeout=25,
    )
    resp.raise_for_status()
    data = resp.json()
    return json.loads(data.get("results", "[]")), data.get("results_count", 0)


def fetch_with_retry(fn, *args, retries: int = 3, label: str = "",
                     silent: bool = False, **kwargs):
    """Appelle fn avec jusqu'à `retries` tentatives et backoff exponentiel."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt   # 1s, 2s
            if not silent:
                print(f"  [Retry {attempt + 1}/{retries - 1}]"
                      f"{' ' + label if label else ''}: {exc} — attente {wait}s…")
            time.sleep(wait)


def fetch_all_listings(ctx: dict, extra_filters: dict | None = None,
                       silent: bool = False) -> tuple[list, int]:
    """Récupère toutes les annonces via pagination (cap MAX_PAGES)."""
    all_listings: list = []
    total = 0

    for page in range(MAX_PAGES):
        offset       = page * PAGE_SIZE
        page_filters = {**(extra_filters or {}), "offset": offset}
        page_data, total = fetch_with_retry(
            fetch_listings, ctx, page_filters,
            label=f"page {page + 1}", silent=silent,
        )
        if not page_data:
            break
        all_listings.extend(page_data)
        if len(all_listings) >= total or len(page_data) < PAGE_SIZE:
            break

    return all_listings, total


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print("[ERREUR] config.json introuvable. Lance d'abord : python monitor.py --discover")
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def create_default_config(url: str):
    if CONFIG_FILE.exists():
        return
    DATA_DIR.mkdir(exist_ok=True)
    default = {
        "urls":                  [url],
        "extra_filters":         {},
        "desktop_notifications": True,
        "ntfy_topic":            "",
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default, f, indent=2, ensure_ascii=False)


def get_urls(config: dict) -> list[str]:
    """Retourne la liste des URLs configurées. Compatible avec l'ancienne clé 'url'."""
    urls = config.get("urls")
    if isinstance(urls, list):
        return [u for u in urls if u]
    url = config.get("url", DEFAULT_URL)
    return [url] if url else [DEFAULT_URL]


# ── Cache seen_listings ───────────────────────────────────────────────────────

def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    with open(SEEN_FILE, encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


# ── Historique ────────────────────────────────────────────────────────────────

def save_history(new_listings: list):
    history: list = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    entry = {
        "timestamp": datetime.now().isoformat(),
        "count":     len(new_listings),
        "listings": [
            {
                "id":    l["id"],
                "title": l.get("main_title") or l.get("lodging_type_string", ""),
                "rent":  l.get("cost_total_rent"),
                "city":  l.get("address_city", ""),
                "url":   listing_url(l),
            }
            for l in new_listings
        ],
    }
    history.insert(0, entry)
    history = history[:100]
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Notification bureau Windows ───────────────────────────────────────────────

def windows_toast(title: str, message: str):
    """Notification ballon Windows via PowerShell (zéro dépendance)."""
    if sys.platform != "win32":
        return
    title   = title.replace('"', "'")
    message = message.replace('"', "'")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        f'$n.ShowBalloonTip(8000,"{title}","{message}",[System.Windows.Forms.ToolTipIcon]::Info);'
        "Start-Sleep 9;$n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=0x08000000,   # CREATE_NO_WINDOW
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ── Notification push téléphone (ntfy.sh) ────────────────────────────────────

def send_ntfy(topic: str, title: str, message: str, click_url: str = ""):
    if not topic or not topic.strip():
        return
    headers = {
        "Title":    title,
        "Priority": "high",
        "Tags":     "house",
    }
    if click_url:
        headers["Click"]   = click_url
        headers["Actions"] = f"view, Voir l'annonce, {click_url}"
    try:
        requests.post(
            f"https://ntfy.sh/{topic.strip()}",
            data=message.encode("utf-8"),
            headers=headers,
            impersonate="chrome",
            timeout=10,
        )
    except Exception as e:
        print(f"  [ntfy] Erreur : {e}")


# ── URL annonce ───────────────────────────────────────────────────────────────

def listing_url(l: dict) -> str:
    return BASE_URL + l.get("relative_url", "")


# ── Modes ─────────────────────────────────────────────────────────────────────

def mode_discover():
    print("=" * 60)
    print("  DECOUVERTE --- lacartedescolocs.fr")
    print("=" * 60)

    url = DEFAULT_URL
    if CONFIG_FILE.exists():
        try:
            cfg  = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            urls = get_urls(cfg)
            url  = urls[0] if urls else DEFAULT_URL
        except Exception:
            pass

    print(f"\nURL : {url}")
    print("Chargement…")

    try:
        ctx = fetch_with_retry(get_page_context, url, label="chargement page")
    except Exception as e:
        print(f"\n[ERREUR] Impossible de charger la page : {e}")
        sys.exit(1)

    try:
        listings, total = fetch_all_listings(ctx)
    except Exception as e:
        print(f"\n[ERREUR] API : {e}")
        sys.exit(1)

    print(f"\n--- {len(listings)} annonces chargées (total site : {total}) ---")
    for l in listings[:5]:
        rent   = f"{l['cost_total_rent']} EUR/mois" if l.get("cost_total_rent") else "—"
        title  = l.get("main_title") or l.get("lodging_type_string") or "?"
        city   = l.get("address_city", "")
        street = l.get("address_street", "")
        publi  = l.get("published_at_string", "")
        print(f"\n  Titre  : {title}")
        print(f"  Loyer  : {rent}")
        print(f"  Adresse: {street}, {city}")
        print(f"  Date   : {publi}")
        print(f"  URL    : {listing_url(l)}")

    print("\n--- Filtres disponibles dans extra_filters (config.json) ---")
    print()
    print("  PRIX")
    print("    rent_min: 400              loyer minimum (EUR)")
    print("    rent_max: 800              loyer maximum (EUR, max 2000)")
    print()
    print("  SURFACE")
    print("    lodging_surface_min: 30    surface totale min (m²)")
    print("    lodging_surface_max: 150   surface totale max (m², max 500)")
    print("    room_surface_min: 9        surface de la chambre min (m²)")
    print("    room_surface_max: 25       surface de la chambre max (m², max 40)")
    print()
    print("  TYPE D'ANNONCE  (false = exclure)")
    print("    listing_type_flatshare: false    colocations")
    print("    listing_type_rental: false       locations entieres")
    print("    listing_type_coliving: false     colivings")
    print("    listing_type_homestay: false     chambres chez l'habitant")
    print("    listing_type_sublet: false       sous-locations")
    print("    listing_type_student_residence: false  residences etudiantes")
    print("    listing_type_student_room: false       chambres etudiantes")
    print()
    print("  TYPE DE LOGEMENT  (false = exclure)")
    print("    lodging_type_flat: false         appartement")
    print("    lodging_type_house: false        maison")
    print("    lodging_type_studio: false       studio")
    print("    lodging_type_duplex: false       duplex")
    print("    lodging_type_loft: false         loft")
    print("    lodging_type_villa: false        villa")
    print("    lodging_type_residence: false    residence")
    print("    lodging_type_mansion: false      manoir/hotel particulier")
    print("    lodging_type_building: false     immeuble entier")
    print("    lodging_type_chalet: false       chalet")
    print("    lodging_type_cabin: false        cabane")
    print("    lodging_type_farm: false         ferme")
    print("    lodging_type_castle: false       chateau")
    print("    lodging_type_houseboat: false    peniche")
    print()
    print("  NOMBRE DE PIECES  (false = exclure)")
    print("    lodging_size_f1: false    1 piece (studio)")
    print("    lodging_size_f2: false    2 pieces")
    print("    lodging_size_f3: false    3 pieces")
    print("    lodging_size_f4: false    4 pieces")
    print("    lodging_size_f5: false    5 pieces")
    print("    lodging_size_f6: false    6 pieces")
    print("    lodging_size_f7: false    7 pieces")
    print("    lodging_size_f8: false    8 pieces et plus")
    print()
    print("  NOMBRE DE COLOCATAIRES  (false = exclure)")
    print("    housemates_h0: false    sans colocataire")
    print("    housemates_h1: false    1 colocataire")
    print("    housemates_h2: false    2 colocataires")
    print("    housemates_h3: false    3 colocataires")
    print("    housemates_h4: false    4 colocataires")
    print("    housemates_h5: false    5 colocataires")
    print("    housemates_h6: false    6 colocataires")
    print("    housemates_h7: false    7 colocataires et plus")
    print()
    print("  EQUIPEMENTS  (true = exiger, absent = indifferent)")
    print("    commodities_furnished: true        meuble")
    print("    commodities_wifi: true             wifi inclus")
    print("    commodities_washing_machine: true  machine a laver")
    print("    commodities_parking: true          parking")
    print("    commodities_garage: true           garage")
    print("    commodities_elevator: true         ascenseur")
    print("    commodities_dishwasher: true       lave-vaisselle")
    print("    commodities_air_conditioning: true climatisation")
    print("    commodities_balcony: true          balcon")
    print("    commodities_garden: true           jardin")
    print("    commodities_pool: true             piscine")
    print("    commodities_disabled_friendly: true  acces handicapes")
    print()
    print("  REGLES  (true = exiger, absent = indifferent)")
    print("    particular_rules_pets_allowed: true      animaux acceptes")
    print("    particular_rules_smokers_allowed: true   fumeurs acceptes")
    print("    particular_rules_only_women_allowed: true  femmes uniquement")
    print("    particular_rules_only_men_allowed: true    hommes uniquement")
    print()
    print("  DATE / DISPONIBILITE")
    print("    date_min: -7               publiees dans les 7 derniers jours (min -60)")
    print("    availability_start: '2026-06-01'  disponible a partir de cette date")

    create_default_config(url)
    bat_path = (BASE_DIR / "run.bat").resolve()
    print(f"\n--- Planification Windows (toutes les 10 min) ---")
    print(f'  schtasks /create /tn "ColocMonitor" /tr "{bat_path}" /sc minute /mo 10 /f')
    print()


def mode_preview_json():
    """Sortie JSON des annonces actuelles — utilisé par la GUI (onglet Annonces).
    Aucune sortie texte sur stdout sauf le JSON final sur une seule ligne."""
    try:
        config        = load_config()
        urls          = get_urls(config)
        extra_filters = config.get("extra_filters", {})

        seen          = load_seen()
        all_listings: list = []
        total_sum     = 0
        seen_ids: set = set()

        for url in urls:
            ctx             = fetch_with_retry(get_page_context, url, silent=True)
            listings, total = fetch_all_listings(ctx, extra_filters, silent=True)
            total_sum      += total
            for l in listings:
                lid = str(l["id"])
                if lid not in seen_ids:
                    seen_ids.add(lid)
                    l["_is_new"] = lid not in seen
                    all_listings.append(l)

        def _date_key(l):
            pub = l.get("published_at")
            return pub if isinstance(pub, str) and pub else str(l.get("id", 0)).zfill(20)

        all_listings.sort(key=_date_key, reverse=True)
        all_listings.sort(key=lambda l: 0 if l.get("_is_new") else 1)

        result = {
            "ok":         True,
            "listings":   all_listings,
            "total":      total_sum,
            "seen_count": len(seen),
        }
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}

    payload = json.dumps(result, ensure_ascii=False)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write((payload + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()



def mode_monitor():
    config        = load_config()
    urls          = get_urls(config)
    extra_filters = config.get("extra_filters", {})
    do_toast      = config.get("desktop_notifications", True)
    ntfy_topic    = config.get("ntfy_topic", "")

    ts               = datetime.now().strftime("%Y-%m-%d %H:%M")
    seen             = load_seen()
    all_new_listings: list = []
    all_current_ids:  set  = set()

    url_overrides = config.get("url_overrides", {})

    for url in urls:
        url_filters = {**extra_filters}
        for key, overrides in url_overrides.items():
            if key in url:
                url_filters.update(overrides)

        print(f"[{ts}] Vérification : {url}")
        try:
            ctx = fetch_with_retry(get_page_context, url, label="chargement page")
        except Exception as e:
            print(f"  [ERREUR] Chargement impossible : {e}")
            continue

        try:
            listings, total = fetch_all_listings(ctx, url_filters)
        except Exception as e:
            print(f"  [ERREUR] API inaccessible : {e}")
            continue

        if not listings:
            print("  Aucune annonce reçue (API vide).")
            continue

        current_ids   = {str(l["id"]) for l in listings}
        all_current_ids |= current_ids
        new_listings  = [l for l in listings if str(l["id"]) not in seen]

        if new_listings:
            print(f"  {len(new_listings)} nouvelle(s) annonce(s) détectée(s) !")
            for l in new_listings:
                rent = f"{l['cost_total_rent']} EUR/mois" if l.get("cost_total_rent") else "—"
                print(f"    - {l.get('main_title', '?')} | {rent} | {listing_url(l)}")
            all_new_listings.extend(new_listings)
        else:
            print(f"  Aucune nouvelle annonce ({len(listings)}/{total} en ligne).")

    if all_new_listings:
        ref_url = urls[0] if urls else DEFAULT_URL

        save_history(all_new_listings)

        if do_toast:
            windows_toast(
                "Coloc Monitor — Nouvelles annonces",
                f"{len(all_new_listings)} nouvelle(s) annonce(s) sur lacartedescolocs.fr",
            )

        for l in all_new_listings:
            click_url = listing_url(l)
            rent      = f"{l['cost_total_rent']} €/mois" if l.get("cost_total_rent") else ""
            city       = l.get("address_city", "")
            ntfy_title = f"Colocalert - {city}" if city else "Colocalert"
            ntfy_body  = l.get("main_title") or l.get("lodging_type_string") or "Nouvelle annonce"
            if rent:
                ntfy_body += f" — {rent}"
            send_ntfy(ntfy_topic, ntfy_title, ntfy_body, click_url)

    save_seen(seen | all_current_ids)


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--discover":
        mode_discover()
    elif arg == "--preview-json":
        mode_preview_json()
    else:
        mode_monitor()
