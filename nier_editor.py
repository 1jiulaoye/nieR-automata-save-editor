"""
尼尔存档修改器
GUI 主界面 — ttkbootstrap flatly 浅色主题
支持：金币修改 / 背包道具管理 / 武器管理 / 芯片管理
"""

import os
import sys

import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog

import ttkbootstrap as tb
import ttkbootstrap as ttk          # bootstyle 只对 ttkbootstrap 的控件生效（1.x / 2.x 都可用）
from ttkbootstrap.constants import *

from constants import *
from save_io import (
    SaveFile, SaveError, new_operation_id, find_backup_pairs,
    replace_files_atomically,
)
from item_data import (
    ITEM_NAMES, WEAPON_NAMES, CATEGORY_ORDER,
    get_item_name, get_weapon_name, get_category,
)
from chip_data import REGISTRY as CHIPS
from chip_data import CHIP_EFFECTS, CHIP_RECORD_SIZE


# ======================== 视觉规范 ========================

UI_BG = "#f6f7f9"           # 页面底色
UI_CARD = "#ffffff"         # 内容区白底
UI_BORDER = "#e5e7eb"       # 1px 分隔线 / 控件描边
UI_PRIMARY = "#2f6fed"      # 主色
UI_PRIMARY_DARK = "#2559c4"
UI_SUCCESS = "#16a34a"      # 成功色
UI_SUCCESS_DARK = "#12813b"
UI_TEXT = "#111827"
UI_MUTED = "#6b7280"
UI_SELECT = "#eaf0ff"
UI_FONT = "Microsoft YaHei"

SPACE_OUTER = 16            # 外边距
SPACE_BLOCK = 12            # 块间距
SPACE_INLINE = 8            # 行内间距


def _shorten_path(path: str, limit: int = 46) -> str:
    """路径过长时保留头尾、中间省略，避免把顶栏撑开。"""
    if len(path) <= limit:
        return path
    head = max(12, limit // 2 - 4)
    tail = max(12, limit - head - 1)
    return f"{path[:head]}…{path[-tail:]}"


def _enable_dpi_awareness() -> None:
    """在创建 Tk 之前声明 DPI 感知，避免 Windows 位图缩放把窗口放大。

    只在 Windows 上执行；Linux/macOS 直接跳过。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass


def _query_dpi(root) -> float:
    """取当前屏幕 DPI（96 = 100%，144 = 150%）；取不到就按 96 处理。"""
    try:
        return float(root.winfo_fpixels("1i"))
    except Exception:
        return 96.0


def _fit_window_to_screen(screen_w: int, screen_h: int,
                          scale: float = 1.0) -> tuple[int, int, int, int]:
    """按屏幕尺寸与显示缩放计算窗口大小与居中位置：返回 (w, h, x, y)。

    scale = DPI / 96：100% → 1.0，150% → 1.5。窗口按逻辑尺寸等比放大，
    再被屏幕尺寸封顶，保证既不超出屏幕、也不会在高 DPI 屏上显得很小。
    """
    screen_w = max(1, int(screen_w))
    screen_h = max(1, int(screen_h))
    scale = min(3.0, max(1.0, float(scale)))
    w = min(int(940 * scale), int(screen_w * 0.92))
    h = min(int(660 * scale), int(screen_h * 0.86))
    x = max(0, (screen_w - w) // 2)
    y = max(0, (screen_h - h) // 2)
    return w, h, x, y


class NierSaveEditor:
    """主窗口"""

    def __init__(self):
        # 必须在 Tk 创建前声明 DPI 感知（仅 Windows 生效）
        _enable_dpi_awareness()

        self.root = tb.Window(themename="flatly")
        self.root.title("尼尔存档修改器")

        # 显示缩放：150% 屏幕下按 1.5 倍放大逻辑尺寸，同时让 Tk 按 DPI 渲染文字
        dpi = _query_dpi(self.root)
        self._ui_scale = min(3.0, max(1.0, dpi / 96.0))
        try:
            self.root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

        # 窗口尺寸随屏幕自适应：小屏不超出，大屏也不无限放大；居中显示
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w, win_h, win_x, win_y = _fit_window_to_screen(screen_w, screen_h, self._ui_scale)
        self.root.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")
        self.root.minsize(
            min(int(720 * self._ui_scale), int(screen_w * 0.9)),
            min(int(480 * self._ui_scale), int(screen_h * 0.85)),
        )
        self.root.resizable(True, True)
        self.root.configure(background=UI_BG)

        # 状态
        self.save_folder = tk.StringVar()
        self.cur_slot = tk.IntVar(value=0)
        self.gamedata: SaveFile | None = None
        self.slotdata: SaveFile | None = None
        self._loaded_slot = 0  # 当前加载的存档位
        self._money_items_dirty = False  # 金币/背包道具被改过
        self._weapons_dirty = False      # 武器表被改过
        self._chips_dirty = False        # 芯片被改过
        self._slot_buttons = []
        self._corpse_window = None
        self._money_font_size = 36
        self._money_entry_font_size = 11

        self._configure_fonts()
        self._configure_styles()
        self._build_ui()
        self._update_money_font()
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self._auto_detect_folder()

    # ======================== 全局样式 ========================

    def _configure_fonts(self):
        """全局 Microsoft YaHei 10（找不到字体时 Tk 会自动回退）。"""
        try:
            import tkinter.font as tkfont
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                         "TkHeadingFont", "TkCaptionFont"):
                try:
                    tkfont.nametofont(name).configure(family=UI_FONT, size=10)
                except Exception:
                    pass
        except Exception:
            pass

    def _configure_styles(self):
        style = ttk.Style()
        style.configure(
            ".", font=(UI_FONT, 10), background=UI_BG, foreground=UI_TEXT,
        )

        # 容器 / 文字
        style.configure("TFrame", background=UI_BG)
        style.configure("Card.TFrame", background=UI_CARD)
        style.configure("TopBar.TFrame", background=UI_CARD)
        style.configure("Status.TFrame", background=UI_CARD)
        style.configure("Card.TLabel", background=UI_CARD,
                        foreground=UI_TEXT, font=(UI_FONT, 10))
        style.configure("Field.TLabel", background=UI_CARD,
                        foreground=UI_MUTED, font=(UI_FONT, 9))
        style.configure("Path.TLabel", background=UI_CARD,
                        foreground=UI_MUTED, font=(UI_FONT, 9))
        style.configure("Muted.TLabel", background=UI_CARD,
                        foreground=UI_MUTED, font=(UI_FONT, 9))
        style.configure("Count.TLabel", background=UI_CARD,
                        foreground=UI_MUTED, font=(UI_FONT, 9))
        style.configure("Section.TLabel", background=UI_CARD,
                        foreground=UI_TEXT, font=(UI_FONT, 12, "bold"))
        style.configure("Money.TLabel", background=UI_CARD,
                        foreground=UI_TEXT,
                        font=(UI_FONT, -self._money_font_size, "bold"))

        # 按钮
        style.configure(
            "Primary.TButton", background=UI_PRIMARY, foreground="#ffffff",
            bordercolor=UI_PRIMARY, focuscolor=UI_PRIMARY,
            padding=(14, 7), font=(UI_FONT, 10),
        )
        style.map(
            "Primary.TButton",
            background=[("pressed", UI_PRIMARY_DARK),
                        ("active", UI_PRIMARY_DARK)],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure(
            "Success.TButton", background=UI_SUCCESS, foreground="#ffffff",
            bordercolor=UI_SUCCESS, focuscolor=UI_SUCCESS,
            padding=(14, 7), font=(UI_FONT, 10),
        )
        style.map(
            "Success.TButton",
            background=[("pressed", UI_SUCCESS_DARK),
                        ("active", UI_SUCCESS_DARK)],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure(
            "Ghost.TButton", background=UI_CARD, foreground=UI_TEXT,
            bordercolor=UI_BORDER, focuscolor=UI_BORDER,
            padding=(12, 7), font=(UI_FONT, 10),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#f3f4f6"), ("pressed", "#e5e7eb")],
            foreground=[("active", UI_TEXT)],
        )
        style.configure(
            "Danger.TButton", background=UI_CARD, foreground="#dc2626",
            bordercolor="#fecaca", focuscolor="#fecaca",
            padding=(12, 7), font=(UI_FONT, 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#fef2f2"), ("pressed", "#fee2e2")],
            foreground=[("active", "#b91c1c")],
        )
        style.configure(
            "Slot.TButton", background=UI_CARD, foreground=UI_TEXT,
            bordercolor=UI_BORDER, focuscolor=UI_BORDER,
            padding=(6, 5), font=(UI_FONT, 10),
        )
        style.map(
            "Slot.TButton",
            background=[("active", "#f3f4f6")],
            foreground=[("active", UI_TEXT)],
        )
        style.configure(
            "SlotActive.TButton", background=UI_PRIMARY, foreground="#ffffff",
            bordercolor=UI_PRIMARY, focuscolor=UI_PRIMARY,
            padding=(6, 5), font=(UI_FONT, 10, "bold"),
        )
        style.map(
            "SlotActive.TButton",
            background=[("active", UI_PRIMARY_DARK),
                        ("pressed", UI_PRIMARY_DARK)],
        )
        style.configure(
            "Backup.TMenubutton", background=UI_CARD, foreground=UI_TEXT,
            bordercolor=UI_BORDER, focuscolor=UI_BORDER,
            padding=(12, 6), font=(UI_FONT, 10),
        )
        style.map(
            "Backup.TMenubutton",
            background=[("active", "#f3f4f6"), ("pressed", "#e5e7eb")],
            foreground=[("active", UI_TEXT)],
        )
        style.configure(
            "Link.TButton", background=UI_CARD, foreground=UI_MUTED,
            borderwidth=0, relief="flat", padding=(6, 4),
            font=(UI_FONT, 9),
        )
        style.map(
            "Link.TButton",
            background=[("active", UI_CARD)],
            foreground=[("active", UI_PRIMARY)],
        )

        # 输入控件
        style.configure(
            "TEntry", fieldbackground=UI_CARD, foreground=UI_TEXT,
            bordercolor=UI_BORDER, lightcolor=UI_BORDER,
            darkcolor=UI_BORDER, padding=5,
        )
        style.configure(
            "TSpinbox", fieldbackground=UI_CARD, foreground=UI_TEXT,
            bordercolor=UI_BORDER, arrowcolor=UI_MUTED, padding=4,
        )
        style.configure(
            "TCombobox", fieldbackground=UI_CARD, background=UI_CARD,
            foreground=UI_TEXT, bordercolor=UI_BORDER,
            arrowcolor=UI_MUTED, padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", UI_CARD)],
            foreground=[("readonly", UI_TEXT)],
            selectbackground=[("readonly", UI_CARD)],
            selectforeground=[("readonly", UI_TEXT)],
        )
        style.configure(
            "TCheckbutton", background=UI_CARD, foreground=UI_MUTED,
            font=(UI_FONT, 9), padding=(2, 0),
        )
        style.map(
            "TCheckbutton",
            background=[("active", UI_CARD)],
            foreground=[("active", UI_TEXT)],
        )
        style.configure("TSeparator", background=UI_BORDER)

        # 列表
        style.configure(
            "Treeview", background=UI_CARD, fieldbackground=UI_CARD,
            foreground=UI_TEXT, rowheight=30, borderwidth=0,
            font=(UI_FONT, 10),
        )
        style.configure(
            "Treeview.Heading", background="#f9fafb", foreground=UI_MUTED,
            font=(UI_FONT, 9, "bold"), relief="flat", padding=(8, 7),
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", UI_SELECT)],
            foreground=[("selected", UI_TEXT)],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#f3f4f6")],
            foreground=[("active", UI_TEXT)],
        )

        # Notebook
        style.configure(
            "TNotebook", background=UI_BG, borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab", background=UI_BG, foreground=UI_MUTED,
            padding=(18, 8), font=(UI_FONT, 10), borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", UI_CARD)],
            foreground=[("selected", UI_PRIMARY)],
        )

        # 下拉列表配色（Tk 原生 Listbox）
        try:
            self.root.option_add("*TCombobox*Listbox.background", UI_CARD)
            self.root.option_add("*TCombobox*Listbox.foreground", UI_TEXT)
            self.root.option_add("*TCombobox*Listbox.selectBackground", UI_SELECT)
            self.root.option_add("*TCombobox*Listbox.selectForeground", UI_TEXT)
            self.root.option_add("*TCombobox*Listbox.font", (UI_FONT, 10))
        except Exception:
            pass

    # ======================== UI 构建 ========================

    def _build_ui(self):
        # 根布局用 grid：顶栏/状态栏按内容取高，只有中间 notebook 伸缩。
        # 这样即使窗口很矮，状态栏和「备份 ▾」也不会被 notebook 顶出窗口。
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # 1) 顶栏：白底 + 1px 底部分隔线（高度随内容，不写死）
        topbar = ttk.Frame(self.root, style="TopBar.TFrame")
        topbar.grid(row=0, column=0, sticky="ew")

        top_line = tk.Frame(self.root, background=UI_BORDER, height=1)
        top_line.grid(row=1, column=0, sticky="ew")

        top_inner = ttk.Frame(topbar, style="TopBar.TFrame")
        top_inner.pack(fill=BOTH, expand=True, padx=SPACE_OUTER)

        left = ttk.Frame(top_inner, style="TopBar.TFrame")
        left.pack(side=LEFT, fill=Y)

        ttk.Button(
            left, text="打开存档文件夹", style="Primary.TButton",
            command=self._browse_folder,
        ).pack(side=LEFT, pady=11)

        self.path_label = ttk.Label(
            left, text="未选择存档文件夹", style="Path.TLabel",
        )
        self.path_label.pack(side=LEFT, padx=(SPACE_BLOCK, 0), pady=18)
        self.save_folder.trace_add("write", lambda *_: self._update_path_label())

        right = ttk.Frame(top_inner, style="TopBar.TFrame")
        right.pack(side=RIGHT, fill=Y)

        ttk.Button(
            right, text="保存修改", style="Success.TButton",
            command=self._save_all,
        ).pack(side=RIGHT, padx=(SPACE_BLOCK, 0), pady=11)

        slot_box = ttk.Frame(right, style="TopBar.TFrame")
        slot_box.pack(side=RIGHT, pady=11)
        for i in range(3):
            btn = ttk.Button(
                slot_box, text=str(i + 1), width=3, style="Slot.TButton",
                command=lambda i=i: self._on_slot_clicked(i),
            )
            btn.pack(side=LEFT, padx=(0 if i == 0 else 6, 0))
            self._slot_buttons.append(btn)

        # 2) 内容区：四个 tab
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(
            row=2, column=0, sticky="nsew",
            padx=SPACE_OUTER, pady=SPACE_BLOCK,
        )

        self.money_tab = ttk.Frame(
            self.notebook, style="Card.TFrame", padding=24,
        )
        self.notebook.add(self.money_tab, text="金币")
        self._build_money_tab()

        self.item_tab = ttk.Frame(
            self.notebook, style="Card.TFrame", padding=16,
        )
        self.notebook.add(self.item_tab, text="道具")
        self._build_item_tab()

        self.weapon_tab = ttk.Frame(
            self.notebook, style="Card.TFrame", padding=16,
        )
        self.notebook.add(self.weapon_tab, text="武器")
        self._build_weapon_tab()

        self.chip_tab = ttk.Frame(
            self.notebook, style="Card.TFrame", padding=16,
        )
        self.notebook.add(self.chip_tab, text="芯片")
        self._build_chip_tab()

        # 3) 状态栏：左侧状态 + 右侧「备份 ▾」；按内容取高，始终完整可见
        status_line = tk.Frame(self.root, background=UI_BORDER, height=1)
        status_line.grid(row=3, column=0, sticky="ew")

        status = ttk.Frame(self.root, style="Status.TFrame")
        status.grid(row=4, column=0, sticky="ew")

        status_inner = ttk.Frame(status, style="Status.TFrame")
        status_inner.pack(fill=BOTH, expand=True, padx=SPACE_OUTER)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(
            status_inner, textvariable=self.status_var, style="Muted.TLabel",
        ).pack(side=LEFT, pady=7)

        backup_btn = ttk.Menubutton(
            status_inner, text="备份 ▾", style="Backup.TMenubutton",
        )
        backup_menu = tk.Menu(backup_btn, tearoff=0, font=(UI_FONT, 10))
        backup_menu.add_command(label="手动备份", command=self._manual_backup)
        backup_menu.add_command(label="恢复备份", command=self._restore_backup)
        backup_btn.configure(menu=backup_menu)
        backup_btn.pack(side=RIGHT, pady=6)

        self._update_slot_buttons()
        self._update_path_label()

    def _on_root_configure(self, event):
        """窗口尺寸变化时，按当前高度收缩金币大字号/输入行。"""
        if event.widget is not self.root:
            return
        self._update_money_font(event.height)

    def _update_money_font(self, height=None):
        if height is None:
            height = self.root.winfo_height()
        try:
            height = max(1, int(height))
        except (TypeError, ValueError):
            height = 1
        # 600px 以上用 36px；窗口越矮字号越小，但绝不低于 24px
        scale = getattr(self, "_ui_scale", 1.0)
        money_px = int(max(24, min(36, int(height * 0.06))) * scale)
        entry_pt = max(9, min(11, money_px // 3))
        width = max(10, min(14, int(self.root.winfo_width() / 72)))
        state = (money_px, entry_pt, width)
        if getattr(self, "_money_font_state", None) == state:
            return
        self._money_font_state = state
        self._money_font_size = money_px
        self._money_entry_font_size = entry_pt
        try:
            ttk.Style().configure(
                "Money.TLabel", background=UI_CARD, foreground=UI_TEXT,
                font=(UI_FONT, -money_px, "bold"),
            )
        except Exception:
            pass
        entry = getattr(self, "money_entry", None)
        if entry is not None:
            try:
                entry.configure(font=(UI_FONT, entry_pt), width=width)
            except Exception:
                pass

    def _update_path_label(self):
        if not hasattr(self, "path_label"):
            return
        path = self.save_folder.get().strip()
        self.path_label.configure(
            text=_shorten_path(path) if path else "未选择存档文件夹",
        )

    def _update_slot_buttons(self):
        if not getattr(self, "_slot_buttons", None):
            return
        current = self.cur_slot.get()
        for i, btn in enumerate(self._slot_buttons):
            btn.configure(
                style="SlotActive.TButton" if i == current else "Slot.TButton",
            )

    def _on_slot_clicked(self, slot: int):
        if slot == self.cur_slot.get():
            self._update_slot_buttons()
            return
        self.cur_slot.set(slot)
        self._update_slot_buttons()
        self._switch_slot()
        self._update_slot_buttons()

    # ======================== 金币 Tab ========================

    def _build_money_tab(self):
        center = ttk.Frame(self.money_tab, style="Card.TFrame")
        center.pack(expand=True)

        ttk.Label(
            center, text="当前金币", style="Field.TLabel",
        ).pack(pady=(0, 6))

        self.money_label = ttk.Label(
            center, text="尚未加载存档", style="Money.TLabel",
        )
        self.money_label.pack(pady=(0, 20))

        row = ttk.Frame(center, style="Card.TFrame")
        row.pack()
        self.money_entry = ttk.Entry(
            row, width=14, justify=CENTER, font=(UI_FONT, 11),
        )
        self.money_entry.pack(side=LEFT, padx=(0, SPACE_INLINE))
        ttk.Button(
            row, text="设为", style="Primary.TButton",
            command=self._set_money,
        ).pack(side=LEFT, padx=(0, SPACE_INLINE))
        ttk.Button(
            row, text="填满最大", style="Ghost.TButton",
            command=self._fill_max_money,
        ).pack(side=LEFT)

        ttk.Label(
            center, text=f"可设置范围 0 ~ {MAX_MONEY:,} G", style="Muted.TLabel",
        ).pack(pady=(SPACE_BLOCK, 0))

    # ======================== 道具 Tab ========================

    def _build_item_tab(self):
        # 顶部：搜索 / 分类 / 显示全部 + 添加道具。
        # 窄窗口下拆成两行（每行仍可横向排布），避免右侧「添加」被 720px 挤掉。
        top = ttk.Frame(self.item_tab, style="Card.TFrame")
        top.pack(fill=X, pady=(0, SPACE_BLOCK))

        top_filter = ttk.Frame(top, style="Card.TFrame")
        top_filter.pack(fill=X, side=tk.TOP)

        ttk.Label(top_filter, text="搜索", style="Field.TLabel").pack(side=LEFT)
        self.item_search_var = tk.StringVar()
        ttk.Entry(
            top_filter, textvariable=self.item_search_var, width=22,
        ).pack(side=LEFT, padx=(6, SPACE_BLOCK))
        self.item_search_var.trace_add("write", lambda *_: self._refresh_items())

        ttk.Label(top_filter, text="分类", style="Field.TLabel").pack(side=LEFT)
        self.item_cat_var = tk.StringVar(value="全部")
        cats = ["全部"] + list(CATEGORY_ORDER)
        cat_cb = ttk.Combobox(
            top_filter, textvariable=self.item_cat_var, values=cats,
            width=12, state="readonly",
        )
        cat_cb.pack(side=LEFT, padx=(6, SPACE_BLOCK))
        cat_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_items())

        self.show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top_filter, text="显示全部", variable=self.show_all_var,
            command=self._refresh_items,
        ).pack(side=LEFT)

        top_add = ttk.Frame(top, style="Card.TFrame")
        top_add.pack(fill=X, side=tk.TOP, pady=(SPACE_INLINE, 0))
        ttk.Label(top_add, text="添加道具", style="Field.TLabel").pack(side=LEFT)
        self.item_add_var = tk.StringVar()
        all_items = sorted(ITEM_NAMES.items(), key=lambda x: x[1])
        item_names = [f"{n} (0x{i:04X})" for i, n in all_items]
        self.item_add_cb = ttk.Combobox(
            top_add, textvariable=self.item_add_var, values=item_names,
            width=30, state="readonly",
        )
        self.item_add_cb.pack(side=LEFT, padx=(6, SPACE_INLINE))
        ttk.Button(
            top_add, text="添加", style="Success.TButton",
            command=self._add_item,
        ).pack(side=LEFT)

        # 底部先占位：矮窗口时优先保证「增加/减少/设为/尸体背包」可见
        bottom = ttk.Frame(self.item_tab, style="Card.TFrame")
        bottom.pack(fill=X, side=tk.BOTTOM, pady=(SPACE_BLOCK, 0))

        self.item_amount_var = tk.StringVar(value="1")
        ttk.Label(bottom, text="数量", style="Field.TLabel").pack(side=LEFT)
        ttk.Entry(
            bottom, textvariable=self.item_amount_var, width=8,
            justify=CENTER,
        ).pack(side=LEFT, padx=(6, SPACE_INLINE))
        ttk.Button(
            bottom, text="增加", style="Ghost.TButton",
            command=lambda: self._mod_item(1),
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            bottom, text="减少", style="Ghost.TButton",
            command=lambda: self._mod_item(-1),
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            bottom, text="设为", style="Primary.TButton",
            command=lambda: self._mod_item(0),
        ).pack(side=LEFT)

        ttk.Button(
            bottom, text="尸体背包（只读）", style="Link.TButton",
            command=self._open_corpse_window,
        ).pack(side=RIGHT)

        # 中间：列表（最后 pack，吃掉剩余空间）
        list_wrap = ttk.Frame(self.item_tab, style="Card.TFrame")
        list_wrap.pack(fill=BOTH, expand=True)
        cols = ("名称", "数量", "ID")
        self.item_tree = ttk.Treeview(
            list_wrap, columns=cols, show="headings", height=10,
            selectmode="browse",
        )
        self.item_tree.heading("名称", text="名称")
        self.item_tree.heading("数量", text="数量")
        self.item_tree.heading("ID", text="ID")
        self.item_tree.column("名称", width=340, anchor="w")
        self.item_tree.column("数量", width=90, anchor=CENTER)
        self.item_tree.column("ID", width=110, anchor=CENTER)
        self.item_tree.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            list_wrap, orient=VERTICAL, command=self.item_tree.yview,
        )
        self.item_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

    # ======================== 武器 Tab ========================

    def _build_weapon_tab(self):
        # 顶部：已获得计数
        head = ttk.Frame(self.weapon_tab, style="Card.TFrame")
        head.pack(fill=X, pady=(0, SPACE_INLINE))
        ttk.Label(head, text="已获得", style="Field.TLabel").pack(side=LEFT)
        self.weapon_count_label = ttk.Label(
            head, text=f"0 / {WEAPONS_COUNT}", style="Count.TLabel",
        )
        self.weapon_count_label.pack(side=LEFT, padx=(6, 0))

        # 底部先占位：矮窗口时优先保证等级 / 添加 / 删除可见
        bar = ttk.Frame(self.weapon_tab, style="Card.TFrame")
        bar.pack(fill=X, side=tk.BOTTOM, pady=(SPACE_BLOCK, 0))

        ttk.Label(bar, text="等级 1-4", style="Field.TLabel").pack(side=LEFT)
        self.weapon_level_var = tk.IntVar(value=1)
        self.weapon_level_spin = ttk.Spinbox(
            bar, from_=WEAPON_LEVEL_MIN, to=WEAPON_LEVEL_MAX,
            textvariable=self.weapon_level_var, width=4, justify=CENTER,
        )
        self.weapon_level_spin.pack(side=LEFT, padx=(6, SPACE_INLINE))
        ttk.Button(
            bar, text="保存等级", style="Primary.TButton",
            command=self._set_weapon_level,
        ).pack(side=LEFT)

        ttk.Separator(bar, orient=VERTICAL).pack(
            side=LEFT, fill=Y, padx=SPACE_OUTER, pady=2,
        )

        self.weapon_add_var = tk.StringVar()
        weapon_names = [f"{n} (0x{i:04X})"
                        for i, n in sorted(WEAPON_NAMES.items(), key=lambda x: x[1])]
        self.weapon_add_cb = ttk.Combobox(
            bar, textvariable=self.weapon_add_var,
            values=weapon_names, width=26, state="readonly",
        )
        self.weapon_add_cb.pack(side=LEFT, padx=(0, SPACE_INLINE))
        ttk.Button(
            bar, text="添加", style="Success.TButton",
            command=self._add_weapon,
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            bar, text="删除", style="Danger.TButton",
            command=self._remove_weapon,
        ).pack(side=LEFT)

        # 中间：列表（最后 pack，吃掉剩余空间）
        list_wrap = ttk.Frame(self.weapon_tab, style="Card.TFrame")
        list_wrap.pack(fill=BOTH, expand=True)
        cols = ("名称", "等级", "状态", "ID")
        self.weapon_tree = ttk.Treeview(
            list_wrap, columns=cols, show="headings", height=10,
            selectmode="browse",
        )
        self.weapon_tree.heading("名称", text="名称")
        self.weapon_tree.heading("等级", text="等级")
        self.weapon_tree.heading("状态", text="状态")
        self.weapon_tree.heading("ID", text="ID")
        self.weapon_tree.column("名称", width=340, anchor="w")
        self.weapon_tree.column("等级", width=80, anchor=CENTER)
        self.weapon_tree.column("状态", width=100, anchor=CENTER)
        self.weapon_tree.column("ID", width=110, anchor=CENTER)
        self.weapon_tree.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            list_wrap, orient=VERTICAL, command=self.weapon_tree.yview,
        )
        self.weapon_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

    # ======================== 尸体背包（只读弹窗） ========================

    def _open_corpse_window(self):
        """四 tab 之外的只读尸体背包，按需打开，不占用主界面。"""
        win = self._corpse_window
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_set()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self.root)
        self._corpse_window = win
        win.title("尸体背包（只读）")
        win.geometry("640x480")
        win.minsize(520, 360)
        win.configure(background=UI_BG)
        try:
            win.transient(self.root)
        except Exception:
            pass

        card = ttk.Frame(win, style="Card.TFrame", padding=16)
        card.pack(fill=BOTH, expand=True, padx=SPACE_OUTER, pady=SPACE_OUTER)

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill=X, pady=(0, SPACE_INLINE))
        ttk.Label(
            head, text="尸体背包（只读）", style="Section.TLabel",
        ).pack(side=LEFT)
        self.corpse_count_label = ttk.Label(
            head, text="0 条", style="Count.TLabel",
        )
        self.corpse_count_label.pack(side=RIGHT)

        list_wrap = ttk.Frame(card, style="Card.TFrame")
        list_wrap.pack(fill=BOTH, expand=True)
        cols = ("名称", "数量", "ID")
        self.corpse_tree = ttk.Treeview(
            list_wrap, columns=cols, show="headings", height=12,
            selectmode="browse",
        )
        self.corpse_tree.heading("名称", text="名称")
        self.corpse_tree.heading("数量", text="数量")
        self.corpse_tree.heading("ID", text="ID")
        self.corpse_tree.column("名称", width=300, anchor="w")
        self.corpse_tree.column("数量", width=90, anchor=CENTER)
        self.corpse_tree.column("ID", width=110, anchor=CENTER)
        self.corpse_tree.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            list_wrap, orient=VERTICAL, command=self.corpse_tree.yview,
        )
        self.corpse_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

        win.protocol("WM_DELETE_WINDOW", self._close_corpse_window)
        self._refresh_corpse()

    def _close_corpse_window(self):
        try:
            if self._corpse_window is not None:
                self._corpse_window.destroy()
        except Exception:
            pass
        self._corpse_window = None
        self.corpse_tree = None
        self.corpse_count_label = None

    # ======================== 芯片 Tab ========================

    def _build_chip_tab(self):
        # 顶部：搜索 / 分类 + 右侧已装计数
        top = ttk.Frame(self.chip_tab, style="Card.TFrame")
        top.pack(fill=X, pady=(0, SPACE_BLOCK))

        ttk.Label(top, text="搜索", style="Field.TLabel").pack(side=LEFT)
        self.chip_search_var = tk.StringVar()
        ttk.Entry(
            top, textvariable=self.chip_search_var, width=22,
        ).pack(side=LEFT, padx=(6, SPACE_BLOCK))
        self.chip_search_var.trace_add("write", lambda *_: self._refresh_chips())

        ttk.Label(top, text="分类", style="Field.TLabel").pack(side=LEFT)
        self.chip_cat_var = tk.StringVar(value="全部")
        chip_cats = ["全部", "攻击", "防御", "辅助", "HUD", "特殊"]
        cat_cb = ttk.Combobox(
            top, textvariable=self.chip_cat_var, values=chip_cats,
            width=10, state="readonly",
        )
        cat_cb.pack(side=LEFT, padx=(6, 0))
        cat_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_chips())

        self.chip_count_label = ttk.Label(
            top, text=f"0 / {CHIPS_COUNT}", style="Count.TLabel",
        )
        self.chip_count_label.pack(side=RIGHT)
        ttk.Label(top, text="已装", style="Field.TLabel").pack(
            side=RIGHT, padx=(0, 6),
        )

        # 底部先占位：矮窗口时优先保证芯片下拉 + 等级 + 添加 / 删除可见
        bar = ttk.Frame(self.chip_tab, style="Card.TFrame")
        bar.pack(fill=X, side=tk.BOTTOM, pady=(SPACE_BLOCK, 0))

        self.chip_add_var = tk.StringVar()
        common_names = sorted(CHIPS.common_names)
        unique_names = sorted(CHIPS.unique_names)
        all_chip_names = common_names + unique_names
        self.chip_add_cb = ttk.Combobox(
            bar, textvariable=self.chip_add_var,
            values=all_chip_names, width=26, state="readonly",
        )
        self.chip_add_cb.pack(side=LEFT, padx=(0, SPACE_INLINE))
        # 选中系统/唯一芯片时，等级由芯片本身固定，禁用等级输入并给出提示
        self.chip_add_cb.bind(
            "<<ComboboxSelected>>", lambda e: self._on_chip_add_selected(),
        )

        ttk.Label(bar, text="等级", style="Field.TLabel").pack(side=LEFT)
        self.chip_lv_var = tk.IntVar(value=0)
        self.chip_lv_spin = ttk.Spinbox(
            bar, from_=0, to=8, textvariable=self.chip_lv_var,
            width=4, justify=CENTER,
        )
        self.chip_lv_spin.pack(side=LEFT, padx=(6, SPACE_INLINE))
        self.chip_lv_hint = ttk.Label(
            bar, text="", style="Muted.TLabel",
        )
        self.chip_lv_hint.pack(side=LEFT, padx=(0, SPACE_INLINE))

        ttk.Button(
            bar, text="添加", style="Success.TButton",
            command=self._add_chip,
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            bar, text="删除", style="Danger.TButton",
            command=self._remove_chip,
        ).pack(side=LEFT)

        # 中间：列表（最后 pack，吃掉剩余空间）
        list_wrap = ttk.Frame(self.chip_tab, style="Card.TFrame")
        list_wrap.pack(fill=BOTH, expand=True)
        cols = ("名称", "等级", "格数", "效果")
        self.chip_tree = ttk.Treeview(
            list_wrap, columns=cols, show="headings", height=10,
            selectmode="browse",
        )
        self.chip_tree.heading("名称", text="名称")
        self.chip_tree.heading("等级", text="等级")
        self.chip_tree.heading("格数", text="格数")
        self.chip_tree.heading("效果", text="效果")
        self.chip_tree.column("名称", width=260, anchor="w")
        self.chip_tree.column("等级", width=70, anchor=CENTER)
        self.chip_tree.column("格数", width=60, anchor=CENTER)
        self.chip_tree.column("效果", width=380, anchor="w")
        self.chip_tree.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            list_wrap, orient=VERTICAL, command=self.chip_tree.yview,
        )
        self.chip_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

    # ======================== 数据加载 ========================

    def _auto_detect_folder(self):
        """自动检测存档文件夹"""
        home = os.path.expanduser("~")
        # 尝试多个可能的路径
        candidates = [
            os.path.join(home, "Documents", SAVE_PARENT, SAVE_FOLDER_NAME),
            os.path.join(home, "文档", SAVE_PARENT, SAVE_FOLDER_NAME),
        ]
        # 也搜一下 OneDrive
        for prefix in ["", "OneDrive\\", "OneDrive\\文档\\", "OneDrive\\Documents\\"]:
            candidates.append(os.path.join(home, prefix, SAVE_PARENT, SAVE_FOLDER_NAME))

        gd = GAMEDATA_FILE
        for guess in candidates:
            if os.path.isfile(os.path.join(guess, gd)):
                self.save_folder.set(guess)
                self._refresh()
                return
        self.status_var.set("未找到存档文件夹，请手动浏览选择")
        # 给个提示
        self.money_label.config(text="请选择存档文件夹")

    def _browse_folder(self):
        path = filedialog.askdirectory(title="选择 NieR_Automata 存档文件夹")
        if path:
            self.save_folder.set(path)
            self._refresh()

    def _refresh(self):
        """重新加载所有数据"""
        folder = self.save_folder.get()
        gd_path = os.path.join(folder, GAMEDATA_FILE)
        if not os.path.isfile(gd_path):
            msg = f"在此路径未找到 GameData.dat：\n{folder}\n\n请确认该文件夹包含：\n  GameData.dat\n  SlotData_0.dat\n  SlotData_1.dat\n  SlotData_2.dat"
            self.status_var.set(f"未找到存档")
            self.money_label.config(text="未找到存档")
            messagebox.showwarning("找不到存档", msg)
            return
        # 显示文件大小
        fsize = os.path.getsize(gd_path)
        self.status_var.set(f"正在加载 {GAMEDATA_FILE}（{fsize:,} 字节）...")
        try:
            self.gamedata = SaveFile(gd_path)
            self._switch_slot()
            self.status_var.set(f"已加载存档 — {len(self.gamedata._data):,} 字节")
        except SaveError as e:
            self.gamedata = None
            self.status_var.set("存档格式不符，已拒绝载入")
            messagebox.showerror("不是有效的存档", str(e))
        except Exception as e:
            self.status_var.set(f"加载失败: {e}")
            messagebox.showerror("加载失败", str(e))

    def _switch_slot(self):
        """切换存档位；用户确认丢弃修改时，必须把 GameData 从磁盘重新载入。"""
        self._update_slot_buttons()
        if not self.gamedata:
            return
        new_slot = self.cur_slot.get()
        # 检查未保存修改
        discard = False
        if self._money_items_dirty or self._weapons_dirty or self._chips_dirty:
            if not messagebox.askyesno("未保存的修改", "当前有未保存的修改，切换存档位将丢失。\n继续吗？"):
                self.cur_slot.set(self._loaded_slot)
                self._update_slot_buttons()
                return
            discard = True

        folder = self.save_folder.get()
        gd_path = os.path.join(folder, GAMEDATA_FILE)

        # A1：确认丢弃后，从磁盘重新载入 GameData，清掉旧槽位的内存修改。
        # 载入失败则取消切换，保持原存档位与原对象不变。
        if discard:
            try:
                self.gamedata = SaveFile(gd_path)
            except Exception as e:
                self.cur_slot.set(self._loaded_slot)
                self._update_slot_buttons()
                self.status_var.set("切换已取消：GameData 重新载入失败")
                messagebox.showerror(
                    "切换失败",
                    f"重新载入 {GAMEDATA_FILE} 失败，已取消切换：\n{e}"
                )
                return
            self._money_items_dirty = False
            self._weapons_dirty = False
            self._chips_dirty = False

        slot_file = SLOT_FILES[new_slot]
        slot_path = os.path.join(folder, slot_file)
        self.slotdata = None
        if os.path.isfile(slot_path):
            try:
                self.slotdata = SaveFile(slot_path)
            except SaveError as e:
                self.status_var.set(f"{slot_file} 无效，已跳过")
                messagebox.showwarning("存档位无效", str(e))
        self._loaded_slot = new_slot
        self._money_items_dirty = False
        self._weapons_dirty = False
        self._chips_dirty = False
        self._refresh_money()
        self._refresh_items()
        self._refresh_weapons()
        self._refresh_corpse()
        self._refresh_chips()
        self._update_slot_buttons()

    # ======================== 金币操作 ========================

    def _refresh_money(self):
        try:
            # 优先从 SlotData 读取（游戏实际读这个）
            target = self.slotdata if self.slotdata else self.gamedata
            if target:
                money = target.get_money()
                self.money_label.config(text=f"{money:,} G")
                self.money_entry.delete(0, tk.END)
                self.money_entry.insert(0, str(money))
            else:
                self.money_label.config(text="—")
        except Exception as e:
            self.money_label.config(text="读取失败")
            self.status_var.set(f"金币读取异常: {e}")

    def _fill_max_money(self):
        """把输入框填成金币上限并立即应用。"""
        if not self.gamedata or not self.slotdata:
            return
        self.money_entry.delete(0, tk.END)
        self.money_entry.insert(0, str(MAX_MONEY))
        self._set_money()

    def _set_money(self):
        if not self.gamedata or not self.slotdata:
            return
        try:
            val = int(self.money_entry.get().replace(",", "").strip())
        except (ValueError, TypeError) as e:
            messagebox.showerror("输入错误", f"金币必须是 0 ~ {MAX_MONEY:,} 的整数")
            return
        if not 0 <= val <= MAX_MONEY:
            messagebox.showerror("输入错误", f"金币必须是 0 ~ {MAX_MONEY:,} 的整数")
            return
        # 同时写 GameData 和 SlotData 保持一致
        self.gamedata.set_money(val)
        self.slotdata.set_money(val)
        self._money_items_dirty = True
        self._refresh_money()
        self.status_var.set(f"金币已设为 {val:,} G（未保存）")

    # ======================== 道具操作 ========================

    def _refresh_items(self):
        try:
            # 优先从 SlotData 读取（游戏实际读这个），只读背包 256 条
            target = self.slotdata if self.slotdata else self.gamedata
            if not target:
                return
            for row in self.item_tree.get_children():
                self.item_tree.delete(row)

            query = self.item_search_var.get().lower()
            category = self.item_cat_var.get()
            show_all = self.show_all_var.get()

            all_items = target.get_items(limit=ITEMS_COUNT)
            for i, (iid, amt) in enumerate(all_items):
                if amt == 0 and not show_all:
                    continue
                name = get_item_name(iid)
                if query and query not in name.lower():
                    continue
                if category != "全部" and get_category(iid) != category:
                    continue
                # tags=(str(i),) 存储原始索引，避免重复 item_id 导致改错
                self.item_tree.insert("", END, values=(name, amt, f"0x{iid:04X}"),
                                      tags=(str(i),))
        except Exception as e:
            self.status_var.set(f"道具读取异常: {e}")

    def _get_selected_item_index(self) -> tuple[int, int, int]:
        """返回 (tree_index, item_id, amount) 或 (-1, 0, 0)，索引从 TreeView tags 获取"""
        sel = self.item_tree.selection()
        if not sel:
            return (-1, 0, 0)
        values = self.item_tree.item(sel[0], 'values')
        iid_str = values[2]
        iid = int(iid_str, 16)
        amt = int(values[1])
        # 从 tags 获取原始索引（避免重复 item_id 改错）
        tags = self.item_tree.item(sel[0], 'tags')
        if tags:
            return (int(tags[0]), iid, amt)
        return (-1, iid, amt)

    def _mod_item(self, direction: int):
        """direction: 1=增加, -1=减少, 0=设为指定值"""
        if not self.gamedata or not self.slotdata:
            return
        idx, iid, cur = self._get_selected_item_index()
        if idx < 0:
            messagebox.showwarning("未选中", "请先选择一个道具")
            return
        # A8：数量输入必须是 1..255 的整数；非法输入一律不写入
        try:
            amt_val = int(self.item_amount_var.get())
        except (ValueError, TypeError):
            messagebox.showwarning("输入错误", f"数量必须是 1-{MAX_ITEM_AMOUNT} 的整数")
            return
        if not (1 <= amt_val <= MAX_ITEM_AMOUNT):
            messagebox.showwarning("输入错误", f"数量必须是 1-{MAX_ITEM_AMOUNT} 的整数")
            return

        if direction == 1:
            new_amt = min(cur + amt_val, MAX_ITEM_AMOUNT)
        elif direction == -1:
            new_amt = max(cur - amt_val, 0)
        else:
            new_amt = min(max(amt_val, 0), MAX_ITEM_AMOUNT)

        # 同时写 GameData 和 SlotData 的背包区；任何异常都转成提示，不能逃出 Tk 回调
        try:
            self.gamedata.set_item(idx, iid, new_amt)
            self.slotdata.set_item(idx, iid, new_amt)
        except Exception as e:
            messagebox.showerror("修改失败", f"写入道具失败：{e}")
            return
        self._money_items_dirty = True
        self._refresh_items()
        self.status_var.set(f"道具 {get_item_name(iid)} → {new_amt}（未保存）")

    def _add_item(self):
        if not self.gamedata or not self.slotdata:
            return
        sel = self.item_add_var.get()
        if not sel:
            return
        # 解析 "名称 (0xID)"
        import re
        m = re.search(r'0x([0-9A-Fa-f]+)', sel)
        if not m:
            messagebox.showwarning("未知道具 ID", "请从下拉框选择有效道具")
            return
        iid = int(m.group(1), 16)
        # A10：下拉框只读 + 这里再校验一次，防止未知 ID（含 0xFFFF）被写进存档
        if iid not in ITEM_NAMES:
            messagebox.showwarning("未知道具 ID", f"未知道具 ID: 0x{iid:04X}")
            return

        # 以 SlotData 为权威添加背包道具，再同步到 GameData
        added = self.slotdata.add_or_update_item(iid, 1, limit=ITEMS_COUNT)
        if not added:
            if self.slotdata.get_item(iid) >= MAX_ITEM_AMOUNT:
                messagebox.showwarning("数量已满", "该道具数量已满（255），无法继续增加")
            else:
                messagebox.showwarning("槽位已满", "SlotData 道具槽位已满，无法添加")
            return
        # 同步到 GameData
        self.gamedata.sync_money_items_from(self.slotdata)
        self._money_items_dirty = True
        self._refresh_items()
        self.status_var.set(f"已添加 {get_item_name(iid)}（未保存）")

    # ======================== 武器操作 ========================

    def _weapon_target(self):
        """武器表优先从 SlotData 读写（GameData 的武器区只是占位）。"""
        return self.slotdata if self.slotdata else self.gamedata

    def _refresh_weapons(self):
        try:
            target = self._weapon_target()
            if not target:
                for row in self.weapon_tree.get_children():
                    self.weapon_tree.delete(row)
                return
            for row in self.weapon_tree.get_children():
                self.weapon_tree.delete(row)
            obtained = 0
            for w in target.get_weapons():
                if w['empty']:
                    name = "（空槽）"
                    level_text = "—"
                    status = "未获得"
                    id_text = ""
                else:
                    obtained += 1
                    name = w['name']
                    level_text = w['level']
                    status = "已获得"
                    id_text = f"0x{w['id']:04X}"
                self.weapon_tree.insert(
                    "", END, values=(name, level_text, status, id_text),
                    tags=(str(w['index']),),
                )
            self.weapon_count_label.config(
                text=f"{obtained} / {WEAPONS_COUNT}"
            )
        except Exception as e:
            self.status_var.set(f"武器读取异常: {e}")

    def _refresh_corpse(self):
        """只读展示 0x31170 起的尸体背包，绝不写入；弹窗未打开时直接跳过。"""
        tree = getattr(self, "corpse_tree", None)
        if tree is None:
            return
        label = getattr(self, "corpse_count_label", None)
        try:
            target = self.slotdata if self.slotdata else self.gamedata
            if not target:
                for row in tree.get_children():
                    tree.delete(row)
                if label is not None:
                    label.config(text="0 条")
                return
            for row in tree.get_children():
                tree.delete(row)
            count = 0
            for i, (iid, amt) in enumerate(target.get_corpse_items()):
                if amt <= 0 or iid == ITEM_EMPTY_ID:
                    continue
                count += 1
                tree.insert(
                    "", END,
                    values=(get_item_name(iid), amt, f"0x{iid:04X}"),
                    tags=(str(i),),
                )
            if label is not None:
                label.config(text=f"{count} 条")
        except Exception as e:
            self.status_var.set(f"尸体背包读取异常: {e}")

    def _get_selected_weapon_index(self) -> int:
        sel = self.weapon_tree.selection()
        if not sel:
            return -1
        tags = self.weapon_tree.item(sel[0], 'tags')
        return int(tags[0]) if tags else -1

    def _set_weapon_level(self):
        target = self._weapon_target()
        if not target:
            return
        idx = self._get_selected_weapon_index()
        if idx < 0:
            messagebox.showwarning("未选中", "请先选择一把武器")
            return
        try:
            level = int(self.weapon_level_var.get())
        except (ValueError, TypeError):
            messagebox.showwarning("输入错误", "武器等级必须是 1-4 的整数")
            return
        if not (WEAPON_LEVEL_MIN <= level <= WEAPON_LEVEL_MAX):
            messagebox.showwarning("输入错误", "武器等级必须是 1-4 的整数")
            return
        try:
            target.set_weapon_level(idx, level)
        except Exception as e:
            messagebox.showerror("修改失败", f"写入武器等级失败：{e}")
            return
        self._weapons_dirty = True
        self._refresh_weapons()
        self.status_var.set(f"武器等级 → {level}（未保存）")

    def _add_weapon(self):
        target = self._weapon_target()
        if not target:
            return
        sel = self.weapon_add_var.get()
        if not sel:
            return
        import re
        m = re.search(r'0x([0-9A-Fa-f]+)', sel)
        if not m:
            messagebox.showwarning("未知武器 ID", "请从下拉框选择有效武器")
            return
        wid = int(m.group(1), 16)
        if wid not in WEAPON_NAMES:
            messagebox.showwarning("未知武器 ID", f"未知武器 ID: 0x{wid:04X}")
            return
        if any((not w['empty']) and w['id'] == wid for w in target.get_weapons()):
            messagebox.showwarning("武器已拥有", "该武器已经拥有，不能重复添加")
            return
        if target.add_weapon(wid):
            self._weapons_dirty = True
            self._refresh_weapons()
            self.status_var.set(f"已添加武器 {get_weapon_name(wid)}（未保存）")
        else:
            messagebox.showwarning("武器槽已满", "39 个武器槽已满，无法添加")

    def _remove_weapon(self):
        target = self._weapon_target()
        if not target:
            return
        idx = self._get_selected_weapon_index()
        if idx < 0:
            messagebox.showwarning("未选中", "请先选择一把武器")
            return
        if not messagebox.askyesno("确认删除", "确定要删除这把武器吗？"):
            return
        try:
            target.remove_weapon(idx)
        except Exception as e:
            messagebox.showerror("删除失败", f"删除武器失败：{e}")
            return
        self._weapons_dirty = True
        self._refresh_weapons()
        self.status_var.set("武器已删除（未保存）")

    # ======================== 芯片操作 ========================

    def _refresh_chips(self):
        try:
            if not self.slotdata:
                for row in self.chip_tree.get_children():
                    self.chip_tree.delete(row)
                return
            for row in self.chip_tree.get_children():
                self.chip_tree.delete(row)

            query = self.chip_search_var.get().lower()
            category = self.chip_cat_var.get()

            installed = self.slotdata.get_installed_chips()
            for chip in installed:
                raw12 = chip['raw'][:12]
                try:
                    name = CHIPS.to_name(raw12)
                except Exception:
                    name = f"Unknown ({chip['chip_id_1']})"

                if query and query not in name.lower():
                    continue

                # 简单分类
                if category == "HUD" and not name.startswith("HUD"):
                    continue
                elif category == "攻击" and not any(k in name for k in ['攻击','暴击','冲击','蓄力','反击','气绝','炎上','远程操控']):
                    continue
                elif category == "防御" and not any(k in name for k in ['伤害减轻','连续伤害','耐冲击','HP最大','HP回复','伤害吸收','重新启动','濒死']):
                    continue
                elif category == "辅助" and not any(k in name for k in ['冷却','回避','速度','掉落','经验','复仇','超频','挑衅','自动']):
                    continue
                elif category == "特殊" and not any(k in name for k in ['OS','连击继续','敌弹诱爆','物品扫描','断末魔','子弹回避']):
                    continue

                # 查找效果描述
                base_name = name
                if " +" in name:
                    base_name = name[:name.rindex(" +")]
                effect = CHIP_EFFECTS.get(base_name, "")
                if not effect:
                    for k, v in CHIP_EFFECTS.items():
                        if name.startswith(k) or k.startswith(name):
                            effect = v
                            break

                lv_str = f"+{chip['level']}" if chip['level'] > 0 else "—"
                self.chip_tree.insert("", END, values=(name, lv_str, chip['size'], effect),
                                     tags=(str(chip['index']),))
            count = len(installed)
            self.chip_count_label.config(text=f"{count} / {CHIPS_COUNT}")
        except Exception as e:
            self.status_var.set(f"芯片读取异常: {e}")

    def _remove_chip(self):
        if not self.slotdata:
            return
        sel = self.chip_tree.selection()
        if not sel:
            messagebox.showwarning("未选中", "请先选择一个芯片")
            return
        if not messagebox.askyesno("确认删除", "确定要删除这个芯片吗？"):
            return
        idx = int(self.chip_tree.item(sel[0], 'tags')[0])
        self.slotdata.remove_chip(idx)
        self._chips_dirty = True
        self._refresh_chips()
        self.status_var.set("芯片已删除（未保存）")

    def _on_chip_add_selected(self):
        """A11：系统/唯一芯片等级固定，禁用等级输入并提示；普通芯片恢复可用。"""
        name = self.chip_add_var.get()
        if name in CHIPS.unique_names:
            self.chip_lv_spin.configure(state="disabled")
            self.chip_lv_hint.config(text="该系统芯片固定等级")
        else:
            self.chip_lv_spin.configure(state="normal")
            self.chip_lv_hint.config(text="")

    def _add_chip(self):
        if not self.slotdata:
            return
        try:
            name = self.chip_add_var.get()
            if not name:
                return

            # A11：系统/唯一芯片忽略等级输入（记录里自带固定等级）
            if name in CHIPS.unique_names:
                full_name = name
            else:
                level = int(self.chip_lv_var.get())
                if not 0 <= level <= 8:
                    messagebox.showwarning("输入错误", "等级必须是 0-8")
                    return
                # 普通芯片 +0 不加后缀，+1~+8 加后缀
                full_name = name if level == 0 else f"{name} +{level}"

            chip_bytes = CHIPS.to_bytes(full_name)
            if len(chip_bytes) != CHIP_RECORD_SIZE:
                raise ValueError(f"芯片记录长度错误：{len(chip_bytes)}，应为 {CHIP_RECORD_SIZE}")

            if self.slotdata.add_chip(chip_bytes):
                self._chips_dirty = True
                self._refresh_chips()
                self.status_var.set(f"已添加 {full_name}（未保存）")
            else:
                messagebox.showwarning("槽位已满", "芯片槽位已满，无法添加")
        except Exception as e:
            messagebox.showerror("添加芯片失败", str(e))

    # ======================== 保存 / 恢复 ========================

    def _backup_dir(self) -> str:
        """保存/手动备份/恢复共用同一个备份目录（避免末尾分隔符导致分叉）。"""
        folder = self.save_folder.get()
        return os.path.abspath(os.path.join(folder, os.pardir, SAVE_FOLDER_NAME + "_backup"))

    def _save_all(self):
        if not self.gamedata:
            return
        if not self.slotdata:
            messagebox.showwarning("无存档位", "请先选择一个存档位")
            return
        if (not self._money_items_dirty and not self._weapons_dirty
                and not self._chips_dirty
                and not self.gamedata.modified and not self.slotdata.modified):
            messagebox.showinfo("无需保存", "没有检测到任何修改。")
            return
        if not messagebox.askyesno("确认保存", "保存前将自动备份原存档。\n确定要写入修改吗？"):
            return

        folder = self.save_folder.get()
        slot_index = self.cur_slot.get()
        slot_file = SLOT_FILES[slot_index]
        gd_path = os.path.join(folder, GAMEDATA_FILE)
        sd_path = os.path.join(folder, slot_file)
        backup_dir = self._backup_dir()
        opid = new_operation_id()

        gd_backup = sd_backup = None
        prepared: list[SaveFile] = []
        modified_before: dict[int, bool] = {}
        try:
            # A4：同一次保存的两个文件使用同一个 opid，写入同一份 manifest
            gd_backup = self.gamedata.backup(backup_dir, opid=opid, slot=slot_index)
            sd_backup = self.slotdata.backup(backup_dir, opid=opid, slot=slot_index)

            # 如果有金币/道具修改，以 SlotData 为权威同步回 GameData
            if self._money_items_dirty:
                self.gamedata.sync_money_items_from(self.slotdata)

            # A2：两个文件都只 stage，不碰 live 文件；全部成功后才 commit
            for sf in (self.gamedata, self.slotdata):
                modified_before[id(sf)] = sf.modified
                if sf.modified:
                    sf.prepare()
                    prepared.append(sf)

            written = []
            for sf in prepared:
                sf.commit()
                written.append(GAMEDATA_FILE if sf is self.gamedata else slot_file)
        except Exception as e:
            # 任一 stage/commit 失败：清理临时文件，并用保存前备份恢复现场
            for sf in prepared:
                sf.abort()
            rollback_error = None
            if gd_backup and sd_backup:
                try:
                    replace_files_atomically([(gd_backup, gd_path), (sd_backup, sd_path)])
                except Exception as re:
                    rollback_error = re
            # 恢复内存中的 modified 标记，用户可以直接重试，不会静默丢修改
            for sf in prepared:
                try:
                    sf._modified = modified_before.get(id(sf), True)
                except Exception:
                    pass
            if rollback_error:
                messagebox.showerror(
                    "保存失败且回滚失败",
                    f"{e}\n\n回滚也失败了：{rollback_error}\n"
                    f"请手动用备份恢复：{backup_dir}"
                )
            else:
                messagebox.showerror(
                    "保存失败",
                    f"{e}\n\n未写入任何文件，已用保存前备份恢复现场。"
                )
            return

        msg = (
            f"保存成功！已写入：{'、'.join(written) or '（无改动）'}\n"
            f"GameData 备份: {os.path.basename(gd_backup)}\n"
            f"SlotData 备份: {os.path.basename(sd_backup)}"
        )
        messagebox.showinfo("成功", msg)
        self.status_var.set(f"已保存 {slot_file}")
        # 重置脏标记
        self._money_items_dirty = False
        self._weapons_dirty = False
        self._chips_dirty = False

    def _restore_backup(self):
        backup_dir = self._backup_dir()
        if not os.path.isdir(backup_dir):
            messagebox.showwarning("无备份", "未找到备份文件夹")
            return

        slot_index = self.cur_slot.get()
        slot_file = SLOT_FILES[slot_index]
        try:
            # A4：只认同一 opid 且包含当前槽位 SlotData 的配对；旧备份按秒分组兜底
            pairs = find_backup_pairs(backup_dir, slot_index)
        except Exception as e:
            messagebox.showerror("读取备份失败", str(e))
            return
        if not pairs:
            messagebox.showwarning(
                "无可用备份",
                f"备份文件夹里没有与「GameData + {slot_file}」同一次操作配对的安全备份。\n"
                f"旧式备份必须同秒分组且包含当前槽位，配不上时已拒绝恢复，避免混搭。"
            )
            return

        pair = pairs[0]
        readable = pair.get("time") or pair["opid"]
        if not messagebox.askyesno(
            "恢复备份",
            f"将把存档回滚到 {readable} 的那次备份（opid={pair['opid']}）：\n"
            f"  {pair['gamedata_name']}\n  {pair['slotdata_name']}\n\n确定吗？"
        ):
            return

        folder = self.save_folder.get()
        gd_path = os.path.join(folder, GAMEDATA_FILE)
        sd_path = os.path.join(folder, slot_file)
        snap_gd = snap_sd = None
        try:
            # A3：先用新机制给当前两个文件做一次成对快照备份
            current_gd = SaveFile(gd_path)
            current_sd = SaveFile(sd_path)
            snap_opid = new_operation_id()
            snap_gd = current_gd.backup(backup_dir, opid=snap_opid, slot=slot_index)
            snap_sd = current_sd.backup(backup_dir, opid=snap_opid, slot=slot_index)

            # 两阶段写入临时文件，再 os.replace
            replace_files_atomically([
                (pair["gamedata"], gd_path),
                (pair["slotdata"], sd_path),
            ])

            # 回读校验：重新 SaveFile 载入，且长度必须与备份源一致
            expected_gd = os.path.getsize(pair["gamedata"])
            expected_sd = os.path.getsize(pair["slotdata"])
            new_gd = SaveFile(gd_path)
            new_sd = SaveFile(sd_path)
            if new_gd.file_size != expected_gd or new_sd.file_size != expected_sd:
                raise SaveError(
                    f"恢复后长度校验失败：GameData {new_gd.file_size}/{expected_gd}，"
                    f"{slot_file} {new_sd.file_size}/{expected_sd}"
                )
        except Exception as e:
            rollback_error = None
            rollback_ok = False
            if snap_gd and snap_sd:
                try:
                    replace_files_atomically([(snap_gd, gd_path), (snap_sd, sd_path)])
                    rb_gd = SaveFile(gd_path)
                    rb_sd = SaveFile(sd_path)
                    if (rb_gd.file_size == os.path.getsize(snap_gd)
                            and rb_sd.file_size == os.path.getsize(snap_sd)):
                        rollback_ok = True
                    else:
                        rollback_error = "回滚后长度校验失败"
                except Exception as re:
                    rollback_error = re
            if rollback_error:
                messagebox.showerror(
                    "恢复失败且回滚失败",
                    f"{e}\n\n回滚也失败了：{rollback_error}\n"
                    f"恢复前快照位于：{backup_dir}"
                )
            elif rollback_ok:
                messagebox.showerror(
                    "恢复失败",
                    f"{e}\n\n已用恢复前快照回滚，存档保持恢复前状态。"
                )
            else:
                messagebox.showerror("恢复失败", str(e))
            return

        # 恢复成功后清掉脏标记，再统一重载
        self._money_items_dirty = False
        self._weapons_dirty = False
        self._chips_dirty = False
        self._refresh()
        self.status_var.set("已从备份恢复")
        messagebox.showinfo(
            "成功",
            f"已从备份恢复存档。\n恢复前快照：{os.path.basename(snap_gd)} / "
            f"{os.path.basename(snap_sd)}"
        )

    def _manual_backup(self):
        if not self.gamedata:
            return
        backup_dir = self._backup_dir()
        slot_index = self.cur_slot.get()
        opid = new_operation_id()
        try:
            b1 = self.gamedata.backup(backup_dir, opid=opid, slot=slot_index)
            msg = f"已备份 GameData → {os.path.basename(b1)}"
            if self.slotdata:
                b2 = self.slotdata.backup(backup_dir, opid=opid, slot=slot_index)
                msg += f"\n已备份 SlotData → {os.path.basename(b2)}"
            messagebox.showinfo("备份完成", msg)
        except Exception as e:
            messagebox.showerror("备份失败", str(e))

    # ======================== 启动 ========================

    def run(self):
        self.root.mainloop()


def main():
    app = NierSaveEditor()
    app.run()


if __name__ == '__main__':
    main()
