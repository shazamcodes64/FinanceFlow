import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import sys
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from database import (
    initialize_database,
    get_summary,
    get_expenses_by_category,
    get_monthly_summary,
    get_all_transactions,
    add_transaction,
    update_transaction,
    delete_transaction,
    get_categories,
    add_category,
    delete_category,
    get_setting,
    set_setting,
    backup_database,
    export_transactions_csv,
)


# ============================================================
# FINANCE FLOW — UI THEME
# ============================================================

APP_NAME = "FINANCE FLOW"

# ---- Dark professional palette (canonical) ----
BG             = "#0F1419"   # dominant content background
SIDEBAR_BG     = "#0B0E13"   # sidebar rail (one step darker -> depth)
SURFACE        = "#161B22"   # card surface
SURFACE_HI     = "#1B222B"   # raised: inputs, comboboxes, secondary buttons, hover
ROW_ALT        = "#141A21"   # alternating table row
ROW_SELECT     = "#22303B"   # selected row / focus
BORDER         = "#262D36"   # subtle 1px card/input borders
BORDER_STRONG  = "#333D48"
TEXT_PRIMARY   = "#E6EDF3"   # off-white primary text
TEXT_SECONDARY = "#8B98A5"   # muted labels/captions
TEXT_DISABLED  = "#5C6773"
ACCENT         = "#E0B36A"   # primary accent: muted brass gold
ACCENT_HI      = "#EBC585"   # accent hover
ACCENT_LO      = "#B98C4A"   # accent pressed
TEXT_ON_ACCENT = "#0F1419"   # dark text on gold fills
PERIOD_A       = "#E0B36A"   # comparison period A = gold (brand)
PERIOD_B       = "#58A6D9"   # comparison period B = calm sky blue
INCOME         = "#4ADE80"   # semantic: income
EXPENSE        = "#F87171"   # semantic: expense
DANGER         = "#C45A5A"   # destructive buttons
DANGER_HI      = "#D26B6B"
SECONDARY_HI   = "#222C37"   # secondary button hover

# ---- Backward-compatible aliases (keep all existing refs valid) ----
BLACK        = BG
PANEL        = SURFACE
PANEL_LIGHT  = SURFACE_HI
WHITE        = TEXT_PRIMARY
MUTED        = TEXT_SECONDARY
GREEN        = INCOME
RED          = EXPENSE
PURPLE       = ACCENT      # was violet -> now gold (period A / focus ring)
BLUE         = PERIOD_B    # comparison period B

# ---- Typography ----
def resolve_font_family(candidates):
    """Pick the first installed family, else TkDefaultFont fallback."""
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for name in candidates:
        if name in available:
            return name
    return "TkDefaultFont"


# Resolved lazily in setup_theme() once a Tk root exists,
# because tkinter.font.families() requires an active interpreter.
FONT_UI = "TkDefaultFont"
FONT_MONO = "TkDefaultFont"

# ---- Spacing scale ----
SP_XS, SP_SM, SP_MD, SP_LG, SP_XL, SP_XXL = 4, 8, 12, 18, 24, 32

# Categorical palette for donut slices (harmonious, distinct from green/red)
CHART_PALETTE = ["#E0B36A", "#58A6D9", "#4FB3A9", "#D98C5A", "#7E8CA0", "#C98AAE"]


# ---- Small color helpers for after()-based button hover animation ----
def _hex_rgb(h):
    h = h.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _rgb_hex(r, g, b):
    return "#%02X%02X%02X" % (int(r), int(g), int(b))


CURRENCIES = {
    "INR": ("₹", "Indian Rupee"),
    "USD": ("$", "US Dollar"),
    "EUR": ("€", "Euro"),
    "GBP": ("£", "British Pound"),
    "JPY": ("¥", "Japanese Yen"),
    "CAD": ("C$", "Canadian Dollar"),
    "AUD": ("A$", "Australian Dollar"),
    "AED": ("د.إ", "UAE Dirham"),
    "SGD": ("S$", "Singapore Dollar"),
}

MONTHS = [
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December"
]


# ============================================================
# APPLICATION
# ============================================================

class FinanceFlow:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1360x850")
        self.root.minsize(1050, 700)
        self.root.configure(bg=BG)

        initialize_database()

        self.currency = get_setting("currency", "INR")
        if self.currency not in CURRENCIES:
            self.currency = "INR"

        self.current_page = "Dashboard"
        self.selected_transaction_id = None

        self.chart_canvases = []

        self.setup_theme()
        self.build_layout()
        self.navigate("Dashboard")

    # --------------------------------------------------------
    # DATE HELPERS
    # --------------------------------------------------------

    @staticmethod
    def display_date(iso_date):
        """Convert database YYYY-MM-DD to UI DD-MM-YYYY."""
        try:
            return datetime.strptime(
                str(iso_date), "%Y-%m-%d"
            ).strftime("%d-%m-%Y")
        except (ValueError, TypeError):
            return str(iso_date)

    @staticmethod
    def parse_display_date(display_date):
        """Convert UI DD-MM-YYYY to database YYYY-MM-DD."""
        return datetime.strptime(
            display_date.strip(), "%d-%m-%Y"
        ).date()

    @staticmethod
    def get_years():
        years = set()

        for row in get_all_transactions():
            try:
                years.add(int(str(row["transaction_date"])[:4]))
            except (ValueError, TypeError):
                pass

        years.add(date.today().year)

        return sorted(years, reverse=True)

    @staticmethod
    def period_dates(year, month=None):
        if month is None:
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        else:
            start = date(year, month, 1)

            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1).replace(day=1)
                from datetime import timedelta
                end = end - timedelta(days=1)

        return start.isoformat(), end.isoformat()

    # --------------------------------------------------------
    # THEME / STYLES
    # --------------------------------------------------------

    def setup_theme(self):
        # Resolve fonts now that a Tk root exists.
        global FONT_UI, FONT_MONO
        FONT_UI = resolve_font_family(
            ["Avenir Next", "Avenir", "Helvetica Neue", "Helvetica", "Arial"]
        )
        FONT_MONO = resolve_font_family(
            ["Menlo", "Monaco", "Courier New", "Courier"]
        )

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Global default fonts so every unstyled widget inherits the theme.
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                      "TkHeadingFont", "TkSmallCaptionFont"):
            try:
                tkfont.nametofont(fname).configure(
                    family=FONT_UI, size=10
                )
            except tk.TclError:
                pass

        # Treeview / table
        style.configure(
            "Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT_PRIMARY,
            borderwidth=0,
            rowheight=40,
            font=(FONT_UI, 10)
        )
        style.configure(
            "Treeview.Heading",
            background=SURFACE_HI,
            foreground=TEXT_PRIMARY,
            borderwidth=0,
            font=(FONT_UI, 9, "bold"),
            padding=10
        )
        style.map(
            "Treeview",
            background=[("selected", ROW_SELECT)],
            foreground=[("selected", TEXT_PRIMARY)]
        )

        # Comboboxes
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_HI,
            background=SURFACE_HI,
            foreground=TEXT_PRIMARY,
            arrowcolor=ACCENT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=8
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", SURFACE_HI)],
            foreground=[("readonly", TEXT_PRIMARY)],
            selectbackground=[("readonly", SURFACE_HI)],
            selectforeground=[("readonly", TEXT_PRIMARY)],
            bordercolor=[("focus", ACCENT)]
        )

        # Thin, modern scrollbar
        style.configure(
            "TScrollbar",
            background=SURFACE,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=TEXT_SECONDARY,
            gripcount=0,
            width=10
        )
        style.map(
            "TScrollbar",
            background=[("active", SURFACE_HI)],
            arrowcolor=[("active", ACCENT)]
        )

        # Make charts inherit the theme.
        try:
            import matplotlib as mpl
            mpl.rcParams["font.family"] = FONT_UI
            mpl.rcParams["axes.edgecolor"] = BORDER
            mpl.rcParams["axes.labelcolor"] = TEXT_SECONDARY
            mpl.rcParams["xtick.color"] = TEXT_SECONDARY
            mpl.rcParams["ytick.color"] = TEXT_SECONDARY
            mpl.rcParams["grid.color"] = BORDER
            mpl.rcParams["figure.facecolor"] = SURFACE
            mpl.rcParams["axes.facecolor"] = SURFACE
        except Exception:
            pass

    # --------------------------------------------------------
    # MAIN LAYOUT
    # --------------------------------------------------------

    def build_layout(self):
        self.sidebar = tk.Frame(
            self.root, bg=SIDEBAR_BG, width=225
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.main_area = tk.Frame(
            self.root, bg=BG
        )
        self.main_area.pack(
            side="right", fill="both", expand=True
        )

        self.build_sidebar()

        # Scrollable main content
        self.content_canvas = tk.Canvas(
            self.main_area,
            bg=BG,
            highlightthickness=0
        )

        self.content_scrollbar = ttk.Scrollbar(
            self.main_area,
            orient="vertical",
            command=self.content_canvas.yview
        )

        self.content = tk.Frame(
            self.content_canvas, bg=BG
        )

        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw"
        )

        self.content_canvas.configure(
            yscrollcommand=self.content_scrollbar.set
        )

        self.content.pack_propagate(True)

        self.content.bind(
            "<Configure>",
            lambda event: self.content_canvas.configure(
                scrollregion=self.content_canvas.bbox("all")
            )
        )

        self.content_canvas.bind(
            "<Configure>",
            lambda event: self.content_canvas.itemconfigure(
                self.content_window,
                width=event.width
            )
        )

        self.content_canvas.pack(
            side="left", fill="both", expand=True,
            padx=(34, 0), pady=28
        )

        self.content_scrollbar.pack(
            side="right", fill="y", padx=(0, 8), pady=28
        )

        self.content_canvas.bind_all(
            "<MouseWheel>",
            self.on_mousewheel
        )

    def on_mousewheel(self, event):
        if self.content_canvas.winfo_exists():
            self.content_canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units"
            )

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    def build_sidebar(self):
        self.create_sidebar()

    def create_sidebar(self):
        self.nav_buttons = {}
        self.nav_indicators = {}

        # Brand block
        brand = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        brand.pack(fill="x", padx=24, pady=(32, 30))

        tk.Label(
            brand,
            text="FINANCE FLOW",
            bg=SIDEBAR_BG,
            fg=TEXT_PRIMARY,
            font=(FONT_UI, 17, "bold")
        ).pack(anchor="w")

        tk.Label(
            brand,
            text="PERSONAL FINANCE",
            bg=SIDEBAR_BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 8, "bold")
        ).pack(anchor="w", pady=(5, 0))

        tk.Label(
            self.sidebar,
            text="MENU",
            bg=SIDEBAR_BG,
            fg=TEXT_DISABLED,
            font=(FONT_UI, 8, "bold")
        ).pack(anchor="w", padx=25, pady=(0, 10))

        pages = [
            ("Dashboard", "⌂"),
            ("Transactions", "↔"),
            ("Reports", "▤"),
            ("Settings", "⚙"),
        ]

        for page, symbol in pages:
            row = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
            row.pack(fill="x", padx=13, pady=2)

            indicator = tk.Frame(row, bg=SIDEBAR_BG, width=3)
            indicator.pack(side="left", fill="y")
            indicator.pack_propagate(False)
            self.nav_indicators[page] = indicator

            button = tk.Label(
                row,
                text=f"   {symbol}    {page}",
                anchor="w",
                bg=SIDEBAR_BG,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 11),
                padx=15,
                pady=12,
                cursor="hand2",
                highlightthickness=0,
            )
            button.pack(side="left", fill="x", expand=True)
            button.bind("<Button-1>", lambda e, p=page: self.navigate(p))
            self.nav_buttons[page] = button

            self._add_nav_hover(button, page)

        # Spacer pushes the footer to the bottom
        tk.Frame(
            self.sidebar, bg=SIDEBAR_BG
        ).pack(fill="both", expand=True)

        tk.Label(
            self.sidebar,
            text="FINANCE FLOW  •  LOCAL APP",
            bg=SIDEBAR_BG,
            fg=TEXT_DISABLED,
            font=(FONT_UI, 8)
        ).pack(anchor="w", padx=24, pady=22)

    def _add_nav_hover(self, button, page):
        def on_enter(_event):
            if self.current_page != page:
                try:
                    button.configure(bg=SURFACE_HI, fg=TEXT_PRIMARY)
                except tk.TclError:
                    pass

        def on_leave(_event):
            if self.current_page != page:
                try:
                    button.configure(bg=SIDEBAR_BG, fg=TEXT_SECONDARY)
                except tk.TclError:
                    pass

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    def navigate(self, page):
        self.current_page = page

        for name, button in self.nav_buttons.items():
            if name == page:
                button.configure(bg=SURFACE_HI, fg=TEXT_PRIMARY)
            else:
                button.configure(bg=SIDEBAR_BG, fg=TEXT_SECONDARY)

        for name, indicator in self.nav_indicators.items():
            indicator.configure(
                bg=ACCENT if name == page else SIDEBAR_BG
            )

        self.clear_content()

        if page == "Dashboard":
            self.show_dashboard()
        elif page == "Transactions":
            self.show_transactions()
        elif page == "Reports":
            self.show_reports()
        elif page == "Settings":
            self.show_settings()

        self.content_canvas.yview_moveto(0)

    def clear_content(self):
        self.chart_canvases.clear()

        for widget in self.content.winfo_children():
            widget.destroy()

    # --------------------------------------------------------
    # REUSABLE UI ELEMENTS
    # --------------------------------------------------------

    def create_header(self, parent, title, subtitle):
        tk.Label(
            parent,
            text=title,
            bg=parent.cget("bg"),
            fg=TEXT_PRIMARY,
            font=(FONT_UI, 26, "bold")
        ).pack(anchor="w")

        tk.Label(
            parent,
            text=subtitle,
            bg=parent.cget("bg"),
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 11)
        ).pack(anchor="w", pady=(5, 24))

    def heading(self, title, subtitle):
        self.create_header(self.content, title, subtitle)

    def create_card(self, parent, title=None, accent=False):
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1
        )

        if accent:
            tk.Frame(
                card, bg=ACCENT, height=2
            ).pack(fill="x")

        if title:
            tk.Label(
                card,
                text=title,
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 10, "bold")
            ).pack(anchor="w", padx=18, pady=(16, 8))

        return card

    def make_card(self, parent, title=None):
        return self.create_card(parent, title)

    def create_styled_button(
        self, parent, text, command,
        tier="secondary", font_size=9, vertical_padding=10
    ):
        if tier == "primary":
            rest, fg, hi, lo = ACCENT, TEXT_ON_ACCENT, ACCENT_HI, ACCENT_LO
        elif tier == "danger":
            rest, fg, hi, lo = DANGER, TEXT_PRIMARY, DANGER_HI, DANGER_HI
        else:
            rest, fg, hi, lo = (
                SURFACE_HI, TEXT_PRIMARY, SECONDARY_HI, SURFACE_HI
            )

        # tk.Label instead of tk.Button — macOS overrides bg/relief on tk.Button
        button = tk.Label(
            parent,
            text=text,
            bg=rest,
            fg=fg,
            highlightthickness=0,
            padx=16,
            pady=vertical_padding,
            font=(FONT_UI, font_size, "bold"),
            cursor="hand2"
        )

        # after()-based hover/press animation (no time.sleep)
        state = {"bg": rest, "job": None}

        def apply(color):
            try:
                button.configure(bg=color)
            except tk.TclError:
                pass

        def animate_to(target_hex):
            if state["job"] is not None:
                try:
                    button.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            s = _hex_rgb(state["bg"])
            tgt = _hex_rgb(target_hex)
            steps = 5

            def tick(i):
                t = i / steps
                mixed = _rgb_hex(
                    *[
                        round(s[k] + (tgt[k] - s[k]) * t)
                        for k in range(3)
                    ]
                )
                apply(mixed)
                state["bg"] = mixed
                if i < steps:
                    state["job"] = button.after(
                        12, lambda: tick(i + 1)
                    )
                else:
                    apply(target_hex)
                    state["bg"] = target_hex
                    state["job"] = None

            tick(0)

        def on_enter(_event):
            animate_to(hi)

        def on_leave(_event):
            animate_to(rest)

        def on_press(_event):
            if state["job"] is not None:
                try:
                    button.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            apply(lo)
            state["bg"] = lo

        def on_release(_event):
            animate_to(hi)
            animate_to(rest)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<ButtonPress-1>", on_press)
        button.bind("<ButtonRelease-1>", on_release)
        button.bind("<Button-1>", lambda e: command())

        return button

    def make_button(
        self, parent, text, command,
        color=PANEL_LIGHT, font_size=9, vertical_padding=10
    ):
        # Map the legacy color argument to a tier so existing call
        # sites get the right style with no edits.
        if color == "#7C3AED":
            tier = "primary"
        elif color == "#3A2020":
            tier = "danger"
        else:
            tier = "secondary"

        return self.create_styled_button(
            parent, text, command,
            tier=tier, font_size=font_size,
            vertical_padding=vertical_padding
        )

    def create_input_field(self, parent, variable=None, width=25):
        return tk.Entry(
            parent,
            textvariable=variable,
            width=width,
            bg=SURFACE_HI,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            bd=0,
            font=(FONT_UI, 11)
        )

    def make_entry(self, parent, variable=None, width=25):
        return self.create_input_field(parent, variable, width)

    def make_label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9)
        )

    def money(self, amount):
        symbol = CURRENCIES.get(
            self.currency, ("₹", "")
        )[0]
        return f"{symbol}{float(amount):,.2f}"

    def update_currency(self):
        self.currency = get_setting("currency", "INR")

        if self.currency not in CURRENCIES:
            self.currency = "INR"

    def clear_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    # --------------------------------------------------------
    # CHART HELPERS
    # --------------------------------------------------------

    def create_chart_canvas(
        self, parent, figure, width=None, height=None
    ):
        figure.patch.set_facecolor(SURFACE)

        canvas = FigureCanvasTkAgg(
            figure, master=parent
        )

        widget = canvas.get_tk_widget()
        widget.configure(bg=SURFACE, highlightthickness=0)
        widget.pack(fill="both", expand=True, padx=8, pady=8)

        canvas.draw()
        self.chart_canvases.append(canvas)

        return canvas

    def draw_donut_chart(self, parent, rows, title="EXPENSE BREAKDOWN"):
        card = self.make_card(parent, title)
        card.pack(fill="both", expand=True)

        if not rows:
            tk.Label(
                card,
                text="No expenses recorded for this period.",
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 10)
            ).pack(expand=True, pady=35)
            return card

        labels = [
            str(row["category"]) for row in rows
        ]
        values = [
            float(row["total"]) for row in rows
        ]

        figure = Figure(
            figsize=(5, 3.2),
            dpi=100,
            facecolor=SURFACE
        )

        ax = figure.add_subplot(111)
        ax.set_facecolor(SURFACE)

        colors = [
            CHART_PALETTE[i % len(CHART_PALETTE)]
            for i in range(len(values))
        ]

        wedges, _ = ax.pie(
            values,
            startangle=90,
            colors=colors,
            wedgeprops={
                "width": 0.42,
                "edgecolor": SURFACE,
                "linewidth": 2
            }
        )

        ax.text(
            0, 0,
            self.money(sum(values)),
            ha="center",
            va="center",
            color=TEXT_PRIMARY,
            fontsize=11,
            fontweight="bold"
        )

        ax.legend(
            wedges,
            labels,
            loc="center left",
            bbox_to_anchor=(0.88, 0.5),
            frameon=False,
            labelcolor=TEXT_PRIMARY,
            fontsize=8
        )

        ax.set_aspect("equal")
        figure.tight_layout()

        self.create_chart_canvas(card, figure)

        return card

    def draw_monthly_bar_chart(
        self, parent, monthly_rows, title="MONTHLY INCOME VS EXPENSES"
    ):
        card = self.make_card(parent, title)
        card.pack(fill="both", expand=True)

        if not monthly_rows:
            tk.Label(
                card,
                text="No monthly data available.",
                bg=SURFACE,
                fg=TEXT_SECONDARY
            ).pack(expand=True, pady=30)
            return card

        months = [
            str(row["month"])[5:7]
            for row in monthly_rows
        ]

        income = [
            float(row["income"]) for row in monthly_rows
        ]

        expenses = [
            float(row["expenses"]) for row in monthly_rows
        ]

        positions = list(range(len(months)))
        width = 0.36

        figure = Figure(
            figsize=(7, 3.2),
            dpi=100,
            facecolor=SURFACE
        )

        ax = figure.add_subplot(111)
        ax.set_facecolor(SURFACE)

        ax.bar(
            [p - width / 2 for p in positions],
            income,
            width,
            label="Income",
            color=GREEN
        )

        ax.bar(
            [p + width / 2 for p in positions],
            expenses,
            width,
            label="Expenses",
            color=RED
        )

        ax.set_xticks(positions)
        ax.set_xticklabels(months, color=TEXT_SECONDARY, fontsize=8)

        ax.tick_params(axis="y", colors=TEXT_SECONDARY, labelsize=8)
        ax.grid(axis="y", color=BORDER, alpha=0.6)
        ax.set_axisbelow(True)

        for spine in ax.spines.values():
            spine.set_color(BORDER)

        ax.legend(
            facecolor=SURFACE,
            edgecolor=BORDER,
            labelcolor=TEXT_PRIMARY,
            fontsize=8
        )

        figure.tight_layout()

        self.create_chart_canvas(card, figure)

        return card

    def draw_comparison_bar_chart(
        self, parent, categories_a, categories_b,
        label_a, label_b
    ):
        card = self.make_card(
            parent, "SIDE-BY-SIDE EXPENSE COMPARISON"
        )
        card.pack(fill="both", expand=True, pady=(18, 0))

        values_a = {
            row["category"]: float(row["total"])
            for row in categories_a
        }

        values_b = {
            row["category"]: float(row["total"])
            for row in categories_b
        }

        labels = list(dict.fromkeys(
            list(values_a.keys()) + list(values_b.keys())
        ))

        if not labels:
            tk.Label(
                card,
                text="No expenses to compare.",
                bg=SURFACE,
                fg=TEXT_SECONDARY
            ).pack(expand=True, pady=30)
            return

        data_a = [values_a.get(label, 0) for label in labels]
        data_b = [values_b.get(label, 0) for label in labels]

        positions = list(range(len(labels)))
        width = 0.36

        figure = Figure(
            figsize=(9, 3.6),
            dpi=100,
            facecolor=SURFACE
        )

        ax = figure.add_subplot(111)
        ax.set_facecolor(SURFACE)

        ax.bar(
            [p - width / 2 for p in positions],
            data_a,
            width,
            label=label_a,
            color=PURPLE
        )

        ax.bar(
            [p + width / 2 for p in positions],
            data_b,
            width,
            label=label_b,
            color=BLUE
        )

        ax.set_xticks(positions)
        ax.set_xticklabels(
            labels,
            color=TEXT_SECONDARY,
            fontsize=8,
            rotation=20,
            ha="right"
        )

        ax.tick_params(axis="y", colors=TEXT_SECONDARY, labelsize=8)
        ax.grid(axis="y", color=BORDER, alpha=0.6)
        ax.set_axisbelow(True)

        for spine in ax.spines.values():
            spine.set_color(BORDER)

        ax.legend(
            facecolor=SURFACE,
            edgecolor=BORDER,
            labelcolor=TEXT_PRIMARY,
            fontsize=8
        )

        figure.tight_layout()

        self.create_chart_canvas(card, figure)

    # --------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------

    def show_dashboard(self):
        self.heading(
            "Dashboard",
            "An overview of your personal finances."
        )

        selector_row = tk.Frame(self.content, bg=BG)
        selector_row.pack(fill="x", pady=(0, 18))

        tk.Label(
            selector_row,
            text="SELECT YEAR",
            bg=BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9, "bold")
        ).pack(side="left", padx=(0, 10))

        years = self.get_years()

        self.dashboard_year = tk.StringVar(
            value=str(date.today().year)
        )

        year_box = ttk.Combobox(
            selector_row,
            textvariable=self.dashboard_year,
            values=[str(year) for year in years],
            state="readonly",
            width=12
        )
        year_box.pack(side="left")

        year_box.bind(
            "<<ComboboxSelected>>",
            lambda event: self.refresh_dashboard()
        )

        self.dashboard_cards = tk.Frame(
            self.content, bg=BG
        )
        self.dashboard_cards.pack(fill="x")

        self.dashboard_charts = tk.Frame(
            self.content, bg=BG
        )
        self.dashboard_charts.pack(
            fill="both", expand=True, pady=(20, 0)
        )

        self.dashboard_recent = tk.Frame(
            self.content, bg=BG
        )
        self.dashboard_recent.pack(
            fill="x", pady=(20, 0)
        )

        self.refresh_dashboard()

    def refresh_dashboard(self):
        if not hasattr(self, "dashboard_cards"):
            return

        self.clear_frame(self.dashboard_cards)
        self.clear_frame(self.dashboard_charts)
        self.clear_frame(self.dashboard_recent)
        self.chart_canvases.clear()

        try:
            selected_year = int(self.dashboard_year.get())
        except ValueError:
            selected_year = date.today().year

        start_text = f"{selected_year}-01-01"
        end_text = f"{selected_year}-12-31"

        summary = get_summary(start_text, end_text)

        card_data = [
            ("TOTAL BALANCE", summary["balance"], TEXT_PRIMARY),
            ("TOTAL INCOME", summary["income"], INCOME),
            ("TOTAL EXPENSES", summary["expenses"], EXPENSE),
        ]

        for title, amount, color in card_data:
            card = self.make_card(self.dashboard_cards)
            card.pack(
                side="left",
                fill="both",
                expand=True,
                padx=(0, 12)
            )

            tk.Label(
                card,
                text=title,
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 9, "bold")
            ).pack(anchor="w", padx=18, pady=(18, 8))

            tk.Label(
                card,
                text=self.money(amount),
                bg=SURFACE,
                fg=color,
                font=(FONT_MONO, 22, "bold")
            ).pack(anchor="w", padx=18, pady=(0, 18))

        category_rows = get_expenses_by_category(
            start_text, end_text
        )

        monthly_rows = get_monthly_summary(selected_year)

        charts_row = tk.Frame(
            self.dashboard_charts, bg=BG
        )
        charts_row.pack(fill="both", expand=True)

        self.draw_donut_chart(
            charts_row,
            category_rows,
            "SPENDING BY CATEGORY"
        ).pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 12)
        )

        self.draw_monthly_bar_chart(
            charts_row,
            monthly_rows,
            f"INCOME VS EXPENSES — {selected_year}"
        ).pack(
            side="left",
            fill="both",
            expand=True
        )

        recent_card = self.make_card(
            self.dashboard_recent,
            "RECENT TRANSACTIONS"
        )
        recent_card.pack(fill="x")

        rows = get_all_transactions(
            start_date=start_text,
            end_date=end_text
        )[:7]

        if not rows:
            tk.Label(
                recent_card,
                text=f"No transactions recorded in {selected_year}.",
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 10)
            ).pack(anchor="w", padx=18, pady=20)
            return

        for row in rows:
            line = tk.Frame(recent_card, bg=SURFACE)
            line.pack(fill="x", padx=18, pady=8)

            amount = float(row["amount"])
            is_income = row["transaction_type"] == "Income"

            tk.Label(
                line,
                text=(
                    f'{row["category"]}  •  '
                    f'{self.display_date(row["transaction_date"])}'
                ),
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=(FONT_UI, 9)
            ).pack(side="left")

            tk.Label(
                line,
                text=(
                    f"+{self.money(amount)}"
                    if is_income else f"-{self.money(amount)}"
                ),
                bg=SURFACE,
                fg=INCOME if is_income else EXPENSE,
                font=(FONT_MONO, 10, "bold")
            ).pack(side="right")

    # --------------------------------------------------------
    # TRANSACTIONS
    # --------------------------------------------------------

    def show_transactions(self):
        self.heading(
            "Transactions",
            "Add, edit, view and manage your income and expenses."
        )

        toolbar = tk.Frame(self.content, bg=BG)
        toolbar.pack(fill="x", pady=(0, 15))

        self.make_button(
            toolbar,
            "+ Add Transaction",
            lambda: self.transaction_dialog()
        ).pack(side="left", padx=(0, 8))

        self.make_button(
            toolbar,
            "Edit Selected",
            self.edit_selected_transaction
        ).pack(side="left", padx=8)

        self.make_button(
            toolbar,
            "Delete Selected",
            self.remove_selected_transaction,
            color="#3A2020"
        ).pack(side="left", padx=8)

        filter_frame = tk.Frame(self.content, bg=BG)
        filter_frame.pack(fill="x", pady=(0, 12))

        tk.Label(
            filter_frame,
            text="Type:",
            bg=BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 10)
        ).pack(side="left", padx=(0, 8))

        self.transaction_filter = ttk.Combobox(
            filter_frame,
            values=["All", "Income", "Expense"],
            state="readonly",
            width=15
        )
        self.transaction_filter.set("All")
        self.transaction_filter.pack(side="left")

        self.transaction_filter.bind(
            "<<ComboboxSelected>>",
            lambda event: self.refresh_transaction_table()
        )

        self.transaction_count = tk.Label(
            filter_frame,
            text="",
            bg=BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 10)
        )
        self.transaction_count.pack(side="right")

        table_frame = tk.Frame(
            self.content, bg=SURFACE,
            highlightbackground=BORDER, highlightthickness=1
        )
        table_frame.pack(fill="both", expand=True)

        columns = (
            "number", "date", "type",
            "category", "description", "amount"
        )

        self.transaction_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        headings = {
            "number": "#",
            "date": "DATE",
            "type": "TYPE",
            "category": "CATEGORY",
            "description": "DESCRIPTION",
            "amount": "AMOUNT",
        }

        widths = {
            "number": 50,
            "date": 120,
            "type": 100,
            "category": 130,
            "description": 260,
            "amount": 140,
        }

        for column in columns:
            self.transaction_tree.heading(
                column, text=headings[column]
            )
            self.transaction_tree.column(
                column,
                width=widths[column],
                minwidth=50,
                anchor="w"
            )

        self.transaction_tree.column(
            "number", anchor="center"
        )
        self.transaction_tree.column(
            "amount", anchor="e"
        )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.transaction_tree.yview
        )

        self.transaction_tree.configure(
            yscrollcommand=scrollbar.set
        )

        self.transaction_tree.pack(
            side="left",
            fill="both",
            expand=True,
            padx=8,
            pady=8
        )

        scrollbar.pack(
            side="right",
            fill="y",
            pady=8
        )

        self.transaction_tree.bind(
            "<Double-1>",
            lambda event: self.edit_selected_transaction()
        )

        self.refresh_transaction_table()

    def refresh_transaction_table(self):
        if not hasattr(self, "transaction_tree"):
            return

        for item in self.transaction_tree.get_children():
            self.transaction_tree.delete(item)

        # Subtle alternating row colors
        self.transaction_tree.tag_configure(
            "even", background=SURFACE
        )
        self.transaction_tree.tag_configure(
            "odd", background=ROW_ALT
        )

        selected_type = self.transaction_filter.get()

        if selected_type == "All":
            rows = get_all_transactions()
        else:
            rows = get_all_transactions(
                transaction_type=selected_type
            )

        for number, row in enumerate(rows, start=1):
            transaction_id = str(row["id"])
            amount = float(row["amount"])
            row_tag = "even" if number % 2 == 0 else "odd"

            self.transaction_tree.insert(
                "",
                "end",
                iid=transaction_id,
                tags=(row_tag,),
                values=(
                    number,
                    self.display_date(row["transaction_date"]),
                    row["transaction_type"],
                    row["category"],
                    row["description"],
                    self.money(amount)
                )
            )

        self.transaction_count.configure(
            text=f"{len(rows)} transaction(s)"
        )

    def transaction_dialog(self, transaction=None):
        is_edit = transaction is not None

        dialog = tk.Toplevel(self.root)
        dialog.title(
            "Edit Transaction" if is_edit else "Add Transaction"
        )
        dialog.geometry("460x590")
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Edit Transaction" if is_edit else "New Transaction",
            bg=BG,
            fg=TEXT_PRIMARY,
            font=(FONT_UI, 20, "bold")
        ).pack(anchor="w", padx=28, pady=(25, 5))

        tk.Label(
            dialog,
            text="Enter the transaction details below.",
            bg=BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9)
        ).pack(anchor="w", padx=28, pady=(0, 20))

        form = tk.Frame(dialog, bg=BG)
        form.pack(fill="both", expand=True, padx=28)

        type_var = tk.StringVar(
            value=transaction["transaction_type"]
            if is_edit else "Expense"
        )

        amount_var = tk.StringVar(
            value=str(transaction["amount"])
            if is_edit else ""
        )

        category_var = tk.StringVar(
            value=transaction["category"]
            if is_edit else ""
        )

        description_var = tk.StringVar(
            value=transaction["description"]
            if is_edit else ""
        )

        date_var = tk.StringVar(
            value=self.display_date(transaction["transaction_date"])
            if is_edit else date.today().strftime("%d-%m-%Y")
        )

        def field_label(text):
            tk.Label(
                form,
                text=text,
                bg=BG,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 9, "bold")
            ).pack(anchor="w", pady=(9, 5))

        field_label("TRANSACTION TYPE")

        type_box = ttk.Combobox(
            form,
            textvariable=type_var,
            values=["Income", "Expense"],
            state="readonly"
        )
        type_box.pack(fill="x", ipady=5)

        field_label("AMOUNT")

        self.make_entry(
            form, amount_var
        ).pack(fill="x", ipady=8)

        field_label("CATEGORY")

        category_box = ttk.Combobox(
            form,
            textvariable=category_var,
            state="readonly"
        )
        category_box.pack(fill="x", ipady=5)

        def update_categories(*args):
            choices = get_categories(type_var.get())
            category_box.configure(values=choices)

            if category_var.get() not in choices:
                category_var.set(
                    choices[0] if choices else ""
                )

        type_var.trace_add("write", update_categories)
        update_categories()

        field_label("DESCRIPTION")

        self.make_entry(
            form, description_var
        ).pack(fill="x", ipady=8)

        field_label("DATE (DD-MM-YYYY)")

        self.make_entry(
            form, date_var
        ).pack(fill="x", ipady=8)

        def save():
            try:
                amount_text = amount_var.get().replace(
                    ",", ""
                ).strip()

                amount = float(amount_text)

                if amount <= 0:
                    raise ValueError(
                        "Amount must be greater than zero."
                    )

                selected_date = self.parse_display_date(
                    date_var.get()
                )

                if not category_var.get():
                    raise ValueError(
                        "Please select a category."
                    )

                values = (
                    type_var.get(),
                    amount,
                    category_var.get(),
                    description_var.get().strip(),
                    selected_date.isoformat()
                )

                if is_edit:
                    update_transaction(
                        transaction["id"], *values
                    )
                else:
                    add_transaction(*values)

                dialog.destroy()

                if self.current_page == "Transactions":
                    self.refresh_transaction_table()

                if self.current_page == "Dashboard":
                    self.refresh_dashboard()

                messagebox.showinfo(
                    "Saved",
                    "Transaction saved successfully.",
                    parent=self.root
                )

            except ValueError as error:
                messagebox.showerror(
                    "Invalid Details",
                    str(error),
                    parent=dialog
                )

            except Exception as error:
                messagebox.showerror(
                    "Error",
                    f"Could not save transaction:\n{error}",
                    parent=dialog
                )

        # Primary gold save button
        self.make_button(
            dialog,
            "SAVE TRANSACTION",
            save,
            color="#7C3AED",
            font_size=13,
            vertical_padding=17
        ).pack(
            fill="x",
            padx=28,
            pady=(15, 25)
        )

    def get_selected_transaction(self):
        selected = self.transaction_tree.selection()

        if not selected:
            messagebox.showwarning(
                "No Selection",
                "Please select a transaction first."
            )
            return None

        transaction_id = int(selected[0])

        rows = get_all_transactions()

        for row in rows:
            if row["id"] == transaction_id:
                return row

        return None

    def edit_selected_transaction(self):
        transaction = self.get_selected_transaction()

        if transaction:
            self.transaction_dialog(transaction)

    def remove_selected_transaction(self):
        transaction = self.get_selected_transaction()

        if not transaction:
            return

        confirmed = messagebox.askyesno(
            "Delete Transaction",
            "Are you sure you want to delete this transaction?"
        )

        if confirmed:
            delete_transaction(transaction["id"])
            self.refresh_transaction_table()

    # --------------------------------------------------------
    # REPORTS
    # --------------------------------------------------------

    def show_reports(self):
        self.heading(
            "Reports",
            "Review your financial activity and compare different periods."
        )

        # Date range report
        filters_card = self.make_card(
            self.content, "DATE RANGE REPORT"
        )
        filters_card.pack(fill="x", pady=(0, 18))

        filters = tk.Frame(filters_card, bg=SURFACE)
        filters.pack(fill="x", padx=18, pady=(0, 18))

        tk.Label(
            filters,
            text="START DATE",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9, "bold")
        ).pack(side="left", padx=(0, 8))

        self.report_start = tk.StringVar(
            value=date.today().replace(day=1).strftime("%d-%m-%Y")
        )

        self.make_entry(
            filters, self.report_start, 13
        ).pack(side="left", padx=(0, 18), ipady=6)

        tk.Label(
            filters,
            text="END DATE",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9, "bold")
        ).pack(side="left", padx=(0, 8))

        self.report_end = tk.StringVar(
            value=date.today().strftime("%d-%m-%Y")
        )

        self.make_entry(
            filters, self.report_end, 13
        ).pack(side="left", padx=(0, 18), ipady=6)

        self.make_button(
            filters,
            "Generate Report",
            self.generate_report,
            color="#7C3AED"
        ).pack(side="left", padx=5)

        self.make_button(
            filters,
            "Export CSV",
            self.export_report
        ).pack(side="left", padx=5)

        self.report_results = tk.Frame(
            self.content, bg=BG
        )
        self.report_results.pack(
            fill="both", expand=True
        )

        self.generate_report()

        # Period comparison section
        self.build_comparison_section()

    def generate_report(self):
        try:
            start = self.parse_display_date(
                self.report_start.get()
            )

            end = self.parse_display_date(
                self.report_end.get()
            )

            if start > end:
                raise ValueError(
                    "Start date cannot be after end date."
                )

            start_text = start.isoformat()
            end_text = end.isoformat()

        except ValueError as error:
            messagebox.showerror(
                "Invalid Dates",
                "Please enter dates in DD-MM-YYYY format.\n\n"
                + str(error)
            )
            return

        summary = get_summary(start_text, end_text)

        rows = get_all_transactions(
            start_date=start_text,
            end_date=end_text
        )

        self.clear_frame(self.report_results)

        cards = tk.Frame(
            self.report_results, bg=BG
        )
        cards.pack(fill="x")

        for title, amount, color in [
            ("INCOME", summary["income"], GREEN),
            ("EXPENSES", summary["expenses"], RED),
            ("NET BALANCE", summary["balance"], WHITE)
        ]:
            card = self.make_card(cards)
            card.pack(
                side="left",
                fill="both",
                expand=True,
                padx=(0, 12)
            )

            tk.Label(
                card,
                text=title,
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 9, "bold")
            ).pack(anchor="w", padx=18, pady=(16, 7))

            tk.Label(
                card,
                text=self.money(amount),
                bg=SURFACE,
                fg=color,
                font=(FONT_MONO, 20, "bold")
            ).pack(anchor="w", padx=18, pady=(0, 16))

        categories = get_expenses_by_category(
            start_text, end_text
        )

        charts = tk.Frame(
            self.report_results, bg=BG
        )
        charts.pack(fill="both", expand=True, pady=(18, 0))

        self.draw_donut_chart(
            charts,
            categories,
            "EXPENSE BREAKDOWN"
        ).pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 12)
        )

        detail_card = self.make_card(
            charts, "REPORT DETAILS"
        )
        detail_card.pack(
            side="left",
            fill="both",
            expand=True
        )

        top_category = (
            categories[0]["category"]
            if categories else "No expenses"
        )

        top_amount = (
            float(categories[0]["total"])
            if categories else 0
        )

        details = [
            ("Period", f"{start.strftime('%d-%m-%Y')} to {end.strftime('%d-%m-%Y')}"),
            ("Transactions", str(len(rows))),
            ("Top spending category", top_category),
            ("Top category spending", self.money(top_amount)),
            ("Income", self.money(summary["income"])),
            ("Expenses", self.money(summary["expenses"])),
            ("Net balance", self.money(summary["balance"])),
        ]

        for label, value in details:
            line = tk.Frame(detail_card, bg=SURFACE)
            line.pack(fill="x", padx=18, pady=8)

            tk.Label(
                line,
                text=label,
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 9)
            ).pack(side="left")

            tk.Label(
                line,
                text=value,
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=(FONT_MONO, 9, "bold")
            ).pack(side="right")

        tk.Label(
            self.report_results,
            text=f"Transactions in this period: {len(rows)}",
            bg=BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 10)
        ).pack(anchor="w", pady=(12, 0))

    def export_report(self):
        try:
            start = self.parse_display_date(
                self.report_start.get()
            ).isoformat()

            end = self.parse_display_date(
                self.report_end.get()
            ).isoformat()

            if start > end:
                raise ValueError(
                    "Start date cannot be after end date."
                )

        except ValueError as error:
            messagebox.showerror(
                "Invalid Dates",
                "Please enter dates in DD-MM-YYYY format.\n\n"
                + str(error)
            )
            return

        destination = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="finance_report.csv"
        )

        if destination:
            try:
                count = export_transactions_csv(
                    destination, start, end
                )

                messagebox.showinfo(
                    "Export Complete",
                    f"Exported {count} transaction(s)."
                )

            except Exception as error:
                messagebox.showerror(
                    "Export Error", str(error)
                )

    # --------------------------------------------------------
    # PERIOD COMPARISON
    # --------------------------------------------------------

    def build_comparison_section(self):
        comparison_card = self.make_card(
            self.content, "COMPARE TWO PERIODS"
        )
        comparison_card.pack(fill="x", pady=(22, 0))

        tk.Label(
            comparison_card,
            text=(
                "Compare expenses, income, balance and spending "
                "categories across two different periods."
            ),
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9)
        ).pack(anchor="w", padx=18, pady=(0, 15))

        controls = tk.Frame(
            comparison_card, bg=SURFACE
        )
        controls.pack(fill="x", padx=18, pady=(0, 18))

        years = self.get_years()
        year_values = [str(year) for year in years]

        current_year = date.today().year

        self.compare_mode = tk.StringVar(value="Full year")

        mode_box = ttk.Combobox(
            controls,
            textvariable=self.compare_mode,
            values=["Full year", "Specific month"],
            state="readonly",
            width=15
        )
        mode_box.pack(side="left", padx=(0, 15))

        self.compare_year_a = tk.StringVar(
            value=str(current_year)
        )
        self.compare_year_b = tk.StringVar(
            value=str(current_year - 1)
        )

        self.compare_month_a = tk.StringVar(
            value=MONTHS[date.today().month - 1]
        )
        self.compare_month_b = tk.StringVar(
            value=MONTHS[date.today().month - 1]
        )

        tk.Label(
            controls,
            text="PERIOD A",
            bg=SURFACE,
            fg=PURPLE,
            font=(FONT_UI, 9, "bold")
        ).pack(side="left", padx=(0, 8))

        self.compare_year_box_a = ttk.Combobox(
            controls,
            textvariable=self.compare_year_a,
            values=year_values,
            state="readonly",
            width=9
        )
        self.compare_year_box_a.pack(
            side="left", padx=(0, 7)
        )

        self.compare_month_box_a = ttk.Combobox(
            controls,
            textvariable=self.compare_month_a,
            values=MONTHS,
            state="readonly",
            width=12
        )
        self.compare_month_box_a.pack(
            side="left", padx=(0, 18)
        )

        tk.Label(
            controls,
            text="PERIOD B",
            bg=SURFACE,
            fg=BLUE,
            font=(FONT_UI, 9, "bold")
        ).pack(side="left", padx=(0, 8))

        self.compare_year_box_b = ttk.Combobox(
            controls,
            textvariable=self.compare_year_b,
            values=year_values,
            state="readonly",
            width=9
        )
        self.compare_year_box_b.pack(
            side="left", padx=(0, 7)
        )

        self.compare_month_box_b = ttk.Combobox(
            controls,
            textvariable=self.compare_month_b,
            values=MONTHS,
            state="readonly",
            width=12
        )
        self.compare_month_box_b.pack(
            side="left", padx=(0, 15)
        )

        self.make_button(
            controls,
            "COMPARE",
            self.compare_periods,
            color="#7C3AED",
            font_size=10,
            vertical_padding=11
        ).pack(side="left")

        def update_month_visibility(*args):
            is_month = self.compare_mode.get() == "Specific month"

            if is_month:
                self.compare_month_box_a.pack(
                    side="left", padx=(0, 18)
                )
                self.compare_month_box_b.pack(
                    side="left", padx=(0, 15)
                )
            else:
                self.compare_month_box_a.pack_forget()
                self.compare_month_box_b.pack_forget()

        self.compare_mode.trace_add(
            "write", update_month_visibility
        )

        update_month_visibility()

        self.comparison_results = tk.Frame(
            self.content, bg=BG
        )
        self.comparison_results.pack(
            fill="both", expand=True, pady=(18, 0)
        )

    def compare_periods(self):
        try:
            year_a = int(self.compare_year_a.get())
            year_b = int(self.compare_year_b.get())

            if self.compare_mode.get() == "Specific month":
                month_a = MONTHS.index(
                    self.compare_month_a.get()
                ) + 1

                month_b = MONTHS.index(
                    self.compare_month_b.get()
                ) + 1
            else:
                month_a = None
                month_b = None

            start_a, end_a = self.period_dates(
                year_a, month_a
            )

            start_b, end_b = self.period_dates(
                year_b, month_b
            )

        except (ValueError, IndexError):
            messagebox.showerror(
                "Comparison Error",
                "Please select valid years and months."
            )
            return

        summary_a = get_summary(start_a, end_a)
        summary_b = get_summary(start_b, end_b)

        categories_a = get_expenses_by_category(
            start_a, end_a
        )

        categories_b = get_expenses_by_category(
            start_b, end_b
        )

        label_a = (
            f"{self.compare_month_a.get()} {year_a}"
            if month_a else str(year_a)
        )

        label_b = (
            f"{self.compare_month_b.get()} {year_b}"
            if month_b else str(year_b)
        )

        self.clear_frame(self.comparison_results)
        self.chart_canvases.clear()

        # Period summary cards
        periods_row = tk.Frame(
            self.comparison_results, bg=BG
        )
        periods_row.pack(fill="x")

        for label, summary, categories, accent in [
            (label_a, summary_a, categories_a, PURPLE),
            (label_b, summary_b, categories_b, BLUE)
        ]:
            period_card = self.make_card(
                periods_row, label.upper()
            )
            period_card.pack(
                side="left",
                fill="both",
                expand=True,
                padx=(0, 12)
            )

            metrics = [
                ("Income", summary["income"], GREEN),
                ("Expenses", summary["expenses"], RED),
                ("Net balance", summary["balance"], WHITE),
            ]

            for metric, amount, color in metrics:
                line = tk.Frame(
                    period_card, bg=SURFACE
                )
                line.pack(
                    fill="x", padx=18, pady=7
                )

                tk.Label(
                    line,
                    text=metric,
                    bg=SURFACE,
                    fg=TEXT_SECONDARY,
                    font=(FONT_UI, 9)
                ).pack(side="left")

                tk.Label(
                    line,
                    text=self.money(amount),
                    bg=SURFACE,
                    fg=color,
                    font=(FONT_MONO, 10, "bold")
                ).pack(side="right")

            top_name = (
                categories[0]["category"]
                if categories else "None"
            )

            top_amount = (
                float(categories[0]["total"])
                if categories else 0
            )

            tk.Label(
                period_card,
                text=f"Top category: {top_name}",
                bg=SURFACE,
                fg=accent,
                font=(FONT_UI, 9, "bold")
            ).pack(
                anchor="w", padx=18, pady=(10, 2)
            )

            tk.Label(
                period_card,
                text=self.money(top_amount),
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=(FONT_MONO, 10, "bold")
            ).pack(
                anchor="w", padx=18, pady=(0, 16)
            )

        # Donut charts side by side
        donut_row = tk.Frame(
            self.comparison_results, bg=BG
        )
        donut_row.pack(
            fill="both", expand=True, pady=(18, 0)
        )

        self.draw_donut_chart(
            donut_row,
            categories_a,
            f"SPENDING — {label_a.upper()}"
        ).pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 12)
        )

        self.draw_donut_chart(
            donut_row,
            categories_b,
            f"SPENDING — {label_b.upper()}"
        ).pack(
            side="left",
            fill="both",
            expand=True
        )

        # Grouped bar chart
        self.draw_comparison_bar_chart(
            self.comparison_results,
            categories_a,
            categories_b,
            label_a,
            label_b
        )

        # Difference summary
        difference_card = self.make_card(
            self.comparison_results,
            "PERIOD-TO-PERIOD DIFFERENCE"
        )
        difference_card.pack(
            fill="x", pady=(18, 0)
        )

        differences = [
            (
                "Income difference",
                summary_b["income"] - summary_a["income"]
            ),
            (
                "Expense difference",
                summary_b["expenses"] - summary_a["expenses"]
            ),
            (
                "Balance difference",
                summary_b["balance"] - summary_a["balance"]
            ),
        ]

        for label, difference in differences:
            line = tk.Frame(
                difference_card, bg=SURFACE
            )
            line.pack(fill="x", padx=18, pady=8)

            tk.Label(
                line,
                text=label,
                bg=SURFACE,
                fg=TEXT_SECONDARY,
                font=(FONT_UI, 9)
            ).pack(side="left")

            if difference > 0:
                color = GREEN
                value = f"+{self.money(difference)}"
            elif difference < 0:
                color = RED
                value = f"-{self.money(abs(difference))}"
            else:
                color = WHITE
                value = self.money(0)

            tk.Label(
                line,
                text=value,
                bg=SURFACE,
                fg=color,
                font=(FONT_MONO, 10, "bold")
            ).pack(side="right")

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    def show_settings(self):
        self.heading(
            "Settings",
            "Manage your preferences, categories and database backups."
        )

        currency_card = self.make_card(
            self.content, "CURRENCY"
        )
        currency_card.pack(fill="x", pady=(0, 18))

        tk.Label(
            currency_card,
            text="Choose the currency symbol displayed in the app.",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9)
        ).pack(anchor="w", padx=18, pady=(0, 12))

        currency_row = tk.Frame(
            currency_card, bg=SURFACE
        )
        currency_row.pack(
            fill="x", padx=18, pady=(0, 18)
        )

        currency_var = tk.StringVar(
            value=self.currency
        )

        currency_box = ttk.Combobox(
            currency_row,
            textvariable=currency_var,
            values=list(CURRENCIES.keys()),
            state="readonly",
            width=15
        )
        currency_box.pack(
            side="left", padx=(0, 12)
        )

        def save_currency():
            set_setting(
                "currency", currency_var.get()
            )

            self.update_currency()

            messagebox.showinfo(
                "Saved",
                "Currency display preference updated."
            )

            self.navigate("Settings")

        self.make_button(
            currency_row,
            "Save Currency",
            save_currency,
            color="#7C3AED"
        ).pack(side="left")

        category_card = self.make_card(
            self.content, "CATEGORY MANAGEMENT"
        )
        category_card.pack(fill="x", pady=(0, 18))

        category_controls = tk.Frame(
            category_card, bg=SURFACE
        )
        category_controls.pack(
            fill="x", padx=18, pady=(0, 12)
        )

        category_type = tk.StringVar(
            value="Expense"
        )
        category_name = tk.StringVar()

        ttk.Combobox(
            category_controls,
            textvariable=category_type,
            values=["Income", "Expense"],
            state="readonly",
            width=12
        ).pack(
            side="left", padx=(0, 10)
        )

        self.make_entry(
            category_controls,
            category_name,
            25
        ).pack(
            side="left", padx=(0, 10), ipady=7
        )

        category_list = tk.Frame(
            category_card, bg=SURFACE
        )
        category_list.pack(
            fill="x", padx=18, pady=(0, 18)
        )

        def refresh_categories():
            self.clear_frame(category_list)

            for name in get_categories(
                category_type.get()
            ):
                row = tk.Frame(
                    category_list, bg=SURFACE
                )
                row.pack(fill="x", pady=3)

                tk.Label(
                    row,
                    text=name,
                    bg=SURFACE,
                    fg=TEXT_PRIMARY,
                    font=(FONT_UI, 9)
                ).pack(side="left")

                self.make_button(
                    row,
                    "Delete",
                    lambda n=name: remove_category(n),
                    "#3A2020"
                ).pack(side="right")

        def add_new_category():
            name = category_name.get().strip()

            if not name:
                messagebox.showwarning(
                    "Missing Name",
                    "Enter a category name."
                )
                return

            try:
                add_category(
                    name, category_type.get()
                )

                category_name.set("")
                refresh_categories()

            except Exception as error:
                messagebox.showerror(
                    "Category Error", str(error)
                )

        def remove_category(name):
            confirmed = messagebox.askyesno(
                "Delete Category",
                f"Delete the category '{name}'?\n\n"
                "Existing transactions will not be deleted."
            )

            if confirmed:
                try:
                    delete_category(
                        name, category_type.get()
                    )
                    refresh_categories()
                except Exception as error:
                    messagebox.showerror(
                        "Category Error", str(error)
                    )

        self.make_button(
            category_controls,
            "Add Category",
            add_new_category,
            color="#7C3AED"
        ).pack(side="left")

        category_type.trace_add(
            "write",
            lambda *args: refresh_categories()
        )

        refresh_categories()

        backup_card = self.make_card(
            self.content, "DATABASE BACKUP"
        )
        backup_card.pack(fill="x")

        tk.Label(
            backup_card,
            text="Save a copy of your local financial database.",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 9)
        ).pack(
            anchor="w", padx=18, pady=(0, 12)
        )

        self.make_button(
            backup_card,
            "Create Database Backup",
            self.create_backup
        ).pack(
            anchor="w", padx=18, pady=(0, 18)
        )

    def create_backup(self):
        destination = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite database", "*.db")],
            initialfile="finance_backup.db"
        )

        if destination:
            try:
                backup_database(destination)

                messagebox.showinfo(
                    "Backup Complete",
                    f"Database backup saved to:\n{destination}"
                )

            except Exception as error:
                messagebox.showerror(
                    "Backup Error", str(error)
                )


# ============================================================
# START APPLICATION
# ============================================================
if __name__ == "__main__":
    root = tk.Tk()

    if getattr(sys, "frozen", False):
        app_dir = Path(sys._MEIPASS)
    else:
        app_dir = Path(__file__).resolve().parent

    icon_path = app_dir / "FinanceFlow.ico"

    if icon_path.exists():
        root.iconbitmap(str(icon_path))

    app = FinanceFlow(root)
    root.mainloop()
