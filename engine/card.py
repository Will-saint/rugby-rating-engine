"""
Génère la carte FIFA-style d'un joueur (image PNG via matplotlib).
Photo : si data/photos/{name}.jpg existe, affichée. Sinon : avatar initiales coloré.
"""

import io
import os
import hashlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Ellipse
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTOS_DIR = os.path.join(ROOT, "data", "photos")
LNR_PHOTO_HASH = "b5e9990d9a31ede8327da9bafe6aeb896ea144f3"


def _build_lnr_photo_url(player: dict) -> str | None:
    lnr_id = player.get("lnr_id")
    lnr_slug = player.get("lnr_slug")
    if not lnr_id or not lnr_slug or str(lnr_id) == "nan":
        return None
    try:
        return (
            f"https://cdn.lnr.fr/joueur/{int(float(lnr_id))}-{lnr_slug}"
            f"/photo/photoFull.{LNR_PHOTO_HASH}"
        )
    except Exception:
        return None

# Tiers par rating
CARD_TIERS = [
    (90, "#0D0800", "#FFD700", "#FFF0A0", "LEGENDAIRE"),
    (84, "#080F20", "#C8A840", "#EAD890", "OR"),
    (77, "#080E08", "#3A7A28", "#70B860", "ARGENT"),
    (70, "#120808", "#8C4020", "#C87040", "BRONZE"),
    (0,  "#141414", "#585858", "#989898", "STANDARD"),
]

FLAGS = {
    "France": "FRA", "New Zealand": "NZL", "Australia": "AUS",
    "South Africa": "RSA", "England": "ENG", "Ireland": "IRL",
    "Scotland": "SCO", "Wales": "WAL", "Argentina": "ARG",
    "Fiji": "FIJ", "Samoa": "SAM", "Tonga": "TGA",
    "Italy": "ITA", "Japan": "JPN", "Georgia": "GEO",
    "Uruguay": "URU", "Portugal": "POR", "Namibia": "NAM",
}

TEAM_COLORS = {
    "Stade Toulousain":  "#8B0000",
    "Bordeaux-Begles":   "#003366",
    "Stade Rochelais":   "#B8860B",
    "Racing 92":         "#4169E1",
    "ASM Clermont":      "#6B6B00",
    "Stade Francais":    "#CC0066",
    "RC Toulon":         "#CC0000",
    "LOU Rugby":         "#8B1A1A",
    "Castres Olympique": "#2F6B3D",
    "Montpellier HRC":   "#003087",
    "USAP Perpignan":    "#C8102E",
    "Aviron Bayonnais":  "#006400",
    "CA Brive":          "#8B4513",
    "Section Paloise":   "#228B22",
}

# Étiquettes rugby pour les 6 axes (sur la carte)
CARD_AXIS_LABELS = ["CARRY", "DEF", "DISC", "BRKD", "KICK", "SETP"]
CARD_AXIS_KEYS   = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]


def _get_tier(rating: int):
    for min_r, bg, accent, stat_col, name in CARD_TIERS:
        if rating >= min_r:
            return bg, accent, stat_col, name
    return CARD_TIERS[-1][1], CARD_TIERS[-1][2], CARD_TIERS[-1][3], CARD_TIERS[-1][4]


def render_card(player: dict, dpi: int = 180) -> bytes:
    """Retourne les bytes PNG de la carte joueur."""
    rating = int(player.get("rating", 70))
    bg, accent, stat_col, tier = _get_tier(rating)

    fig, ax = plt.subplots(figsize=(2.5, 3.5), dpi=dpi)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 140)
    ax.axis("off")

    # Bordure avec effet "glow"
    for lw, alpha in [(10, 0.08), (5, 0.25), (2, 0.9)]:
        border = FancyBboxPatch(
            (1.5, 1.5), 97, 137,
            boxstyle="round,pad=2",
            facecolor="none",
            edgecolor=accent,
            linewidth=lw,
            alpha=alpha,
            zorder=1,
        )
        ax.add_patch(border)

    # --- TOP : rating + poste + nationalité ---
    ax.text(19, 127, str(rating), fontsize=28, fontweight="black",
            color=accent, ha="center", va="center", zorder=3)

    pos_abbr = player.get("position_abbr", "?")
    ax.text(19, 117, pos_abbr, fontsize=8, fontweight="bold",
            color=accent, ha="center", va="center", zorder=3)

    nat_code = FLAGS.get(player.get("nationality", ""), "INT")
    ax.text(81, 127, nat_code, fontsize=7.5, fontweight="bold",
            color=accent, ha="center", va="center", zorder=3)

    ax.text(81, 117, tier, fontsize=5, color=accent,
            ha="center", va="center", zorder=3, style="italic", alpha=0.9)

    # Séparateur haut
    ax.plot([5, 95], [109, 109], color=accent, linewidth=0.8, alpha=0.5, zorder=2)

    # --- MILIEU : photo ou avatar initiales ---
    team = player.get("team", "")
    player_name_raw = player.get("name", "")

    # 1. Chercher photo locale dans data/photos/
    photo_path = os.path.join(PHOTOS_DIR, f"{player_name_raw}.jpg")
    photo_loaded = False

    # 2. Si pas locale, essayer CDN LNR via photo_url dans player dict
    if not os.path.exists(photo_path):
        photo_url = player.get("photo_url") or _build_lnr_photo_url(player)
        if photo_url:
            try:
                import requests as _req
                from io import BytesIO
                r = _req.get(photo_url, timeout=4)
                if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                    os.makedirs(PHOTOS_DIR, exist_ok=True)
                    with open(photo_path, "wb") as _f:
                        _f.write(r.content)
            except Exception:
                pass

    if os.path.exists(photo_path):
        try:
            from PIL import Image
            img = Image.open(photo_path).convert("RGBA")
            # Rogner en cercle
            img = img.resize((140, 140))
            img_arr = np.array(img)
            ax_img = fig.add_axes([0.27, 0.55, 0.46, 0.26], anchor="C")
            ax_img.imshow(img_arr)
            ax_img.axis("off")
            photo_loaded = True
        except Exception:
            pass

    if not photo_loaded:
        # Avatar initiales coloré avec couleur de l'équipe
        team_color = TEAM_COLORS.get(team, "#444444")
        circle = plt.Circle((50, 90), 15, color=team_color, alpha=0.85, zorder=2)
        ax.add_patch(circle)
        # Anneau accent
        ring = plt.Circle((50, 90), 15, color=accent, alpha=0.5, fill=False, linewidth=1.5, zorder=3)
        ax.add_patch(ring)
        initials = "".join(w[0].upper() for w in player_name_raw.split()[:2] if w)
        ax.text(50, 90, initials, fontsize=13, fontweight="black",
                color="white", ha="center", va="center", zorder=4)

    display_name = player_name_raw.upper()
    if len(display_name) > 18:
        display_name = display_name[:17] + "."
    ax.text(50, 74, display_name, fontsize=9.5, fontweight="black",
            color="white", ha="center", va="center", zorder=3)

    ax.text(50, 65, team.upper(), fontsize=6.5, color=stat_col,
            ha="center", va="center", zorder=3, style="italic")

    # Séparateur bas
    ax.plot([5, 95], [59, 59], color=accent, linewidth=0.8, alpha=0.5, zorder=2)

    # --- BAS : 6 stats (étiquettes rugby) ---
    stats = list(zip(CARD_AXIS_LABELS, [int(player.get(k, 50)) for k in CARD_AXIS_KEYS]))

    y_rows = [47, 33, 19]
    for i, (label, val) in enumerate(stats):
        row = i // 2
        col = i % 2
        x_base = 26 if col == 0 else 74
        y = y_rows[row]

        # Barre de fond
        bar_w = 28
        bar_h = 4.5
        bar_fill = (val / 100) * bar_w
        ax.add_patch(FancyBboxPatch(
            (x_base - 2, y - 7), bar_w, bar_h,
            boxstyle="round,pad=0.5", facecolor=accent, alpha=0.12, zorder=2,
        ))
        if bar_fill > 0:
            ax.add_patch(FancyBboxPatch(
                (x_base - 2, y - 7), bar_fill, bar_h,
                boxstyle="round,pad=0.5", facecolor=accent, alpha=0.55, zorder=2,
            ))

        ax.text(x_base - 2, y, str(val), fontsize=10, fontweight="bold",
                color="white", ha="left", va="center", zorder=3)
        ax.text(x_base + 13, y, label, fontsize=6.5, color=stat_col,
                ha="left", va="center", zorder=3)

    # Séparateur vertical entre colonnes stats
    ax.plot([50, 50], [10, 57], color=accent, linewidth=0.4, alpha=0.35, zorder=2)

    plt.tight_layout(pad=0.15)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=bg, dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
