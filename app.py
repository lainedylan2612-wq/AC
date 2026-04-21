"""
Interface graphique — Coloc Monitor v2
"""

import sys
import json
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime

BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
CONFIG_FILE  = DATA_DIR / "config.json"
SEEN_FILE    = DATA_DIR / "seen_listings.json"
HISTORY_FILE = DATA_DIR / "alert_history.json"
LOG_FILE     = DATA_DIR / "monitor.log"
SCRIPT       = BASE_DIR / "monitor.py"

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":      "#f1f5f9",
    "card":    "#ffffff",
    "border":  "#e2e8f0",
    "header":  "#1d4ed8",
    "text":    "#0f172a",
    "label":   "#475569",
    "muted":   "#94a3b8",
    "input":   "#f8fafc",
    "blue":    "#2563eb",
    "green":   "#059669",
    "purple":  "#7c3aed",
    "dark":    "#1e293b",
    "red":     "#dc2626",
    "amber":   "#d97706",
    "gray":    "#f1f5f9",
    "gray_fg": "#334155",
    "log_bg":  "#0f172a",
    "log_fg":  "#e2e8f0",
    "row_new": "#fefce8",
    "row_new_fg": "#854d0e",
}

# ── Définition des filtres ────────────────────────────────────────────────────

LISTING_TYPES = [
    ("listing_type_flatshare",         "Colocation"),
    ("listing_type_rental",            "Location entière"),
    ("listing_type_coliving",          "Coliving"),
    ("listing_type_homestay",          "Chambre chez l'habitant"),
    ("listing_type_sublet",            "Sous-location"),
    ("listing_type_student_residence", "Résidence étudiante"),
    ("listing_type_student_room",      "Chambre étudiante"),
]

LODGING_TYPES = [
    ("lodging_type_flat",      "Appartement"),
    ("lodging_type_house",     "Maison"),
    ("lodging_type_studio",    "Studio"),
    ("lodging_type_duplex",    "Duplex"),
    ("lodging_type_loft",      "Loft"),
    ("lodging_type_villa",     "Villa"),
    ("lodging_type_residence", "Résidence"),
    ("lodging_type_mansion",   "Hôtel particulier"),
    ("lodging_type_building",  "Immeuble entier"),
    ("lodging_type_chalet",    "Chalet"),
    ("lodging_type_cabin",     "Cabane"),
    ("lodging_type_farm",      "Ferme"),
    ("lodging_type_castle",    "Château"),
    ("lodging_type_houseboat", "Péniche"),
]

ROOM_SIZES = [
    ("lodging_size_f1", "Studio (F1)"),
    ("lodging_size_f2", "F2"),
    ("lodging_size_f3", "F3"),
    ("lodging_size_f4", "F4"),
    ("lodging_size_f5", "F5"),
    ("lodging_size_f6", "F6"),
    ("lodging_size_f7", "F7"),
    ("lodging_size_f8", "F8+"),
]

HOUSEMATES = [
    ("housemates_h0", "Seul"),
    ("housemates_h1", "1 coloc"),
    ("housemates_h2", "2 colocs"),
    ("housemates_h3", "3 colocs"),
    ("housemates_h4", "4 colocs"),
    ("housemates_h5", "5 colocs"),
    ("housemates_h6", "6 colocs"),
    ("housemates_h7", "7+"),
]

COMMODITIES = [
    ("commodities_furnished",        "Meublé"),
    ("commodities_wifi",             "Wifi inclus"),
    ("commodities_washing_machine",  "Lave-linge"),
    ("commodities_parking",          "Parking"),
    ("commodities_garage",           "Garage"),
    ("commodities_elevator",         "Ascenseur"),
    ("commodities_dishwasher",       "Lave-vaisselle"),
    ("commodities_air_conditioning", "Climatisation"),
    ("commodities_balcony",          "Balcon"),
    ("commodities_garden",           "Jardin"),
    ("commodities_pool",             "Piscine"),
    ("commodities_disabled_friendly","Accès PMR"),
]

RULES = [
    ("particular_rules_pets_allowed",       "Animaux acceptés"),
    ("particular_rules_smokers_allowed",    "Fumeurs acceptés"),
    ("particular_rules_only_women_allowed", "Femmes uniquement"),
    ("particular_rules_only_men_allowed",   "Hommes uniquement"),
]

# ── Frame scrollable ──────────────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg="white", **kw):
        super().__init__(parent, bg=bg, **kw)
        self._canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        sb = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self.inner.bind("<Configure>", self._on_inner)
        self._win = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._canvas.bind("<Configure>", self._on_canvas)
        self._canvas.bind("<Enter>", lambda _: self._canvas.bind_all("<MouseWheel>", self._scroll))
        self._canvas.bind("<Leave>", lambda _: self._canvas.unbind_all("<MouseWheel>"))

    def _on_inner(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _scroll(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


# ── Application ───────────────────────────────────────────────────────────────

class ColocApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Coloc Monitor — lacartedescolocs.fr")
        self.geometry("1150x780")
        self.minsize(920, 620)
        self.configure(bg=C["bg"])

        self.filter_vars: dict[str, tk.Variable] = {}
        self._listing_data: list[dict] = []

        self._build_ui()
        self._load_all()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=10)

        left_outer = tk.Frame(body, bg=C["bg"], width=380)
        left_outer.pack(side="left", fill="y", padx=(0, 8))
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg=C["bg"], width=370,
                                highlightthickness=0, bd=0)
        left_scroll = tk.Scrollbar(left_outer, orient="vertical",
                                   command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)

        left = tk.Frame(left_canvas, bg=C["bg"])
        left_win = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _on_frame_configure(_e):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        def _on_canvas_resize(e):
            left_canvas.itemconfig(left_win, width=e.width)
        def _on_mousewheel(e):
            left_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        left.bind("<Configure>", _on_frame_configure)
        left_canvas.bind("<Configure>", _on_canvas_resize)
        left_canvas.bind("<MouseWheel>", _on_mousewheel)
        left.bind("<MouseWheel>", _on_mousewheel)

        self._build_config_card(left)
        self._build_actions_card(left)
        self._build_scheduler_card(left)

        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)
        self._build_right_tabs(right)

        self.status_var = tk.StringVar(value="Prêt")
        tk.Label(self, textvariable=self.status_var,
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 8),
                 anchor="w", padx=14).pack(side="bottom", fill="x", pady=(0, 4))

    def _build_header(self):
        h = tk.Frame(self, bg=C["header"], height=50)
        h.pack(fill="x")
        h.pack_propagate(False)
        tk.Label(h, text="  Coloc Monitor", bg=C["header"], fg="white",
                 font=("Segoe UI", 14, "bold"), anchor="w").pack(side="left", padx=14)
        tk.Label(h, text="lacartedescolocs.fr  ", bg=C["header"], fg="#93c5fd",
                 font=("Segoe UI", 9)).pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _card(self, parent, title, pady_top=0):
        outer = tk.Frame(parent, bg=C["bg"])
        outer.pack(fill="x", pady=(pady_top, 8))
        inner = tk.Frame(outer, bg=C["card"],
                         highlightbackground=C["border"], highlightthickness=1)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=title, bg=C["card"], fg="#1e3a5f",
                 font=("Segoe UI", 10, "bold"), anchor="w", padx=12, pady=8
                 ).pack(fill="x")
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x")
        content = tk.Frame(inner, bg=C["card"])
        content.pack(fill="both", expand=True, padx=12, pady=10)
        return content

    def _entry_row(self, parent, label, show=None, width=20):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=C["card"], fg=C["label"],
                 font=("Segoe UI", 9), width=width, anchor="w").pack(side="left")
        var = tk.StringVar()
        tk.Entry(row, textvariable=var, show=show,
                 font=("Segoe UI", 9), bd=1, relief="solid",
                 fg=C["text"], bg=C["input"]).pack(side="left", fill="x", expand=True)
        return var

    def _btn(self, parent, text, bg, cmd, side="left", padx=(0, 6), fg="white"):
        b = tk.Button(parent, text=text, bg=bg, fg=fg,
                      font=("Segoe UI", 9, "bold"), bd=0,
                      padx=10, pady=6, cursor="hand2",
                      activebackground=bg, command=cmd)
        b.pack(side=side, padx=padx)
        return b

    def _treeview_style(self):
        s = ttk.Style()
        s.configure("Treeview", font=("Segoe UI", 9), rowheight=28,
                    background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], borderwidth=0)
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                    background=C["bg"], foreground=C["label"], relief="flat")
        s.map("Treeview", background=[("selected", "#dbeafe")],
              foreground=[("selected", C["text"])])

    # ── Carte Configuration ───────────────────────────────────────────────────

    def _build_config_card(self, parent):
        c = self._card(parent, "Configuration")

        # URLs de recherche (multi-villes)
        tk.Label(c, text="URLs de recherche", bg=C["card"], fg=C["label"],
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(4, 2))

        url_list_frame = tk.Frame(c, bg=C["card"])
        url_list_frame.pack(fill="x", pady=(0, 2))
        self.url_listbox = tk.Listbox(url_list_frame, font=("Segoe UI", 8),
                                      height=4, bd=1, relief="solid",
                                      bg=C["input"], fg=C["text"],
                                      selectmode="single", activestyle="none")
        url_sb = tk.Scrollbar(url_list_frame, orient="vertical",
                              command=self.url_listbox.yview)
        self.url_listbox.configure(yscrollcommand=url_sb.set)
        url_sb.pack(side="right", fill="y")
        self.url_listbox.pack(side="left", fill="x", expand=True)

        url_add_row = tk.Frame(c, bg=C["card"])
        url_add_row.pack(fill="x", pady=(2, 4))
        self.v_url_new = tk.StringVar()
        tk.Entry(url_add_row, textvariable=self.v_url_new,
                 font=("Segoe UI", 8), bd=1, relief="solid",
                 fg=C["text"], bg=C["input"]).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(url_add_row, text="Ajouter", bg=C["blue"], fg="white",
                  font=("Segoe UI", 8, "bold"), bd=0, padx=8, pady=3,
                  cursor="hand2", command=self._add_url).pack(side="left", padx=(0, 4))
        tk.Button(url_add_row, text="Supprimer", bg=C["red"], fg="white",
                  font=("Segoe UI", 8, "bold"), bd=0, padx=8, pady=3,
                  cursor="hand2", command=self._remove_url).pack(side="left")

        # Notifications bureau
        notif_row = tk.Frame(c, bg=C["card"])
        notif_row.pack(fill="x", pady=(0, 6))
        self.v_notif = tk.BooleanVar(value=True)
        tk.Checkbutton(notif_row, variable=self.v_notif,
                       bg=C["card"], activebackground=C["card"],
                       selectcolor="#dbeafe", bd=0, cursor="hand2"
                       ).pack(side="left")
        tk.Label(notif_row, text="Notification bureau Windows",
                 bg=C["card"], fg=C["label"], font=("Segoe UI", 9)
                 ).pack(side="left")

        # Notification push téléphone (ntfy.sh)
        ntfy_row = tk.Frame(c, bg=C["card"])
        ntfy_row.pack(fill="x", pady=(0, 4))
        tk.Label(ntfy_row, text="Push téléphone (ntfy.sh) :", bg=C["card"],
                 fg=C["label"], font=("Segoe UI", 9)).pack(side="left")
        lnk2 = tk.Label(ntfy_row, text="ntfy.sh", bg=C["card"], fg=C["blue"],
                        font=("Segoe UI", 8, "underline"), cursor="hand2")
        lnk2.pack(side="right")
        lnk2.bind("<Button-1>", lambda _: webbrowser.open("https://ntfy.sh"))
        self.v_ntfy = tk.StringVar()
        ntfy_entry_row = tk.Frame(c, bg=C["card"])
        ntfy_entry_row.pack(fill="x", pady=(0, 6))
        tk.Entry(ntfy_entry_row, textvariable=self.v_ntfy, bg=C["input"],
                 fg=C["text"], relief="flat", font=("Segoe UI", 9),
                 highlightthickness=1, highlightbackground=C["border"]
                 ).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(ntfy_entry_row, text="Tester", bg=C["gray"], fg=C["blue"],
                  font=("Segoe UI", 8), relief="flat", cursor="hand2",
                  command=self._test_ntfy
                  ).pack(side="left", padx=(4, 0))

        # Cache info + bouton vider
        self._cache_var = tk.StringVar()
        cache_row = tk.Frame(c, bg=C["card"])
        cache_row.pack(fill="x", pady=(0, 8))
        tk.Label(cache_row, textvariable=self._cache_var,
                 bg=C["card"], fg=C["muted"], font=("Segoe UI", 8)
                 ).pack(side="left")
        tk.Button(cache_row, text="Vider le cache", bg=C["gray"], fg=C["amber"],
                  font=("Segoe UI", 8, "bold"), bd=0, padx=8, pady=3,
                  cursor="hand2", command=self._clear_cache
                  ).pack(side="right")

        btn_row = tk.Frame(c, bg=C["card"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Sauvegarder", C["blue"],  self._save_all,  side="right", padx=(6, 0))
        self._btn(btn_row, "Recharger",   C["gray"],  self._load_all,  side="right", padx=(0, 0), fg=C["gray_fg"])

    def _add_url(self):
        url = self.v_url_new.get().strip()
        if not url:
            return
        if url not in self.url_listbox.get(0, tk.END):
            self.url_listbox.insert(tk.END, url)
        self.v_url_new.set("")

    def _remove_url(self):
        sel = self.url_listbox.curselection()
        if sel:
            self.url_listbox.delete(sel[0])

    def _get_urls(self) -> list:
        return list(self.url_listbox.get(0, tk.END))

    def _set_urls(self, urls: list):
        self.url_listbox.delete(0, tk.END)
        for u in urls:
            if u:
                self.url_listbox.insert(tk.END, u)

    def _update_cache_info(self):
        count = 0
        if SEEN_FILE.exists():
            try:
                count = len(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
            except Exception:
                pass
        self._cache_var.set(f"Cache : {count} annonce(s) déjà vue(s)")

    def _clear_cache(self):
        count = 0
        if SEEN_FILE.exists():
            try:
                count = len(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
            except Exception:
                pass
        if not messagebox.askyesno(
            "Vider le cache",
            f"Supprimer les {count} annonces mémorisées ?\n\n"
            "La prochaine vérification considérera toutes les annonces actuelles comme nouvelles."
        ):
            return
        if SEEN_FILE.exists():
            SEEN_FILE.unlink()
        self._update_cache_info()
        self._log("Cache vidé. Prochaine vérification = toutes les annonces actuelles.", "warn")

    # ── Carte Actions ─────────────────────────────────────────────────────────

    def _build_actions_card(self, parent):
        c = self._card(parent, "Actions")

        r1 = tk.Frame(c, bg=C["card"])
        r1.pack(fill="x", pady=(0, 6))
        self._btn(r1, "Vérifier maintenant",  C["blue"],   self._run_monitor)

        r2 = tk.Frame(c, bg=C["card"])
        r2.pack(fill="x")
        self._btn(r2, "Découvrir (filtres + exemples)", C["purple"], self._run_discover)

    # ── Carte Surveillance automatique ────────────────────────────────────────

    def _build_scheduler_card(self, parent):
        c = self._card(parent, "Surveillance automatique")

        # Statut
        status_row = tk.Frame(c, bg=C["card"])
        status_row.pack(fill="x", pady=(0, 8))
        tk.Label(status_row, text="Statut :", bg=C["card"],
                 fg=C["label"], font=("Segoe UI", 9)).pack(side="left")
        self._sched_dot  = tk.Label(status_row, text="●", bg=C["card"],
                                    fg=C["muted"], font=("Segoe UI", 11))
        self._sched_dot.pack(side="left", padx=(6, 2))
        self._sched_status_var = tk.StringVar(value="—")
        tk.Label(status_row, textvariable=self._sched_status_var, bg=C["card"],
                 fg=C["text"], font=("Segoe UI", 9)).pack(side="left")
        tk.Button(status_row, text="↻", bg=C["gray"], fg=C["gray_fg"],
                  font=("Segoe UI", 9, "bold"), bd=0, padx=6, pady=2,
                  cursor="hand2", command=self._refresh_scheduler_status
                  ).pack(side="right")

        # Séparateur
        tk.Frame(c, bg=C["border"], height=1).pack(fill="x", pady=(0, 8))

        # Intervalle
        interval_row = tk.Frame(c, bg=C["card"])
        interval_row.pack(fill="x", pady=(0, 8))
        tk.Label(interval_row, text="Intervalle :", bg=C["card"],
                 fg=C["label"], font=("Segoe UI", 9)).pack(side="left")
        self._sched_interval = tk.StringVar(value="15")
        cb = ttk.Combobox(interval_row, textvariable=self._sched_interval,
                          values=["5", "10", "15", "30", "60"],
                          width=5, state="readonly", font=("Segoe UI", 9))
        cb.pack(side="left", padx=(8, 4))
        tk.Label(interval_row, text="minutes", bg=C["card"],
                 fg=C["label"], font=("Segoe UI", 9)).pack(side="left")

        # Toggle surveillance on/off
        toggle_row = tk.Frame(c, bg=C["card"])
        toggle_row.pack(fill="x", pady=(0, 8))
        tk.Label(toggle_row, text="Surveillance active :", bg=C["card"],
                 fg=C["label"], font=("Segoe UI", 9)).pack(side="left")
        self._sched_toggle_var = tk.BooleanVar(value=False)
        self._sched_toggle_btn = tk.Button(
            toggle_row, text="  OFF  ", bg=C["muted"], fg="white",
            font=("Segoe UI", 9, "bold"), bd=0, padx=10, pady=4,
            cursor="hand2", relief="flat",
            command=self._toggle_scheduler,
        )
        self._sched_toggle_btn.pack(side="left", padx=(8, 0))

        # Séparateur
        tk.Frame(c, bg=C["border"], height=1).pack(fill="x", pady=(0, 8))

        # Installer / Supprimer
        btn_row = tk.Frame(c, bg=C["card"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Installer / Mettre à jour", C["dark"],
                  self._setup_scheduler)
        self._btn(btn_row, "Supprimer", C["red"], self._remove_scheduler, padx=(6, 0))

        self._refresh_scheduler_status()

    # ── Onglets droite ────────────────────────────────────────────────────────

    def _build_right_tabs(self, parent):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TNotebook",     background=C["bg"], borderwidth=0)
        s.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"),
                    padding=[14, 6], background=C["border"], foreground=C["label"])
        s.map("TNotebook.Tab",
              background=[("selected", C["card"])],
              foreground=[("selected", C["blue"])])
        self._treeview_style()

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        for title, builder in [
            ("  Annonces  ",   self._build_annonces_tab),
            ("  Filtres  ",    self._build_filter_tab),
            ("  Historique  ", self._build_historique_tab),
            ("  Journal  ",    self._build_log_tab),
        ]:
            frame = tk.Frame(nb, bg=C["card"])
            nb.add(frame, text=title)
            builder(frame)

    # ── Onglet Annonces ───────────────────────────────────────────────────────

    def _build_annonces_tab(self, parent):
        top = tk.Frame(parent, bg=C["card"])
        top.pack(fill="x", padx=12, pady=(10, 6))

        self._btn(top, "Charger les annonces", C["blue"], self._run_preview)

        self._ann_count_var    = tk.StringVar(value="")
        self._ann_loading_var  = tk.StringVar(value="")
        tk.Label(top, textvariable=self._ann_count_var,
                 bg=C["card"], fg=C["label"], font=("Segoe UI", 9)).pack(side="left", padx=10)
        tk.Label(top, textvariable=self._ann_loading_var,
                 bg=C["card"], fg=C["blue"],  font=("Segoe UI", 9, "italic")).pack(side="left")

        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

        tree_wrap = tk.Frame(parent, bg=C["card"])
        tree_wrap.pack(fill="both", expand=True)

        cols = ("new", "title", "rent", "city", "date")
        self.ann_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings",
                                     selectmode="browse")
        self.ann_tree.heading("new",   text="")
        self.ann_tree.heading("title", text="Titre / Type")
        self.ann_tree.heading("rent",  text="Loyer")
        self.ann_tree.heading("city",  text="Ville")
        self.ann_tree.heading("date",  text="Publié")
        self.ann_tree.column("new",   width=28,  minwidth=28,  stretch=False, anchor="center")
        self.ann_tree.column("title", width=300, minwidth=180, stretch=True)
        self.ann_tree.column("rent",  width=110, minwidth=80,  stretch=False)
        self.ann_tree.column("city",  width=130, minwidth=80,  stretch=False)
        self.ann_tree.column("date",  width=130, minwidth=80,  stretch=False)

        self.ann_tree.tag_configure("new",  background=C["row_new"], foreground=C["row_new_fg"])
        self.ann_tree.tag_configure("seen", background=C["card"],    foreground=C["text"])

        vsb = tk.Scrollbar(tree_wrap, orient="vertical",   command=self.ann_tree.yview)
        hsb = tk.Scrollbar(tree_wrap, orient="horizontal", command=self.ann_tree.xview)
        self.ann_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.ann_tree.pack(fill="both", expand=True)

        self.ann_tree.bind("<Double-1>", self._on_ann_double_click)

        tk.Label(parent, text="Double-clic sur une ligne pour ouvrir l'annonce dans le navigateur",
                 bg=C["card"], fg=C["muted"], font=("Segoe UI", 8), anchor="w"
                 ).pack(side="bottom", fill="x", padx=12, pady=(0, 6))

    def _on_ann_double_click(self, _event):
        sel = self.ann_tree.selection()
        if not sel:
            return
        idx = self.ann_tree.index(sel[0])
        if 0 <= idx < len(self._listing_data):
            url = self._listing_data[idx].get("_url", "")
            if url:
                webbrowser.open(url)

    def _run_preview(self):
        self._save_all()
        self._ann_count_var.set("")
        self._ann_loading_var.set("Chargement des annonces…")
        self.ann_tree.delete(*self.ann_tree.get_children())
        self._listing_data = []

        def worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(SCRIPT), "--preview-json"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(BASE_DIR),
                )
                raw, _ = proc.communicate(timeout=90)
                text   = raw.decode("utf-8", errors="replace").strip()
                if text:
                    data = json.loads(text)
                    self.after(0, self._populate_annonces, data)
                else:
                    self.after(0, self._ann_count_var.set, "Aucun résultat reçu")
            except Exception as exc:
                self.after(0, self._ann_count_var.set, f"Erreur : {exc}")
            finally:
                self.after(0, self._ann_loading_var.set, "")

        threading.Thread(target=worker, daemon=True).start()

    def _populate_annonces(self, data: dict):
        self.ann_tree.delete(*self.ann_tree.get_children())
        self._listing_data = []

        if not data.get("ok"):
            self._ann_count_var.set(f"Erreur : {data.get('error', '?')}")
            return

        listings  = data.get("listings", [])
        total     = data.get("total", 0)
        new_count = sum(1 for l in listings if l.get("_is_new"))

        msg = f"{len(listings)} annonces chargées  (total site : {total})"
        if new_count:
            msg += f"  —  ★ {new_count} nouvelle(s)"
        self._ann_count_var.set(msg)

        for l in listings:
            is_new = l.get("_is_new", False)
            title  = l.get("main_title") or l.get("lodging_type_string") or "?"
            rent   = f"{l['cost_total_rent']} €/mois" if l.get("cost_total_rent") else "—"
            city   = l.get("address_city", "")
            date   = l.get("published_at_string", "")
            l["_url"] = BASE_URL + l.get("relative_url", "")
            self._listing_data.append(l)
            self.ann_tree.insert("", "end",
                                 values=("★" if is_new else "", title, rent, city, date),
                                 tags=("new" if is_new else "seen",))

        self._update_cache_info()

    # ── Onglet Filtres ────────────────────────────────────────────────────────

    def _build_filter_tab(self, parent):
        top = tk.Frame(parent, bg=C["card"])
        top.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(top, text="Sélectionne les critères — sauvegardés avec la configuration.",
                 bg=C["card"], fg=C["muted"], font=("Segoe UI", 8)).pack(side="left")
        self._btn(top, "Tout réinitialiser", C["gray"], self._reset_filters,
                  side="right", padx=(0, 0), fg=C["gray_fg"])
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

        sf  = ScrollFrame(parent, bg=C["card"])
        sf.pack(fill="both", expand=True)
        inn = sf.inner
        inn.configure(padx=14, pady=10)

        # PRIX
        self._fsec(inn, "PRIX")
        pr = tk.Frame(inn, bg=C["card"])
        pr.pack(fill="x", pady=(2, 8))
        for key, lbl in [("rent_min", "Loyer min"), ("rent_max", "Loyer max")]:
            f = tk.Frame(pr, bg=C["card"])
            f.pack(side="left", padx=(0, 24))
            tk.Label(f, text=lbl, bg=C["card"], fg=C["label"],
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            var = tk.StringVar()
            self.filter_vars[key] = var
            tk.Entry(f, textvariable=var, width=7,
                     font=("Segoe UI", 9), bd=1, relief="solid", bg=C["input"]
                     ).pack(side="left")
            tk.Label(f, text="€/mois", bg=C["card"], fg=C["muted"],
                     font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))

        # SURFACE
        self._fsec(inn, "SURFACE")
        sr = tk.Frame(inn, bg=C["card"])
        sr.pack(fill="x", pady=(2, 8))
        for key, lbl, unit in [
            ("lodging_surface_min", "Surface logement min", "m²"),
            ("lodging_surface_max", "Surface logement max", "m²"),
            ("room_surface_min",    "Surface chambre min",  "m²"),
            ("room_surface_max",    "Surface chambre max",  "m²"),
        ]:
            f = tk.Frame(sr, bg=C["card"])
            f.pack(side="left", padx=(0, 14))
            tk.Label(f, text=lbl, bg=C["card"], fg=C["label"],
                     font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
            var = tk.StringVar()
            self.filter_vars[key] = var
            tk.Entry(f, textvariable=var, width=5,
                     font=("Segoe UI", 9), bd=1, relief="solid", bg=C["input"]
                     ).pack(side="left")
            tk.Label(f, text=unit, bg=C["card"], fg=C["muted"],
                     font=("Segoe UI", 8)).pack(side="left", padx=(3, 0))

        # Groupes checkbox
        self._fsec(inn, "TYPE D'ANNONCE",   "Décocher = exclure")
        self._cbgroup(inn, LISTING_TYPES, default=True,  cols=3, require=False)
        self._fsec(inn, "TYPE DE LOGEMENT", "Décocher = exclure")
        self._cbgroup(inn, LODGING_TYPES, default=True,  cols=4, require=False)
        self._fsec(inn, "NOMBRE DE PIÈCES", "Décocher = exclure")
        self._cbgroup(inn, ROOM_SIZES,    default=True,  cols=4, require=False)
        self._fsec(inn, "NOMBRE DE COLOCATAIRES", "Décocher = exclure")
        self._cbgroup(inn, HOUSEMATES,    default=True,  cols=4, require=False)
        self._fsec(inn, "ÉQUIPEMENTS",    "Cocher = exiger")
        self._cbgroup(inn, COMMODITIES,   default=False, cols=3, require=True)
        self._fsec(inn, "RÈGLES",         "Cocher = exiger")
        self._cbgroup(inn, RULES,         default=False, cols=2, require=True)

        # DATE
        self._fsec(inn, "DATE DE PUBLICATION")
        dr = tk.Frame(inn, bg=C["card"])
        dr.pack(fill="x", pady=(2, 14))
        for key, lbl, hint in [
            ("date_min",           "Publiées depuis (jours)", "ex: 7"),
            ("availability_start", "Disponible à partir de",  "AAAA-MM-JJ"),
        ]:
            f = tk.Frame(dr, bg=C["card"])
            f.pack(side="left", padx=(0, 28))
            tk.Label(f, text=lbl, bg=C["card"], fg=C["label"],
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            var = tk.StringVar()
            self.filter_vars[key] = var
            tk.Entry(f, textvariable=var, width=12,
                     font=("Segoe UI", 9), bd=1, relief="solid", bg=C["input"]
                     ).pack(side="left")
            tk.Label(f, text=hint, bg=C["card"], fg=C["muted"],
                     font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))

    def _fsec(self, parent, title, note=""):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", pady=(8, 2))
        tk.Label(row, text=title, bg=C["card"], fg="#1e3a5f",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        if note:
            tk.Label(row, text=f"  — {note}", bg=C["card"], fg=C["muted"],
                     font=("Segoe UI", 8)).pack(side="left")

    def _cbgroup(self, parent, items, default: bool, cols: int, require: bool):
        frame = tk.Frame(parent, bg=C["card"])
        frame.pack(fill="x", pady=(0, 2))
        sel_clr = "#fef9c3" if require else C["check_on"] if hasattr(C, "check_on") else "#dbeafe"

        for i, (key, label) in enumerate(items):
            var = tk.BooleanVar(value=default)
            self.filter_vars[key] = var
            cf = tk.Frame(frame, bg=C["card"], cursor="hand2")
            cf.grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=2)
            tk.Checkbutton(cf, variable=var,
                           bg=C["card"], activebackground=C["card"],
                           selectcolor="#dbeafe", bd=0, cursor="hand2"
                           ).pack(side="left")
            lbl = tk.Label(cf, text=label, bg=C["card"], fg=C["text"],
                           font=("Segoe UI", 9), cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

        ctrl = tk.Frame(parent, bg=C["card"])
        ctrl.pack(anchor="w", pady=(0, 6))
        keys = [k for k, _ in items]
        for txt, val in [("Tout cocher", True), ("Tout décocher", False)]:
            tk.Button(ctrl, text=txt, bg=C["gray"], fg=C["gray_fg"],
                      font=("Segoe UI", 7), bd=0, padx=6, pady=2,
                      cursor="hand2",
                      command=lambda v=val, ks=keys: [self.filter_vars[k].set(v) for k in ks]
                      ).pack(side="left", padx=(0, 4))

    # ── Onglet Historique ─────────────────────────────────────────────────────

    def _build_historique_tab(self, parent):
        top = tk.Frame(parent, bg=C["card"])
        top.pack(fill="x", padx=12, pady=(10, 6))
        self._btn(top, "Actualiser",   C["gray"], self._load_history,  fg=C["gray_fg"])
        self._btn(top, "Tout effacer", C["red"],  self._clear_history, padx=(6, 0))
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

        wrap = tk.Frame(parent, bg=C["card"])
        wrap.pack(fill="both", expand=True)

        cols = ("date", "count", "apercu")
        self.hist_tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                      selectmode="browse")
        self.hist_tree.heading("date",   text="Date")
        self.hist_tree.heading("count",  text="Annonces")
        self.hist_tree.heading("apercu", text="Aperçu des titres")
        self.hist_tree.column("date",   width=150, minwidth=130, stretch=False)
        self.hist_tree.column("count",  width=90,  minwidth=70,  stretch=False, anchor="center")
        self.hist_tree.column("apercu", width=500, minwidth=200, stretch=True)

        vsb = tk.Scrollbar(wrap, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.hist_tree.pack(fill="both", expand=True)

        self.hist_tree.bind("<Double-1>", self._on_hist_double_click)
        tk.Label(parent, text="Double-clic sur une alerte pour voir les annonces dans le navigateur",
                 bg=C["card"], fg=C["muted"], font=("Segoe UI", 8), anchor="w"
                 ).pack(side="bottom", fill="x", padx=12, pady=(0, 6))

        self._load_history()

    def _load_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        self._history_data = []

        if not HISTORY_FILE.exists():
            self.hist_tree.insert("", "end",
                                  values=("—", "—", "Aucune alerte envoyée pour le moment"))
            return
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            self.hist_tree.insert("", "end", values=("Erreur", "", str(exc)))
            return

        if not history:
            self.hist_tree.insert("", "end",
                                  values=("—", "—", "Aucune alerte envoyée pour le moment"))
            return

        for entry in history:
            ts = entry.get("timestamp", "")
            try:
                date_str = datetime.fromisoformat(ts).strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = ts
            count  = entry.get("count", 0)
            titles = ", ".join(l.get("title", "?") for l in entry.get("listings", [])[:3])
            extra  = len(entry.get("listings", [])) - 3
            if extra > 0:
                titles += f"  +{extra} autre(s)"
            self._history_data.append(entry)
            self.hist_tree.insert("", "end",
                                  values=(date_str, f"{count} annonce(s)", titles))

    def _on_hist_double_click(self, _event):
        sel = self.hist_tree.selection()
        if not sel:
            return
        idx = self.hist_tree.index(sel[0])
        if 0 <= idx < len(self._history_data):
            for l in self._history_data[idx].get("listings", []):
                url = l.get("url", "")
                if url:
                    webbrowser.open(url)

    def _clear_history(self):
        if not messagebox.askyesno("Confirmer", "Effacer tout l'historique des alertes ?"):
            return
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        self._load_history()
        self._log("Historique effacé.", "info")

    # ── Onglet Journal ────────────────────────────────────────────────────────

    def _build_log_tab(self, parent):
        top = tk.Frame(parent, bg=C["card"])
        top.pack(fill="x", padx=12, pady=(8, 4))
        for txt, cmd in [("monitor.log", self._view_log_file), ("Effacer", self._clear_log)]:
            tk.Button(top, text=txt, bg=C["gray"], fg=C["gray_fg"],
                      font=("Segoe UI", 8), bd=0, padx=8, pady=3,
                      cursor="hand2", command=cmd).pack(side="right", padx=(0, 4))
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

        lf = tk.Frame(parent, bg=C["log_bg"])
        lf.pack(fill="both", expand=True)
        self.log_widget = tk.Text(lf, state="disabled", font=("Consolas", 9),
                                  bg=C["log_bg"], fg=C["log_fg"],
                                  bd=0, padx=10, pady=8, wrap="word")
        sb = tk.Scrollbar(lf, command=self.log_widget.yview)
        self.log_widget.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_widget.pack(fill="both", expand=True)

        self.log_widget.tag_config("info",    foreground="#64748b")
        self.log_widget.tag_config("success", foreground="#4ade80")
        self.log_widget.tag_config("error",   foreground="#f87171")
        self.log_widget.tag_config("warn",    foreground="#facc15")
        self.log_widget.tag_config("stdout",  foreground=C["log_fg"])

    # ── Config ────────────────────────────────────────────────────────────────

    def _collect_filters(self) -> dict:
        f: dict = {}
        for key in ["rent_min", "rent_max",
                    "lodging_surface_min", "lodging_surface_max",
                    "room_surface_min",    "room_surface_max"]:
            v = self.filter_vars[key].get().strip()
            if v:
                try:
                    f[key] = int(v)
                except ValueError:
                    pass

        v = self.filter_vars["date_min"].get().strip()
        if v:
            try:
                f["date_min"] = -abs(int(v))
            except ValueError:
                pass

        avail = self.filter_vars["availability_start"].get().strip()
        if avail:
            f["availability_start"] = avail

        for key, _ in (LISTING_TYPES + LODGING_TYPES + ROOM_SIZES + HOUSEMATES):
            if not self.filter_vars[key].get():
                f[key] = False

        for key, _ in (COMMODITIES + RULES):
            if self.filter_vars[key].get():
                f[key] = True

        return f

    def _apply_filters(self, extra: dict):
        for key in ["rent_min", "rent_max",
                    "lodging_surface_min", "lodging_surface_max",
                    "room_surface_min",    "room_surface_max"]:
            v = extra.get(key)
            self.filter_vars[key].set(str(v) if v is not None else "")

        v = extra.get("date_min")
        self.filter_vars["date_min"].set(str(abs(v)) if v is not None else "")
        self.filter_vars["availability_start"].set(extra.get("availability_start", ""))

        for key, _ in (LISTING_TYPES + LODGING_TYPES + ROOM_SIZES + HOUSEMATES):
            self.filter_vars[key].set(extra.get(key, True) is not False)

        for key, _ in (COMMODITIES + RULES):
            self.filter_vars[key].set(extra.get(key) is True)

    def _reset_filters(self):
        for key in ["rent_min", "rent_max",
                    "lodging_surface_min", "lodging_surface_max",
                    "room_surface_min",    "room_surface_max",
                    "date_min",            "availability_start"]:
            self.filter_vars[key].set("")
        for key, _ in (LISTING_TYPES + LODGING_TYPES + ROOM_SIZES + HOUSEMATES):
            self.filter_vars[key].set(True)
        for key, _ in (COMMODITIES + RULES):
            self.filter_vars[key].set(False)
        self._log("Filtres réinitialisés.", "info")

    def _load_all(self):
        if not CONFIG_FILE.exists():
            self._update_cache_info()
            return
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            urls = cfg.get("urls") or ([cfg["url"]] if cfg.get("url") else [])
            self._set_urls(urls)
            self.v_notif.set(cfg.get("desktop_notifications", True))
            self.v_ntfy.set(cfg.get("ntfy_topic", ""))
            self._apply_filters(cfg.get("extra_filters", {}))
            self._update_cache_info()
        except Exception as e:
            self._log(f"Erreur lecture config : {e}", "error")

    def _save_all(self):
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
        cfg["urls"]                  = self._get_urls()
        cfg["extra_filters"]         = self._collect_filters()
        cfg["desktop_notifications"] = self.v_notif.get()
        cfg["ntfy_topic"]            = self.v_ntfy.get().strip()
        CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        self._log("Configuration et filtres sauvegardés.", "success")
        self._set_status("Sauvegardé")
        threading.Thread(target=self._git_push_config, daemon=True).start()
        return True

    def _git_push_config(self):
        try:
            cmds = [
                ["git", "add", str(CONFIG_FILE)],
                ["git", "commit", "-m", "config: mise à jour filtres"],
                ["git", "push"],
            ]
            for cmd in cmds:
                r = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
                if r.returncode != 0:
                    if "nothing to commit" in r.stdout + r.stderr:
                        break
                    self.after(0, self._log, f"[git] {r.stderr.strip()}", "error")
                    return
            self.after(0, self._log, "Configuration synchronisée avec GitHub.", "success")
        except Exception as e:
            self.after(0, self._log, f"[git] Erreur : {e}", "error")

    def _test_ntfy(self):
        import urllib.request
        topic = self.v_ntfy.get().strip()
        if not topic:
            messagebox.showwarning("ntfy.sh", "Saisis d'abord un topic ntfy.sh.")
            return
        def _do():
            try:
                import urllib.parse
                req = urllib.request.Request(
                    f"https://ntfy.sh/{topic}",
                    data="Annonce test".encode("utf-8"),
                    headers={
                        "Title":   urllib.parse.quote("Colocalert"),
                        "Tags":    "house",
                        "Click":   "https://www.lacartedescolocs.fr",
                        "Actions": "view, Voir l'annonce, https://www.lacartedescolocs.fr",
                    },
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                self._log("Notification ntfy envoyée.", "success")
            except Exception as e:
                self._log(f"[ntfy] Erreur : {e}", "error")
        threading.Thread(target=_do, daemon=True).start()

    # ── Journal ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "stdout"):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            w  = self.log_widget
            w.configure(state="normal")
            w.insert(tk.END, f"[{ts}] {msg}\n", tag)
            w.see(tk.END)
            w.configure(state="disabled")
        self.after(0, _do)

    def _log_line(self, line: str):
        low = line.lower()
        if "[erreur]" in low or "error" in low:       tag = "error"
        elif "nouvelle" in low and "annonce" in low:  tag = "warn"
        elif "envoy" in low or "succès" in low:       tag = "success"
        else:                                          tag = "stdout"
        self._log(line, tag)

    def _clear_log(self):
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state="disabled")

    def _view_log_file(self):
        if not LOG_FILE.exists():
            self._log("monitor.log n'existe pas encore.", "info")
            return
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        self._log("── monitor.log (50 dernières lignes) ──", "info")
        for line in lines[-50:]:
            self._log(line, "stdout")
        self._log("── fin ──", "info")

    def _set_status(self, msg: str):
        self.after(0, self.status_var.set,
                   f"{msg} — {datetime.now().strftime('%H:%M:%S')}")

    # ── Exécution script ──────────────────────────────────────────────────────

    def _run_script(self, args: list, label: str):
        self._set_status(f"{label}…")
        self._log(f"→ {label}…", "info")

        def worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(SCRIPT)] + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=str(BASE_DIR),
                )
                for raw in proc.stdout:
                    line = raw.rstrip("\n\r")
                    if line:
                        self._log_line(line)
                proc.wait()
            except Exception as e:
                self._log(f"Erreur lancement : {e}", "error")
            self._set_status(f"{label} terminé")
            self.after(0, self._update_cache_info)
            self.after(0, self._load_history)

        threading.Thread(target=worker, daemon=True).start()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run_discover(self):
        self._run_script(["--discover"], "Découverte")

    def _run_monitor(self):
        self._save_all()
        self._run_script([], "Vérification des annonces")

    def _refresh_scheduler_status(self):
        def worker():
            try:
                res = subprocess.run(
                    'schtasks /query /tn "ColocMonitor" /fo LIST',
                    shell=True, capture_output=True, text=True,
                    encoding="cp850", errors="replace",
                )
                if res.returncode != 0:
                    self.after(0, self._set_scheduler_status, "none")
                    return
                out = res.stdout
                if "Désactivé" in out or "Disabled" in out:
                    self.after(0, self._set_scheduler_status, "disabled")
                elif "Prêt" in out or "Ready" in out or "En cours" in out or "Running" in out:
                    interval = self._parse_scheduler_interval(out)
                    self.after(0, self._set_scheduler_status, "active", interval)
                else:
                    self.after(0, self._set_scheduler_status, "unknown")
            except Exception:
                self.after(0, self._set_scheduler_status, "none")
        threading.Thread(target=worker, daemon=True).start()

    def _parse_scheduler_interval(self, schtasks_output: str) -> str:
        for line in schtasks_output.splitlines():
            if "Intervalle" in line or "Schedule" in line or "Interval" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    return parts[-1].strip()
        return ""

    def _set_scheduler_status(self, state: str, detail: str = ""):
        dot_colors = {
            "active":   C["green"],
            "disabled": C["amber"],
            "none":     C["muted"],
            "unknown":  C["muted"],
        }
        labels = {
            "active":   f"Active{' — ' + detail if detail else ''}",
            "disabled": "Désactivée (en pause)",
            "none":     "Non installée",
            "unknown":  "État inconnu",
        }
        self._sched_dot.configure(fg=dot_colors.get(state, C["muted"]))
        self._sched_status_var.set(labels.get(state, "—"))

        is_active = state == "active"
        self._sched_toggle_var.set(is_active)
        if is_active:
            self._sched_toggle_btn.configure(text="  ON   ", bg=C["green"])
        else:
            self._sched_toggle_btn.configure(text="  OFF  ", bg=C["muted"])

    def _toggle_scheduler(self):
        if self._sched_toggle_var.get():
            self._disable_scheduler()
        else:
            self._enable_scheduler()

    def _setup_scheduler(self):
        interval = self._sched_interval.get() or "10"
        bat = (BASE_DIR / "run.bat").resolve()
        cmd = f'schtasks /create /tn "ColocMonitor" /tr "{bat}" /sc minute /mo {interval} /f'
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True,
                                 text=True, encoding="cp850", errors="replace")
            if res.returncode == 0:
                self._log(f"Tâche planifiée installée — vérification toutes les {interval} min.", "success")
                self._refresh_scheduler_status()
            else:
                self._log(f"Erreur : {res.stderr.strip() or res.stdout.strip()}", "error")
                self._log("Conseil : lance l'interface en tant qu'administrateur.", "warn")
        except Exception as e:
            self._log(f"Erreur : {e}", "error")

    def _enable_scheduler(self):
        try:
            res = subprocess.run('schtasks /change /tn "ColocMonitor" /enable',
                                 shell=True, capture_output=True,
                                 text=True, encoding="cp850", errors="replace")
            if res.returncode == 0:
                self._log("Tâche réactivée.", "success")
                self._refresh_scheduler_status()
            else:
                self._log(f"Erreur : {res.stderr.strip() or res.stdout.strip()}", "error")
        except Exception as e:
            self._log(f"Erreur : {e}", "error")

    def _disable_scheduler(self):
        try:
            res = subprocess.run('schtasks /change /tn "ColocMonitor" /disable',
                                 shell=True, capture_output=True,
                                 text=True, encoding="cp850", errors="replace")
            if res.returncode == 0:
                self._log("Tâche désactivée (elle reste installée, utilise Activer pour reprendre).", "warn")
                self._refresh_scheduler_status()
            else:
                self._log(f"Erreur : {res.stderr.strip() or res.stdout.strip()}", "error")
        except Exception as e:
            self._log(f"Erreur : {e}", "error")

    def _remove_scheduler(self):
        if not messagebox.askyesno("Confirmer",
                                   "Supprimer la tâche planifiée ColocMonitor ?"):
            return
        try:
            res = subprocess.run('schtasks /delete /tn "ColocMonitor" /f',
                                 shell=True, capture_output=True,
                                 text=True, encoding="cp850", errors="replace")
            if res.returncode == 0:
                self._log("Tâche planifiée supprimée.", "success")
                self._refresh_scheduler_status()
            else:
                self._log(f"Erreur : {res.stderr.strip() or res.stdout.strip()}", "error")
        except Exception as e:
            self._log(f"Erreur : {e}", "error")


# ── Référence BASE_URL pour _populate_annonces ───────────────────────────────
BASE_URL = "https://www.lacartedescolocs.fr"

if __name__ == "__main__":
    app = ColocApp()
    app.mainloop()
