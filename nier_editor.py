"""
小柒 尼尔机械纪元 存档修改器
GUI 主界面 — ttkbootstrap 暗色主题
支持：金币修改 / 道具管理 / 芯片管理
"""

import os
import shutil

import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog

import ttkbootstrap as tb
import ttkbootstrap as ttk          # bootstyle 只对 ttkbootstrap 的控件生效（1.x / 2.x 都可用）
from ttkbootstrap.constants import *

from constants import *
from save_io import SaveFile, SaveError
from item_data import ITEM_NAMES, CATEGORY_ORDER, get_item_name, get_category, is_weapon
from chip_data import REGISTRY as CHIPS
from chip_data import CHIP_EFFECTS, CHIP_RECORD_SIZE


class NierSaveEditor:
    """主窗口"""

    def __init__(self):
        self.root = tb.Window(themename="darkly")
        self.root.title("小柒 尼尔机械纪元 存档修改器")
        self.root.geometry("950x680")
        self.root.minsize(800, 550)

        # 状态
        self.save_folder = tk.StringVar()
        self.cur_slot = tk.IntVar(value=0)
        self.gamedata: SaveFile | None = None
        self.slotdata: SaveFile | None = None
        self._loaded_slot = 0  # 当前加载的存档位
        self._money_items_dirty = False  # 金币/道具被改过
        self._chips_dirty = False        # 芯片被改过

        self._build_ui()
        self._auto_detect_folder()

    # ======================== UI 构建 ========================

    def _build_ui(self):
        # 顶部：路径选择
        top = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top.pack(fill=X)
        ttk.Label(top, text="存档文件夹:").pack(side=LEFT, padx=(0, 5))
        ttk.Entry(top, textvariable=self.save_folder, width=50).pack(side=LEFT, padx=5)
        ttk.Button(top, text="浏览...", command=self._browse_folder).pack(side=LEFT, padx=5)
        ttk.Button(top, text="刷新", command=self._refresh).pack(side=LEFT, padx=5)

        # 存档位选择
        slot_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        slot_frame.pack(fill=X)
        ttk.Label(slot_frame, text="存档位:").pack(side=LEFT, padx=(0, 5))
        for i, label in enumerate(["Slot 1", "Slot 2", "Slot 3"]):
            ttk.Radiobutton(slot_frame, text=label, variable=self.cur_slot,
                           value=i, command=self._switch_slot).pack(side=LEFT, padx=5)

        # 分隔线
        ttk.Separator(self.root, orient=HORIZONTAL).pack(fill=X, padx=10, pady=5)

        # 笔记本
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # Tab 1: 金币
        self.money_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.money_tab, text="💰 金币")
        self._build_money_tab()

        # Tab 2: 道具
        self.item_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.item_tab, text="🧪 道具")
        self._build_item_tab()

        # Tab 3: 芯片
        self.chip_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.chip_tab, text="🔧 芯片")
        self._build_chip_tab()

        # 底部：全局操作
        bottom = ttk.Frame(self.root, padding=(10, 5, 10, 10))
        bottom.pack(fill=X)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self.status_var).pack(side=LEFT)

        ttk.Button(bottom, text="💾 保存修改", bootstyle=SUCCESS,
                   command=self._save_all).pack(side=RIGHT, padx=5)
        ttk.Button(bottom, text="↩ 恢复备份", bootstyle=WARNING,
                   command=self._restore_backup).pack(side=RIGHT, padx=5)
        ttk.Button(bottom, text="📦 手动备份", bootstyle=SECONDARY,
                   command=self._manual_backup).pack(side=RIGHT, padx=5)

    # ======================== 金币 Tab ========================

    def _build_money_tab(self):
        frame = ttk.Frame(self.money_tab)
        frame.pack(expand=True)

        ttk.Label(frame, text="当前金币", font=("Microsoft YaHei", 11)).pack(pady=5)
        self.money_label = ttk.Label(frame, text="尚未加载存档", font=("Microsoft YaHei", 24, "bold"))
        self.money_label.pack(pady=5)

        row = ttk.Frame(frame)
        row.pack(pady=10)
        ttk.Label(row, text="新数值:").pack(side=LEFT, padx=5)
        self.money_entry = ttk.Entry(row, width=15)
        self.money_entry.pack(side=LEFT, padx=5)
        ttk.Button(row, text="修改", bootstyle=PRIMARY, command=self._set_money).pack(side=LEFT, padx=5)

        ttk.Label(frame, text=f"范围: 0 ~ {MAX_MONEY:,}", font=("Microsoft YaHei", 8)).pack()

    # ======================== 道具 Tab ========================

    def _build_item_tab(self):
        # 搜索栏
        search_frame = ttk.Frame(self.item_tab)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="🔍").pack(side=LEFT, padx=(0, 5))
        self.item_search_var = tk.StringVar()
        self.item_search_var.trace_add('write', lambda *_: self._refresh_items())
        ttk.Entry(search_frame, textvariable=self.item_search_var, width=25).pack(side=LEFT, padx=5)

        ttk.Label(search_frame, text="分类:").pack(side=LEFT, padx=(10, 5))
        self.item_cat_var = tk.StringVar(value="全部")
        cats = ["全部"] + list(CATEGORY_ORDER)
        cb = ttk.Combobox(search_frame, textvariable=self.item_cat_var, values=cats, width=15, state="readonly")
        cb.pack(side=LEFT, padx=5)
        cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_items())

        self.show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text="显示全部", variable=self.show_all_var,
                       command=self._refresh_items).pack(side=RIGHT, padx=5)

        # 道具列表
        cols = ("名称", "数量", "ID")
        self.item_tree = ttk.Treeview(self.item_tab, columns=cols, show="headings", height=18)
        self.item_tree.heading("名称", text="名称")
        self.item_tree.heading("数量", text="数量")
        self.item_tree.heading("ID", text="ID")
        self.item_tree.column("名称", width=300)
        self.item_tree.column("数量", width=80, anchor=CENTER)
        self.item_tree.column("ID", width=100, anchor=CENTER)
        self.item_tree.pack(fill=BOTH, expand=True, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self.item_tree, orient=VERTICAL, command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 操作按钮
        btn_frame = ttk.Frame(self.item_tab)
        btn_frame.pack(fill=X, pady=5)

        self.item_amount_var = tk.StringVar(value="1")
        ttk.Label(btn_frame, text="数量:").pack(side=LEFT, padx=5)
        ttk.Entry(btn_frame, textvariable=self.item_amount_var, width=8).pack(side=LEFT, padx=5)

        ttk.Button(btn_frame, text="➕ 增加", bootstyle=SUCCESS,
                   command=lambda: self._mod_item(1)).pack(side=LEFT, padx=3)
        ttk.Button(btn_frame, text="➖ 减少", bootstyle=DANGER,
                   command=lambda: self._mod_item(-1)).pack(side=LEFT, padx=3)
        ttk.Button(btn_frame, text="✏ 设数量", bootstyle=INFO,
                   command=lambda: self._mod_item(0)).pack(side=LEFT, padx=3)

        # 添加新道具
        add_frame = ttk.Frame(self.item_tab)
        add_frame.pack(fill=X, pady=5)
        ttk.Label(add_frame, text="添加道具:").pack(side=LEFT, padx=5)
        self.item_add_var = tk.StringVar()
        all_items = sorted(ITEM_NAMES.items(), key=lambda x: x[1])
        item_names = [f"{n} (0x{i:04X})" for i, n in all_items]
        self.item_add_cb = ttk.Combobox(add_frame, textvariable=self.item_add_var,
                                        values=item_names, width=35)
        self.item_add_cb.pack(side=LEFT, padx=5)
        ttk.Button(add_frame, text="添加", bootstyle=SUCCESS,
                   command=self._add_item).pack(side=LEFT, padx=5)

    # ======================== 芯片 Tab ========================

    def _build_chip_tab(self):
        # 搜索 + 分类
        search_frame = ttk.Frame(self.chip_tab)
        search_frame.pack(fill=X, pady=(0, 5))
        ttk.Label(search_frame, text="🔍").pack(side=LEFT, padx=(0, 5))
        self.chip_search_var = tk.StringVar()
        self.chip_search_var.trace_add('write', lambda *_: self._refresh_chips())
        ttk.Entry(search_frame, textvariable=self.chip_search_var, width=25).pack(side=LEFT, padx=5)

        ttk.Label(search_frame, text="分类:").pack(side=LEFT, padx=(10, 5))
        self.chip_cat_var = tk.StringVar(value="全部")
        chip_cats = ["全部", "攻击", "防御", "辅助", "HUD", "特殊"]
        cb = ttk.Combobox(search_frame, textvariable=self.chip_cat_var, values=chip_cats, width=12, state="readonly")
        cb.pack(side=LEFT, padx=5)
        cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_chips())

        ttk.Label(search_frame, text="已装芯片:", font=("Microsoft YaHei", 9)).pack(side=RIGHT)
        self.chip_count_label = ttk.Label(search_frame, text="0", font=("Microsoft YaHei", 9))
        self.chip_count_label.pack(side=RIGHT)

        # 芯片列表
        cols = ("名称", "等级", "格数", "效果")
        self.chip_tree = ttk.Treeview(self.chip_tab, columns=cols, show="headings", height=16)
        self.chip_tree.heading("名称", text="名称")
        self.chip_tree.heading("等级", text="等级")
        self.chip_tree.heading("格数", text="格数")
        self.chip_tree.heading("效果", text="效果")
        self.chip_tree.column("名称", width=300)
        self.chip_tree.column("等级", width=60, anchor=CENTER)
        self.chip_tree.column("格数", width=50, anchor=CENTER)
        self.chip_tree.column("效果", width=350)
        self.chip_tree.pack(fill=BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(self.chip_tree, orient=VERTICAL, command=self.chip_tree.yview)
        self.chip_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 删除按钮
        btn_frame = ttk.Frame(self.chip_tab)
        btn_frame.pack(fill=X, pady=5)
        ttk.Button(btn_frame, text="🗑 删除选中", bootstyle=DANGER,
                   command=self._remove_chip).pack(side=LEFT, padx=5)

        # 添加芯片
        add_frame = ttk.Frame(self.chip_tab)
        add_frame.pack(fill=X, pady=5)
        ttk.Label(add_frame, text="添加芯片:").pack(side=LEFT, padx=5)

        self.chip_add_var = tk.StringVar()
        common_names = sorted(CHIPS.common_names)
        unique_names = sorted(CHIPS.unique_names)
        all_chip_names = common_names + unique_names
        self.chip_add_cb = ttk.Combobox(add_frame, textvariable=self.chip_add_var,
                                        values=all_chip_names, width=25)
        self.chip_add_cb.pack(side=LEFT, padx=5)

        ttk.Label(add_frame, text="等级:").pack(side=LEFT, padx=(10, 5))
        self.chip_lv_var = tk.IntVar(value=0)
        ttk.Spinbox(add_frame, from_=0, to=8, textvariable=self.chip_lv_var,
                    width=5).pack(side=LEFT, padx=5)

        ttk.Button(add_frame, text="添加", bootstyle=SUCCESS,
                   command=self._add_chip).pack(side=LEFT, padx=5)

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
        """切换存档位"""
        if not self.gamedata:
            return
        new_slot = self.cur_slot.get()
        # 检查未保存修改
        if self._money_items_dirty or self._chips_dirty:
            if not messagebox.askyesno("未保存的修改", "当前有未保存的修改，切换存档位将丢失。\n继续吗？"):
                self.cur_slot.set(self._loaded_slot)
                return
        folder = self.save_folder.get()
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
        self._chips_dirty = False
        self._refresh_money()
        self._refresh_items()
        self._refresh_chips()

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

    def _set_money(self):
        if not self.gamedata or not self.slotdata:
            return
        try:
            val = int(self.money_entry.get())
            # 同时写 GameData 和 SlotData 保持一致
            self.gamedata.set_money(val)
            self.slotdata.set_money(val)
            self._money_items_dirty = True
            self._refresh_money()
            self.status_var.set(f"金币已设为 {val:,} G（未保存）")
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))

    # ======================== 道具操作 ========================

    def _refresh_items(self):
        try:
            # 优先从 SlotData 读取（游戏实际读这个），限制 512 条
            target = self.slotdata if self.slotdata else self.gamedata
            if not target:
                return
            for row in self.item_tree.get_children():
                self.item_tree.delete(row)

            query = self.item_search_var.get().lower()
            category = self.item_cat_var.get()
            show_all = self.show_all_var.get()

            all_items = target.get_items(limit=SLOT_MAX_ITEMS)
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
        try:
            amt_val = int(self.item_amount_var.get())
        except ValueError:
            messagebox.showwarning("输入错误", "请输入有效整数")
            return
        if direction == 1:
            new_amt = min(cur + amt_val, MAX_ITEM_AMOUNT)
        elif direction == -1:
            new_amt = max(cur - amt_val, 0)
        else:
            new_amt = min(max(amt_val, 0), MAX_ITEM_AMOUNT)
        # 同时写 GameData 和 SlotData 保持一致
        self.gamedata.set_item(idx, iid, new_amt)
        if idx < SLOT_MAX_ITEMS:
            self.slotdata.set_item(idx, iid, new_amt)
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
            return
        iid = int(m.group(1), 16)
        # 以 SlotData 为权威添加，再同步到 GameData
        added = self.slotdata.add_or_update_item(iid, 1, limit=SLOT_MAX_ITEMS)
        if not added:
            messagebox.showwarning("槽位已满", "SlotData 道具槽位已满，无法添加")
            return
        # 同步到 GameData
        self.gamedata.sync_money_items_from(self.slotdata)
        self._money_items_dirty = True
        self._refresh_items()
        self.status_var.set(f"已添加 {get_item_name(iid)}（未保存）")

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
            self.chip_count_label.config(text=f"{count} / {MAX_CHIPS}")
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

    def _add_chip(self):
        if not self.slotdata:
            return
        try:
            name = self.chip_add_var.get()
            if not name:
                return

            level = int(self.chip_lv_var.get())
            if not 0 <= level <= 8:
                messagebox.showwarning("输入错误", "等级必须是 0-8")
                return

            # 普通芯片 +0 不加后缀，+1~+8 加后缀
            if name in CHIPS.common_names:
                full_name = name if level == 0 else f"{name} +{level}"
            else:
                full_name = name

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

    def _save_all(self):
        if not self.gamedata:
            return
        if not self.slotdata:
            messagebox.showwarning("无存档位", "请先选择一个存档位")
            return
        if not self._money_items_dirty and not self._chips_dirty and not self.gamedata.modified and not self.slotdata.modified:
            messagebox.showinfo("无需保存", "没有检测到任何修改。")
            return
        if not messagebox.askyesno("确认保存", "保存前将自动备份原存档。\n确定要写入修改吗？"):
            return

        folder = self.save_folder.get()
        slot_file = SLOT_FILES[self.cur_slot.get()]
        backup_dir = os.path.abspath(os.path.join(folder, "..", SAVE_FOLDER_NAME + "_backup"))
        try:
            # 备份
            gd_backup = self.gamedata.backup(backup_dir)
            sd_backup = self.slotdata.backup(backup_dir)

            # 如果有金币/道具修改，以 SlotData 为权威同步回 GameData
            if self._money_items_dirty:
                self.gamedata.sync_money_items_from(self.slotdata)

            # 只写真正改动过的文件，避免无谓地重写另一个文件
            written = []
            if self.gamedata.modified:
                self.gamedata.save()
                written.append(GAMEDATA_FILE)
            if self.slotdata.modified:
                self.slotdata.save()
                written.append(slot_file)

            msg = (
                f"保存成功！已写入：{'、'.join(written) or '（无改动）'}\n"
                f"GameData 备份: {os.path.basename(gd_backup)}\n"
                f"SlotData 备份: {os.path.basename(sd_backup)}"
            )
            messagebox.showinfo("成功", msg)
            self.status_var.set(f"已保存 {slot_file} ✓")
            # 重置脏标记
            self._money_items_dirty = False
            self._chips_dirty = False
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _restore_backup(self):
        folder = self.save_folder.get()
        backup_dir = os.path.join(os.path.dirname(folder), SAVE_FOLDER_NAME + "_backup")
        if not os.path.isdir(backup_dir):
            messagebox.showwarning("无备份", "未找到备份文件夹")
            return

        # 找出所有 backup 文件名，取最新的 GameData 和 SlotData
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.dat')], reverse=True)
        if not backups:
            messagebox.showwarning("无备份", "备份文件夹为空")
            return

        # 按时间戳配对：必须 GameData 和当前存档位的 SlotData 出自同一次备份
        import re
        pat = re.compile(r'^(?P<base>.+)_(?P<ts>\d{8}_\d{6})\.dat$')
        groups: dict[str, dict[str, str]] = {}
        for f in backups:
            m = pat.match(f)
            if m:
                groups.setdefault(m.group('ts'), {})[m.group('base')] = f

        slot_file = SLOT_FILES[self.cur_slot.get()]
        slot_base = slot_file.replace('.dat', '')
        pairs = [
            (ts, files) for ts, files in sorted(groups.items(), reverse=True)
            if 'GameData' in files and slot_base in files
        ]
        if not pairs:
            messagebox.showwarning(
                "无可用备份",
                f"备份文件夹里没有「GameData + {slot_file}」成对的备份，无法安全恢复。"
            )
            return

        ts, files = pairs[0]
        readable = ts.replace('_', ' ')
        if not messagebox.askyesno(
            "恢复备份",
            f"将把存档回滚到 {readable} 的那次备份：\n"
            f"  {files['GameData']}\n  {files[slot_base]}\n\n确定吗？"
        ):
            return

        try:
            shutil.copy2(os.path.join(backup_dir, files['GameData']),
                         os.path.join(folder, 'GameData.dat'))
            shutil.copy2(os.path.join(backup_dir, files[slot_base]),
                         os.path.join(folder, slot_file))

            self._refresh()
            self.status_var.set("已从备份恢复 ✓")
            messagebox.showinfo("成功", "已从备份恢复存档")
        except Exception as e:
            messagebox.showerror("恢复失败", str(e))

    def _manual_backup(self):
        if not self.gamedata:
            return
        folder = self.save_folder.get()
        backup_dir = os.path.abspath(os.path.join(folder, "..", SAVE_FOLDER_NAME + "_backup"))
        b1 = self.gamedata.backup(backup_dir)
        msg = f"已备份 GameData → {os.path.basename(b1)}"
        if self.slotdata:
            b2 = self.slotdata.backup(backup_dir)
            msg += f"\n已备份 SlotData → {os.path.basename(b2)}"
        messagebox.showinfo("备份完成", msg)

    # ======================== 启动 ========================

    def run(self):
        self.root.mainloop()


def main():
    app = NierSaveEditor()
    app.run()


if __name__ == '__main__':
    main()
