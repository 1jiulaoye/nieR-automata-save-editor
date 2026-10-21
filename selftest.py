"""存档读写自检：造一份假存档 → 读写 → 回读比对。

不依赖游戏本体，也不需要显示器：
    python selftest.py

覆盖：
  1. 合法尺寸的 GameData / SlotData 能正常载入
  2. 金币读写
  3. 小恢复药（item_id = 0）不会被当成空槽
  4. 武器可以写入并回读
  5. 芯片增删与空槽判定
  6. 保存后文件大小不变（不静默扩容）、无残留 .tmp
  7. 过小 / 被截断的文件会被拒绝载入
"""

import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import types
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import constants as K
import save_io as SIO
from chip_data import REGISTRY as CHIPS
from item_data import (
    get_item_name, get_weapon_name, get_category, is_weapon,
    ITEM_NAMES, WEAPON_NAMES, CATEGORY_ORDER, ITEM_CATEGORIES,
    search_items,
)
from save_io import (
    SaveError, SaveFile, BACKUP_MANIFEST_NAME, find_backup_pairs,
    load_backup_manifest, replace_files_atomically,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def make_gamedata(path: str, money: int = 5000) -> str:
    g = bytearray(400_000)
    struct.pack_into("<I", g, K.OFFSET_MONEY, money)
    for i in range(K.SLOT_MAX_ITEMS):
        off = K.OFFSET_ITEMS_START + i * K.ITEM_RECORD_SIZE
        struct.pack_into("<H", g, off, K.ITEM_EMPTY_ID)
    with open(path, "wb") as f:
        f.write(g)
    return path


def make_slot(path: str, money: int = 5000) -> str:
    s = bytearray(231_000)
    struct.pack_into("<I", s, K.OFFSET_MONEY, money)
    for i in range(K.SLOT_MAX_ITEMS):
        off = K.OFFSET_ITEMS_START + i * K.ITEM_RECORD_SIZE
        struct.pack_into("<H", s, off, K.ITEM_EMPTY_ID)
    # 尸体背包 / 武器表 / 芯片区的空槽都是 0xFF（武器 id == -1）
    s[K.CORPSE_ITEMS_START:K.CORPSE_ITEMS_END] = (
        b"\xff" * (K.CORPSE_ITEMS_END - K.CORPSE_ITEMS_START)
    )
    s[K.WEAPONS_START:K.WEAPONS_END] = (
        b"\xff" * (K.WEAPONS_END - K.WEAPONS_START)
    )
    s[K.OFFSET_CHIPS_START:K.CHIPS_END] = (
        b"\xff" * (K.CHIPS_END - K.OFFSET_CHIPS_START)
    )
    with open(path, "wb") as f:
        f.write(s)
    return path


def make_saves(tmp: str) -> tuple[str, str]:
    """造一份 400KB GameData + 231KB SlotData 的空存档"""
    gd = os.path.join(tmp, "GameData.dat")
    sd = os.path.join(tmp, "SlotData_0.dat")
    make_gamedata(gd)
    make_slot(sd)
    return gd, sd


def _install_gui_stubs() -> None:
    """无 tkinter/ttkbootstrap 环境下也能导入 nier_editor 做对象级测试。"""
    class FakeVar:
        def __init__(self, value=None):
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

        def trace_add(self, *args, **kwargs):
            return "trace"

    tkmod = types.ModuleType("tkinter")
    tkmod.StringVar = FakeVar
    tkmod.IntVar = FakeVar
    tkmod.BooleanVar = FakeVar
    tkmod.END = "end"
    tkmod.LEFT = "left"
    tkmod.RIGHT = "right"
    tkmod.X = "x"
    tkmod.Y = "y"
    tkmod.BOTH = "both"
    tkmod.HORIZONTAL = "horizontal"
    tkmod.VERTICAL = "vertical"
    tkmod.CENTER = "center"

    messagebox = types.ModuleType("tkinter.messagebox")
    filedialog = types.ModuleType("tkinter.filedialog")
    tkmod.messagebox = messagebox
    tkmod.filedialog = filedialog

    tb = types.ModuleType("ttkbootstrap")
    tb_constants = types.ModuleType("ttkbootstrap.constants")
    tb.constants = tb_constants

    sys.modules["tkinter"] = tkmod
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.filedialog"] = filedialog
    sys.modules["ttkbootstrap"] = tb
    sys.modules["ttkbootstrap.constants"] = tb_constants


def _test_a1(tmp: str) -> None:
    """A1：Slot 0 改金币 → 确认丢弃并切到 Slot 1 → 再保存，金币必须一致。"""
    print("\nA1 存档位状态泄漏（无 GUI 对象级）")
    d = os.path.join(tmp, "a1")
    os.makedirs(d)
    gd, sd0 = make_saves(d)
    sd1 = make_slot(os.path.join(d, "SlotData_1.dat"))

    _install_gui_stubs()
    import nier_editor
    errors = []
    nier_editor.messagebox.askyesno = lambda *a, **k: True
    nier_editor.messagebox.showinfo = lambda *a, **k: None
    nier_editor.messagebox.showwarning = lambda *a, **k: None
    nier_editor.messagebox.showerror = lambda title, msg: errors.append((title, msg))

    ed = object.__new__(nier_editor.NierSaveEditor)
    ed.save_folder = nier_editor.tk.StringVar(d)
    ed.cur_slot = nier_editor.tk.IntVar(0)
    ed.status_var = nier_editor.tk.StringVar("")
    ed.gamedata = SaveFile(gd)
    ed.slotdata = SaveFile(sd0)
    ed._loaded_slot = 0
    ed._money_items_dirty = False
    ed._weapons_dirty = False
    ed._chips_dirty = False
    ed._refresh_money = lambda: None
    ed._refresh_items = lambda: None
    ed._refresh_weapons = lambda: None
    ed._refresh_corpse = lambda: None
    ed._refresh_chips = lambda: None

    # Slot 0 改金币（模拟 GUI 同时写两个对象）
    ed.gamedata.set_money(8888)
    ed.slotdata.set_money(8888)
    ed._money_items_dirty = True
    ed.cur_slot.set(1)
    ed._switch_slot()  # 弹窗确认“丢弃”由上面的 askyesno=True 模拟

    check("A1 切换后 GameData 从磁盘重载（8888 → 5000）",
          ed.gamedata.get_money() == 5000, f"实际 {ed.gamedata.get_money()}")
    check("A1 切换后 gamedata.modified 与 dirty 标记全部清除",
          not ed.gamedata.modified and not ed._money_items_dirty and not ed._chips_dirty)
    check("A1 已载入 SlotData_1",
          ed.slotdata is not None and ed.slotdata.filepath.endswith("SlotData_1.dat"))

    # Slot 1 改金币后再保存，验证 GameData 与 SlotData_1 不会各写各的
    ed.gamedata.set_money(6000)
    ed.slotdata.set_money(6000)
    ed._money_items_dirty = True
    ed._save_all()
    g2, s2 = SaveFile(gd), SaveFile(sd1)
    check("A1 保存后 GameData 与 SlotData_1 金币一致",
          g2.get_money() == s2.get_money() == 6000,
          f"GameData={g2.get_money()}, SlotData_1={s2.get_money()}")
    check("A1 整个切换/保存过程无错误弹窗", not errors, str(errors))

    # 载入失败必须取消切换
    missing = os.path.join(tmp, "a1_missing")
    os.makedirs(missing)
    errors.clear()
    old_gd = ed.gamedata
    ed.save_folder = nier_editor.tk.StringVar(missing)
    ed.gamedata.set_money(1234)
    ed.slotdata.set_money(1234)
    ed._money_items_dirty = True
    ed.cur_slot.set(0)
    ed._switch_slot()
    check("A1 重新载入失败时取消切换并保留原对象",
          ed.cur_slot.get() == 1 and ed.gamedata is old_gd
          and ed._money_items_dirty and bool(errors),
          f"slot={ed.cur_slot.get()}, errors={errors}")


def _test_a2(tmp: str) -> None:
    """A2：prepare/commit 两阶段写入。"""
    print("\nA2 双文件两阶段写入")
    d = os.path.join(tmp, "a2")
    os.makedirs(d)
    gd, sd = make_saves(d)

    g = SaveFile(gd)
    g.set_money(4321)
    tmp_file = g.prepare()
    check("A2 prepare 只写临时文件，原文件未变",
          os.path.exists(tmp_file) and SaveFile(gd).get_money() == 5000)
    g.commit()
    check("A2 commit 后 os.replace 生效、无残留 .tmp",
          SaveFile(gd).get_money() == 4321 and not os.path.exists(tmp_file))

    g, s = SaveFile(gd), SaveFile(sd)
    g.set_money(7001)
    s.set_money(7001)
    tg, ts = g.prepare(), s.prepare()
    check("A2 两个文件都 stage 成功后才提交",
          os.path.exists(tg) and os.path.exists(ts))
    g.commit()
    s.commit()
    check("A2 双文件提交后金币一致",
          SaveFile(gd).get_money() == SaveFile(sd).get_money() == 7001)

    g = SaveFile(gd)
    g.set_money(9999)
    tmp_file = g.prepare()
    g.abort()
    check("A2 abort 清理临时文件且不改原文件",
          not os.path.exists(tmp_file) and SaveFile(gd).get_money() == 7001)


def _test_a4(tmp: str) -> None:
    """A4：唯一 opid、manifest、同槽配对、旧备份秒级兜底。"""
    print("\nA4 备份命名与配对")
    d = os.path.join(tmp, "a4")
    os.makedirs(d)
    gd, sd = make_saves(d)
    bdir = os.path.join(tmp, "a4_backup")
    pat = re.compile(r"^(?:GameData|SlotData_\d+)_"
                     r"(\d{8}_\d{6}_\d{6}_[0-9a-f]{4})\.dat$")

    real_dt, real_token = SIO.datetime, SIO.secrets.token_hex
    frozen = datetime(2026, 1, 2, 3, 4, 5, 123456)
    tokens = iter(["aaaa", "bbbb"])

    class FrozenDateTime:
        @classmethod
        def now(cls):
            return frozen

        strptime = staticmethod(real_dt.strptime)

    SIO.datetime = FrozenDateTime
    SIO.secrets.token_hex = lambda n=2: next(tokens)
    try:
        b1 = SaveFile(gd).backup(bdir)
        b2 = SaveFile(gd).backup(bdir)
    finally:
        SIO.datetime = real_dt
        SIO.secrets.token_hex = real_token

    m1 = pat.match(os.path.basename(b1))
    m2 = pat.match(os.path.basename(b2))
    check("A4 同一秒连续两次 backup 生成两个不同 opid 文件",
          b1 != b2 and os.path.isfile(b1) and os.path.isfile(b2)
          and m1 and m2 and m1.group(1) != m2.group(1),
          f"{os.path.basename(b1)} / {os.path.basename(b2)}")

    manifest = load_backup_manifest(bdir)
    ops = manifest.get("operations", [])
    check("A4 manifest.json 记录 opid、槽位、时间与文件列表",
          len(ops) == 2 and all(op.get("opid") and op.get("time")
                                and "slot" in op and op.get("files") for op in ops))
    sha_ok = True
    for path in (b1, b2):
        opid = pat.match(os.path.basename(path)).group(1)
        op = next((x for x in ops if x.get("opid") == opid), None)
        entry = next((x for x in (op or {}).get("files", [])
                      if x.get("source") == "GameData.dat"), None)
        want = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if not entry or entry.get("sha256") != want:
            sha_ok = False
    check("A4 manifest 中的 sha256 与实际备份文件一致", sha_ok)
    check("A4 两份同秒备份内容都完整可回读",
          open(b1, "rb").read() == open(gd, "rb").read()
          and open(b2, "rb").read() == open(gd, "rb").read())

    # 同一 opid 配对 + 跨槽不混搭
    pdir = os.path.join(tmp, "a4_pair")
    os.makedirs(pdir)
    sd1 = make_slot(os.path.join(d, "SlotData_1.dat"), money=6000)
    op0 = "20260102_030405_123456_abcd"
    op1 = "20260102_030406_123456_abce"
    g = SaveFile(gd)
    g.backup(pdir, opid=op0, slot=0)
    SaveFile(sd).backup(pdir, opid=op0, slot=0)
    g.backup(pdir, opid=op1, slot=1)
    SaveFile(sd1).backup(pdir, opid=op1, slot=1)

    pairs0 = find_backup_pairs(pdir, 0)
    pairs1 = find_backup_pairs(pdir, 1)
    check("A4 Slot 0 只配对同一 opid 的 SlotData_0",
          len(pairs0) == 1 and pairs0[0]["opid"] == op0
          and pairs0[0]["slotdata_name"] == f"SlotData_0_{op0}.dat",
          str([(p["opid"], p["slotdata_name"]) for p in pairs0]))
    check("A4 Slot 1 只配对同一 opid 的 SlotData_1（不拿 Slot 0 混搭）",
          len(pairs1) == 1 and pairs1[0]["opid"] == op1
          and pairs1[0]["slotdata_name"] == f"SlotData_1_{op1}.dat",
          str([(p["opid"], p["slotdata_name"]) for p in pairs1]))

    # 配对备份可原子恢复
    rdir = os.path.join(tmp, "a4_restore")
    os.makedirs(rdir)
    rgd = os.path.join(rdir, "GameData.dat")
    rsd = os.path.join(rdir, "SlotData_0.dat")
    shutil.copyfile(gd, rgd)
    shutil.copyfile(sd, rsd)
    r = SaveFile(rgd)
    r.set_money(9999)
    r.save()
    replace_files_atomically([(pairs0[0]["gamedata"], rgd),
                              (pairs0[0]["slotdata"], rsd)])
    check("A4 成对备份可恢复且无残留临时文件",
          SaveFile(rgd).get_money() == 5000 and SaveFile(rsd).get_money() == 5000
          and not [f for f in os.listdir(rdir) if f.endswith(".tmp")])

    # 没有 manifest 的旧备份：按秒级分组兜底
    ldir = os.path.join(tmp, "a4_legacy")
    os.makedirs(ldir)
    shutil.copyfile(gd, os.path.join(ldir, "GameData_20260102_030405.dat"))
    shutil.copyfile(sd, os.path.join(ldir, "SlotData_0_20260102_030405.dat"))
    legacy = find_backup_pairs(ldir, 0)
    check("A4 无 manifest 的旧备份按同秒分组成功配对",
          len(legacy) == 1 and legacy[0]["source"] == "legacy",
          str([(p["opid"], p["slotdata_name"]) for p in legacy]))

    ldir2 = os.path.join(tmp, "a4_legacy_mismatch")
    os.makedirs(ldir2)
    shutil.copyfile(gd, os.path.join(ldir2, "GameData_20260102_030405.dat"))
    shutil.copyfile(sd1, os.path.join(ldir2, "SlotData_1_20260102_030405.dat"))
    check("A4 旧备份同秒但只有其他槽位时明确拒绝配对（不混搭）",
          find_backup_pairs(ldir2, 0) == [])

    ldir3 = os.path.join(tmp, "a4_legacy_ambiguous")
    os.makedirs(ldir3)
    shutil.copyfile(gd, os.path.join(ldir3, "GameData_20260102_030405.dat"))
    shutil.copyfile(sd, os.path.join(ldir3, "SlotData_0_20260102_030405.dat"))
    shutil.copyfile(sd1, os.path.join(ldir3, "SlotData_1_20260102_030405.dat"))
    check("A4 旧备份同秒含多个槽位时判为无法配对（拒绝跨槽混搭）",
          find_backup_pairs(ldir3, 0) == [] and find_backup_pairs(ldir3, 1) == [])

    check("A4 manifest.json 已写入备份目录",
          os.path.isfile(os.path.join(bdir, BACKUP_MANIFEST_NAME)))


def _test_a6(tmp: str) -> None:
    """A6：芯片判空必须同时考虑整条 48 字节与 level/size。"""
    print("\nA6 芯片判空")
    d = os.path.join(tmp, "a6")
    os.makedirs(d)
    _, sd = make_saves(d)
    s = SaveFile(sd)
    off = K.OFFSET_CHIPS_START

    struct.pack_into("<12i", s._data, off, 0, 0, 0, 5, 9, 0, 0, 0, 0, 0, 0, 0)
    chip = s.get_chips()[0]
    check("A6 (0,0,0,level=5,size=9) 不算空",
          not chip["empty"] and chip["level"] == 5 and chip["size"] == 9)
    s.add_chip(CHIPS.to_bytes("HP最大值UP +3"))
    chips = s.get_chips()
    check("A6 部分初始化记录不会被 add_chip 覆盖",
          chips[0]["level"] == 5 and chips[0]["size"] == 9 and not chips[1]["empty"])

    struct.pack_into("<12i", s._data, off, *([0] * 12))
    check("A6 48 字节全 0 算空", s.get_chips()[0]["empty"])

    s._data[off:off + K.CHIP_RECORD_SIZE] = b"\xff" * K.CHIP_RECORD_SIZE
    check("A6 前三个 int32 全 -1 算空", s.get_chips()[0]["empty"])

    struct.pack_into("<12i", s._data, off, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0)
    check("A6 前三个 int32 为 0 但其余字节非 0 不算空",
          not s.get_chips()[0]["empty"])

    struct.pack_into("<12i", s._data, off, 0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0)
    check("A6 level=0 但 size=9 不算空", not s.get_chips()[0]["empty"])


def _test_a7(tmp: str) -> None:
    """A7：set_item 索引校验，负索引不得改到金币。"""
    print("\nA7 索引校验")
    d = os.path.join(tmp, "a7")
    os.makedirs(d)
    _, sd = make_saves(d)
    s = SaveFile(sd)
    money = s.get_money()
    rejected = []
    for idx in (-1, -12, K.SLOT_MAX_ITEMS, 600):
        try:
            s.set_item(idx, 0x042E, 99)
        except IndexError:
            rejected.append(idx)
    check("A7 负索引/越界索引全部抛 IndexError",
          rejected == [-1, -12, K.SLOT_MAX_ITEMS, 600], str(rejected))
    check("A7 非法写入后金币不变",
          s.get_money() == money, f"{money} -> {s.get_money()}")

    s.set_item(0, 0x042E, 1)
    check("A7 合法索引仍可正常写入",
          s.get_items(1)[0] == (0x042E, 1), str(s.get_items(1)[0]))



class _FakeWidget:
    """最小 GUI 控件替身：记录构造参数与 state，供 object.__new__ 级测试使用。"""

    def __init__(self, *args, **kwargs):
        self.kwargs = dict(kwargs)
        self._state = kwargs.get("state", "normal")

    def pack(self, *args, **kwargs):
        return self

    def bind(self, *args, **kwargs):
        return None

    def heading(self, *args, **kwargs):
        return None

    def column(self, *args, **kwargs):
        return None

    def configure(self, *args, **kwargs):
        if "state" in kwargs:
            self._state = kwargs["state"]
        self.kwargs.update(kwargs)
        return None

    config = configure

    def cget(self, key):
        if key == "state":
            return self._state
        return self.kwargs.get(key, "")

    def set(self, *args, **kwargs):
        return None

    def yview(self, *args, **kwargs):
        return None


class _FakeTree:
    """只实现 _refresh_items 用到的 Treeview 接口。"""

    def __init__(self):
        self.rows = []
        self._seq = 0

    def get_children(self):
        return [row[0] for row in self.rows]

    def delete(self, row):
        self.rows = [r for r in self.rows if r[0] != row]

    def insert(self, parent, index, values=(), tags=()):
        self._seq += 1
        row_id = f"row{self._seq}"
        self.rows.append((row_id, tuple(values), tuple(tags)))
        return row_id

    def configure(self, *args, **kwargs):
        return None

    def yview(self, *args, **kwargs):
        return None


def _prepare_gui_stubs(nier_editor) -> None:
    """把 nier_editor 里的 ttkbootstrap 控件替换成可记录的替身（无显示器）。"""
    for name in ("X", "Y", "BOTH", "LEFT", "RIGHT", "CENTER",
                 "HORIZONTAL", "VERTICAL", "END",
                 "SUCCESS", "DANGER", "INFO", "PRIMARY", "SECONDARY", "WARNING"):
        setattr(nier_editor, name, name.lower())
    for name in ("Frame", "Label", "Entry", "Combobox", "Checkbutton",
                 "Button", "Treeview", "Scrollbar", "Spinbox", "Separator",
                 "Notebook", "Radiobutton"):
        setattr(nier_editor.ttk, name, _FakeWidget)


def _make_editor(nier_editor, gd: str, sd: str):
    ed = object.__new__(nier_editor.NierSaveEditor)
    ed.gamedata = SaveFile(gd)
    ed.slotdata = SaveFile(sd)
    ed.status_var = nier_editor.tk.StringVar("")
    ed._money_items_dirty = False
    ed._weapons_dirty = False
    ed._chips_dirty = False
    ed._refresh_money = lambda: None
    ed._refresh_items = lambda: None
    ed._refresh_weapons = lambda: None
    ed._refresh_corpse = lambda: None
    ed._refresh_chips = lambda: None
    ed.item_amount_var = nier_editor.tk.StringVar("1")
    ed.weapon_level_var = nier_editor.tk.IntVar(1)
    ed.weapon_add_var = nier_editor.tk.StringVar("")
    return ed


def _capture_messagebox(nier_editor):
    msgs = {"warning": [], "info": [], "error": []}
    nier_editor.messagebox.showwarning = lambda title, msg: msgs["warning"].append((title, msg))
    nier_editor.messagebox.showinfo = lambda title, msg: msgs["info"].append((title, msg))
    nier_editor.messagebox.showerror = lambda title, msg: msgs["error"].append((title, msg))
    return msgs


def _test_a8(tmp: str) -> None:
    """A8：数量输入 1..255 校验、增减结果钳制、set_item 异常不得逃出回调。"""
    print("\nA8 数量输入校验（GUI 对象级）")
    d = os.path.join(tmp, "a8")
    os.makedirs(d)
    gd, sd = make_saves(d)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)

    ed = _make_editor(nier_editor, gd, sd)
    iid = 0x0000  # 小恢复药，非武器
    ed.gamedata.set_item(0, iid, 5)
    ed.slotdata.set_item(0, iid, 5)
    ed._get_selected_item_index = lambda: (0, iid, ed.slotdata.get_item(iid))

    uncaught = []
    for raw in ("-10", "0", "300", "abc"):
        msgs["warning"].clear()
        ed.item_amount_var.set(raw)
        try:
            ed._mod_item(1)
        except Exception as e:  # 不允许 Tk 回调抛未捕获异常
            uncaught.append((raw, repr(e)))
        check(f"A8 输入 {raw!r} 不写入且弹出提示",
              ed.slotdata.get_item(iid) == 5
              and ed.gamedata.get_item(iid) == 5 and bool(msgs["warning"]),
              f"slot={ed.slotdata.get_item(iid)}, gd={ed.gamedata.get_item(iid)}, "
              f"warnings={msgs['warning']}")
    check("A8 四种非法输入均无未捕获异常", not uncaught, str(uncaught))

    # 合法输入：增加钳制 255，减少钳制 0
    msgs["warning"].clear()
    ed.gamedata.set_item(0, iid, 250)
    ed.slotdata.set_item(0, iid, 250)
    ed.item_amount_var.set("10")
    ed._mod_item(1)
    check("A8 增加结果上限 255",
          ed.gamedata.get_item(iid) == 255 and ed.slotdata.get_item(iid) == 255,
          f"{ed.slotdata.get_item(iid)}")
    ed.gamedata.set_item(0, iid, 5)
    ed.slotdata.set_item(0, iid, 5)
    ed._mod_item(-1)
    check("A8 减少结果下限 0",
          ed.gamedata.get_item(iid) == 0 and ed.slotdata.get_item(iid) == 0,
          f"{ed.slotdata.get_item(iid)}")

    # set_item 抛异常时必须捕获并 showerror，不得冒泡
    ed.gamedata.set_item(0, iid, 7)
    ed.slotdata.set_item(0, iid, 7)
    msgs["error"].clear()
    uncaught.clear()
    ed.item_amount_var.set("2")
    original = ed.gamedata.set_item

    def boom(*args, **kwargs):
        raise ValueError("boom-set-item")

    ed.gamedata.set_item = boom
    try:
        ed._mod_item(0)
    except Exception as e:
        uncaught.append(repr(e))
    finally:
        ed.gamedata.set_item = original
    check("A8 set_item 异常被捕获并提示",
          not uncaught and bool(msgs["error"])
          and "boom-set-item" in msgs["error"][-1][1],
          f"uncaught={uncaught}, errors={msgs['error']}")
    check("A8 set_item 异常后数量未改变",
          ed.gamedata.get_item(iid) == 7 and ed.slotdata.get_item(iid) == 7,
          f"gd={ed.gamedata.get_item(iid)}, slot={ed.slotdata.get_item(iid)}")


def _test_a9(tmp: str) -> None:
    """A9：amount 1..255、拒绝 0xFFFF、已满 255 返回 False。"""
    print("\nA9 add_or_update_item 校验")
    d = os.path.join(tmp, "a9")
    os.makedirs(d)
    _, sd = make_saves(d)
    s = SaveFile(sd)
    iid = 0x0000  # 合法道具，且不是空槽标记

    rejected = []
    for bad in (0, -1, 256, 1.5):
        try:
            s.add_or_update_item(iid, bad, limit=K.SLOT_MAX_ITEMS)
        except ValueError:
            rejected.append(bad)
    check("A9 amount 0/-1/256/1.5 均抛 ValueError",
          rejected == [0, -1, 256, 1.5], str(rejected))
    check("A9 非法 amount 未写入任何道具",
          s.get_items(1)[0] == (K.ITEM_EMPTY_ID, 0), str(s.get_items(1)[0]))

    try:
        s.add_or_update_item(K.ITEM_EMPTY_ID, 1, limit=K.SLOT_MAX_ITEMS)
        rejected_empty = False
    except ValueError:
        rejected_empty = True
    check("A9 item_id=0xFFFF 抛 ValueError 且不写空槽",
          rejected_empty and s.get_items(1)[0] == (K.ITEM_EMPTY_ID, 0),
          str(s.get_items(1)[0]))

    check("A9 新道具 amount=254 写入成功", s.add_or_update_item(iid, 254, limit=K.SLOT_MAX_ITEMS))
    check("A9 已到 254 再加 1 返回 True 且变为 255",
          s.add_or_update_item(iid, 1, limit=K.SLOT_MAX_ITEMS)
          and s.get_item(iid) == 255, str(s.get_item(iid)))
    check("A9 已满 255 再加 1 返回 False",
          s.add_or_update_item(iid, 1, limit=K.SLOT_MAX_ITEMS) is False)
    check("A9 已满返回 False 后数量仍为 255", s.get_item(iid) == 255, str(s.get_item(iid)))
    s2 = SaveFile(sd)
    check("A9 直接写 amount=255 可成功且回读 255",
          s2.add_or_update_item(0x0001, 255, limit=K.SLOT_MAX_ITEMS)
          and s2.get_item(0x0001) == 255)

    # A9 的 GUI 语义：已满时提示「数量已满」，而不是误报添加成功
    d_gui = os.path.join(tmp, "a9_gui")
    os.makedirs(d_gui)
    gd_gui, sd_gui = make_saves(d_gui)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)
    ed = _make_editor(nier_editor, gd_gui, sd_gui)
    ed.slotdata.set_item(0, iid, 255)
    ed.item_add_var = nier_editor.tk.StringVar(f"{get_item_name(iid)} (0x{iid:04X})")
    ed._add_item()
    check("A9 GUI 对已满 255 的道具提示「数量已满」",
          bool(msgs["warning"]) and msgs["warning"][-1][0] == "数量已满"
          and ed.slotdata.get_item(iid) == 255,
          f"warnings={msgs['warning']}, amount={ed.slotdata.get_item(iid)}")


def _test_a10(tmp: str) -> None:
    """A10：下拉框只读，未知道具 ID 不得写入。"""
    print("\nA10 下拉框与 ID 校验（GUI 对象级）")
    d = os.path.join(tmp, "a10")
    os.makedirs(d)
    gd, sd = make_saves(d)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)

    ui = object.__new__(nier_editor.NierSaveEditor)
    ui.item_tab = _FakeWidget()
    ui._build_item_tab()
    check("A10 道具添加下拉框 state=readonly",
          ui.item_add_cb.cget("state") == "readonly",
          str(ui.item_add_cb.cget("state")))

    ui2 = object.__new__(nier_editor.NierSaveEditor)
    ui2.chip_tab = _FakeWidget()
    ui2._build_chip_tab()
    check("A10 芯片添加下拉框 state=readonly",
          ui2.chip_add_cb.cget("state") == "readonly",
          str(ui2.chip_add_cb.cget("state")))

    ed = _make_editor(nier_editor, gd, sd)
    ed.item_add_var = nier_editor.tk.StringVar("未知道具 (0xFFFF)")
    msgs["warning"].clear()
    ed._add_item()
    check("A10 未知 ID 0xFFFF 被拒绝且提示「未知道具 ID」",
          bool(msgs["warning"]) and msgs["warning"][-1][0] == "未知道具 ID"
          and ed.slotdata.get_items(1)[0] == (K.ITEM_EMPTY_ID, 0),
          f"warnings={msgs['warning']}, first={ed.slotdata.get_items(1)[0]}")

    msgs["warning"].clear()
    ed.item_add_var.set("小恢复药 (0x0000)")
    ed._add_item()
    check("A10 合法 ID 仍可正常添加",
          ed.slotdata.get_item(0x0000) == 1 and not msgs["warning"],
          f"amount={ed.slotdata.get_item(0x0000)}, warnings={msgs['warning']}")


def _test_a11(tmp: str) -> None:
    """A11：系统芯片禁用等级并提示；添加时忽略等级。"""
    print("\nA11 系统芯片等级（GUI 对象级）")
    d = os.path.join(tmp, "a11")
    os.makedirs(d)
    gd, sd = make_saves(d)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)

    ui = object.__new__(nier_editor.NierSaveEditor)
    ui.chip_tab = _FakeWidget()
    ui._build_chip_tab()
    unique_name = CHIPS.unique_names[0]
    common_name = CHIPS.common_names[0]

    ui.chip_add_var.set(unique_name)
    ui._on_chip_add_selected()
    check("A11 选中系统芯片后等级 Spinbox 禁用并提示固定等级",
          ui.chip_lv_spin.cget("state") == "disabled"
          and "固定等级" in ui.chip_lv_hint.cget("text"),
          f"state={ui.chip_lv_spin.cget('state')}, hint={ui.chip_lv_hint.cget('text')!r}")

    ui.chip_add_var.set(common_name)
    ui._on_chip_add_selected()
    check("A11 选中普通芯片后等级 Spinbox 恢复可用且提示清空",
          ui.chip_lv_spin.cget("state") == "normal"
          and ui.chip_lv_hint.cget("text") == "",
          f"state={ui.chip_lv_spin.cget('state')}, hint={ui.chip_lv_hint.cget('text')!r}")

    ed = _make_editor(nier_editor, gd, sd)
    ed.chip_add_var = nier_editor.tk.StringVar(unique_name)
    ed.chip_lv_var = nier_editor.tk.IntVar(8)
    msgs["error"].clear()
    ed._add_chip()
    expected_level = struct.unpack_from("<i", CHIPS.to_bytes(unique_name), 12)[0]
    installed = ed.slotdata.get_installed_chips()
    check("A11 添加系统芯片时忽略等级 8、按固定等级写入",
          not msgs["error"] and len(installed) == 1
          and installed[0]["level"] == expected_level
          and CHIPS.to_name(installed[0]["raw"][:12]) == unique_name,
          f"errors={msgs['error']}, installed={installed}")

    ed.chip_add_var.set(common_name)
    ed.chip_lv_var.set(3)
    ed._add_chip()
    installed = ed.slotdata.get_installed_chips()
    check("A11 普通芯片仍按用户选择的 +3 写入",
          len(installed) == 2 and installed[1]["level"] == 3,
          str([c["level"] for c in installed]))


def _test_a12(tmp: str) -> None:
    """A12：武器表 39×20B、5 个 int32、等级 1..4、空槽与增删。"""
    print("\nA12 武器表读写与空槽")
    d = os.path.join(tmp, "a12")
    os.makedirs(d)
    gd, sd = make_saves(d)
    s = SaveFile(sd)
    K_WEAPONS_START = K.WEAPONS_START

    ws = s.get_weapons()
    check("A12 武器表固定 39 条", len(ws) == K.WEAPONS_COUNT, str(len(ws)))
    check("A12 初始 39 条全部为空槽", all(w["empty"] for w in ws))
    check("A12 武器表起始偏移 = 0x31D70", K.WEAPONS_START == 0x31D70)
    check("A12 武器记录长度 = 20 字节", K.WEAPON_RECORD_SIZE == 20)
    check("A12 武器表结束偏移 = 0x3207C",
          K.WEAPONS_END == 0x3207C, hex(K.WEAPONS_END))

    check("A12 add_weapon 写入第一个空槽", s.add_weapon(0x042E) is True)
    w = s.get_weapons()[0]
    check("A12 新武器 id/level/new_item/new_story/enemies 正确",
          (w["id"], w["level"], w["new_item"], w["new_story"],
           w["enemies_defeated"]) == (0x042E, 1, 1, 1, 0), str(w))
    check("A12 新武器名称来自 WEAPON_NAMES",
          w["name"] == get_weapon_name(0x042E) == "白之契约", w["name"])

    before = bytes(s._data[K_WEAPONS_START:K_WEAPONS_START + 20])
    s.set_weapon_level(0, 4)
    after = bytes(s._data[K_WEAPONS_START:K_WEAPONS_START + 20])
    diff = [i for i in range(20) if before[i] != after[i]]
    check("A12 改等级只改该条记录第 2 个 int32（偏移 +4..+7）",
          bool(diff) and set(diff) <= set(range(4, 8)), str(diff))
    check("A12 等级回读 4", s.get_weapons()[0]["level"] == 4)
    check("A12 其余 4 个 int32 未变",
          before[:4] == after[:4] and before[8:] == after[8:])

    bad_levels = []
    for bad in (0, -1, 5, 9, "3"):
        try:
            s.set_weapon_level(0, bad)
        except (ValueError, TypeError):
            bad_levels.append(bad)
    check("A12 非法等级 0/-1/5/9/'3' 全部拒绝",
          bad_levels == [0, -1, 5, 9, "3"], str(bad_levels))
    check("A12 非法等级未改变原等级", s.get_weapons()[0]["level"] == 4)

    empty_rejected = False
    try:
        s.set_weapon_level(1, 2)  # index 1 仍是 -1 空槽
    except ValueError:
        empty_rejected = True
    check("A12 空槽改等级被拒绝", empty_rejected)

    idx_rejected = []
    for bad_idx in (-1, K.WEAPONS_COUNT, 100):
        try:
            s.set_weapon_level(bad_idx, 2)
        except IndexError:
            idx_rejected.append(bad_idx)
    check("A12 set_weapon_level 负索引/39/100 抛 IndexError",
          idx_rejected == [-1, K.WEAPONS_COUNT, 100], str(idx_rejected))

    unknown_rejected = False
    try:
        s.add_weapon(0x1234)
    except ValueError:
        unknown_rejected = True
    check("A12 add_weapon 拒绝未知武器 ID", unknown_rejected)

    # 填满 39 个槽，验证「第一个 id == -1」和容量上限
    for _ in range(1, K.WEAPONS_COUNT):
        s.add_weapon(0x03EB)
    check("A12 可以填满 39 个武器槽",
          all(not w["empty"] for w in s.get_weapons()))
    check("A12 无空槽时 add_weapon 返回 False",
          s.add_weapon(0x03EB) is False)

    s.remove_weapon(0)
    raw0 = bytes(s._data[K_WEAPONS_START:K_WEAPONS_START + 20])
    check("A12 remove_weapon 整条写 0xFFFFFFFF",
          raw0 == b"\xff" * 20, raw0.hex())
    check("A12 remove_weapon 后该槽为空", s.get_weapons()[0]["empty"])
    removed_idx_rejected = []
    for bad_idx in (-1, K.WEAPONS_COUNT):
        try:
            s.remove_weapon(bad_idx)
        except IndexError:
            removed_idx_rejected.append(bad_idx)
    check("A12 remove_weapon 越界抛 IndexError",
          removed_idx_rejected == [-1, K.WEAPONS_COUNT], str(removed_idx_rejected))

    size_before = os.path.getsize(sd)
    s.save()
    check("A12 武器修改保存后文件大小不变",
          os.path.getsize(sd) == size_before)
    check("A12 武器修改保存后无 .tmp 残留",
          not [f for f in os.listdir(d) if f.endswith(".tmp")])


def _test_a13(tmp: str) -> None:
    """A13：尸体背包独立只读；背包写入与 sync 绝不碰尸体/武器/芯片。"""
    print("\nA13 尸体背包隔离")
    d = os.path.join(tmp, "a13")
    os.makedirs(d)
    gd, sd = make_saves(d)
    s = SaveFile(sd)

    # 在尸体背包区造两条有效记录（Status 用真实存档里的 -1）
    struct.pack_into("<iii", s._data, K.CORPSE_ITEMS_START, 0x0001, -1, 7)
    struct.pack_into("<iii", s._data, K.CORPSE_ITEMS_START + K.ITEM_RECORD_SIZE,
                     0x0002, -1, 3)
    corpse_before = bytes(s._data[K.CORPSE_ITEMS_START:K.CORPSE_ITEMS_END])
    weapons_before = bytes(s._data[K.WEAPONS_START:K.WEAPONS_END])
    chips_before = bytes(s._data[K.OFFSET_CHIPS_START:K.CHIPS_END])

    check("A13 get_corpse_items 固定 256 条",
          len(s.get_corpse_items()) == K.CORPSE_ITEMS_COUNT,
          str(len(s.get_corpse_items())))
    check("A13 尸体背包读到 2 条有效记录",
          s.get_owned_corpse_items() == [(0x0001, 7), (0x0002, 3)],
          str(s.get_owned_corpse_items()))
    check("A13 get_items 不会把尸体记录算进背包",
          s.get_owned_items() == [], str(s.get_owned_items()))

    s.add_or_update_item(0x0003, 1)
    check("A13 背包添加后尸体区逐字节不变",
          bytes(s._data[K.CORPSE_ITEMS_START:K.CORPSE_ITEMS_END]) == corpse_before)
    check("A13 背包添加后武器区逐字节不变",
          bytes(s._data[K.WEAPONS_START:K.WEAPONS_END]) == weapons_before)
    check("A13 背包添加后芯片区逐字节不变",
          bytes(s._data[K.OFFSET_CHIPS_START:K.CHIPS_END]) == chips_before)
    check("A13 背包添加成功", s.get_owned_items() == [(0x0003, 1)],
          str(s.get_owned_items()))

    # 背包第 255 条写入也不能越过 0x31170
    s.set_item(255, 0x0004, 2)
    check("A13 背包第 255 条仍位于 0x31170 之前",
          s.get_items()[255] == (0x0004, 2))
    check("A13 写背包第 255 条后尸体区仍不变",
          bytes(s._data[K.CORPSE_ITEMS_START:K.CORPSE_ITEMS_END]) == corpse_before)

    src = SaveFile(gd)
    src.set_money(987654)
    src.set_item(0, 0x0005, 9)
    money_before = s.get_money()
    s.sync_money_items_from(src)
    check("A13 sync 后金币来自源存档", s.get_money() == 987654,
          f"{money_before} -> {s.get_money()}")
    check("A13 sync 后背包 256 条与源一致",
          s.get_items() == src.get_items())
    check("A13 sync 不碰尸体背包",
          bytes(s._data[K.CORPSE_ITEMS_START:K.CORPSE_ITEMS_END]) == corpse_before)
    check("A13 sync 不碰武器表",
          bytes(s._data[K.WEAPONS_START:K.WEAPONS_END]) == weapons_before)
    check("A13 sync 不碰芯片表",
          bytes(s._data[K.OFFSET_CHIPS_START:K.CHIPS_END]) == chips_before)
    check("A13 尸体背包没有写入 API",
          not hasattr(s, "set_corpse_item") and not hasattr(s, "add_corpse_item"))


def _test_a14(tmp: str) -> None:
    """A14：背包 256 / 芯片 256 的边界与满容量。"""
    print("\nA14 256 条容量边界")
    d = os.path.join(tmp, "a14")
    os.makedirs(d)
    gd, sd = make_saves(d)
    s = SaveFile(sd)

    check("A14 背包只暴露 256 条", len(s.get_items()) == K.ITEMS_COUNT == 256,
          str(len(s.get_items())))
    check("A14 get_items(999) 仍只返回 256 条",
          len(s.get_items(999)) == 256, str(len(s.get_items(999))))
    money = s.get_money()
    rejected = []
    for bad_idx in (-1, -12, K.ITEMS_COUNT, 600):
        try:
            s.set_item(bad_idx, 0x0000, 1)
        except IndexError:
            rejected.append(bad_idx)
    check("A14 背包索引 -1/-12/256/600 抛 IndexError",
          rejected == [-1, -12, K.ITEMS_COUNT, 600], str(rejected))
    check("A14 越界写入后金币不变", s.get_money() == money)

    s.set_item(255, 0x0000, 5)
    check("A14 背包第 255 条可正常写入",
          s.get_items()[255] == (0x0000, 5), str(s.get_items()[255]))

    s2 = SaveFile(sd)
    for i in range(255):
        s2.set_item(i, 0x0001, 1)
    check("A14 仅剩第 255 槽为空时 add_or_update 成功",
          s2.add_or_update_item(0x0003, 1) is True)
    check("A14 新道具落在第 255 槽",
          s2.get_items()[255] == (0x0003, 1), str(s2.get_items()[255]))
    check("A14 256 条全满后 add_or_update 返回 False",
          s2.add_or_update_item(0x0004, 1) is False)

    # 芯片：256 条上限
    s3 = SaveFile(sd)
    chip = CHIPS.to_bytes("HP最大值UP +3")
    added_all = True
    for _ in range(K.CHIPS_COUNT):
        if not s3.add_chip(chip):
            added_all = False
            break
    check("A14 芯片可写满 256 条", added_all)
    check("A14 get_chips 只返回 256 条",
          len(s3.get_chips()) == K.CHIPS_COUNT == 256,
          str(len(s3.get_chips())))
    check("A14 第 256 条芯片之后 add_chip 返回 False",
          s3.add_chip(chip) is False)
    s3.remove_chip(255)
    check("A14 remove_chip(255) 后该槽为空", s3.get_chips()[255]["empty"])
    check("A14 删除后可以再次添加", s3.add_chip(chip) is True)
    chip_rejected = []
    for bad_idx in (-1, K.CHIPS_COUNT, 600):
        try:
            s3.remove_chip(bad_idx)
        except IndexError:
            chip_rejected.append(bad_idx)
    check("A14 芯片索引 -1/256/600 抛 IndexError",
          chip_rejected == [-1, K.CHIPS_COUNT, 600], str(chip_rejected))
    check("A14 布局常量首尾相接",
          K.ITEMS_END == K.CORPSE_ITEMS_START
          and K.CORPSE_ITEMS_END == K.WEAPONS_START
          and K.WEAPONS_END <= K.OFFSET_CHIPS_START)

    size_before = os.path.getsize(sd)
    s3.save()
    check("A14 满容量芯片保存后文件大小不变",
          os.path.getsize(sd) == size_before)
    check("A14 满容量芯片保存后无 .tmp 残留",
          not [f for f in os.listdir(d) if f.endswith(".tmp")])


def _test_a15(tmp: str) -> None:
    """A15：武器 tab（只读下拉框 / 等级 1..4 / 增删 / 只写 SlotData）。"""
    print("\nA15 武器 tab（GUI 对象级）")
    d = os.path.join(tmp, "a15")
    os.makedirs(d)
    gd, sd = make_saves(d)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)
    nier_editor.messagebox.askyesno = lambda *a, **k: True

    ui = object.__new__(nier_editor.NierSaveEditor)
    ui.weapon_tab = _FakeWidget()
    ui._build_weapon_tab()
    check("A15 武器添加下拉框 state=readonly",
          ui.weapon_add_cb.cget("state") == "readonly",
          str(ui.weapon_add_cb.cget("state")))
    values = list(ui.weapon_add_cb.kwargs.get("values", []))
    check("A15 武器下拉框正好 39 项", len(values) == 39, str(len(values)))
    parsed = [int(v.rsplit("0x", 1)[1].rstrip(")"), 16) for v in values]
    check("A15 武器下拉框全部来自 WEAPON_NAMES",
          set(parsed) == set(WEAPON_NAMES), str(set(parsed) ^ set(WEAPON_NAMES)))
    check("A15 武器下拉框不含道具 ID",
          not any(i in ITEM_NAMES for i in parsed))

    ed = _make_editor(nier_editor, gd, sd)
    ed.weapon_tree = _FakeTree()
    ed.weapon_count_label = _FakeWidget()
    nier_editor.NierSaveEditor._refresh_weapons(ed)
    check("A15 武器列表列出 39 条", len(ed.weapon_tree.rows) == 39,
          str(len(ed.weapon_tree.rows)))
    check("A15 空存档 39 条均显示未获得",
          all(r[1][2] == "未获得" for r in ed.weapon_tree.rows))

    ed.weapon_add_var.set("白之契约 (0x042E)")
    msgs["warning"].clear()
    ed._add_weapon()
    check("A15 GUI 添加武器写入 SlotData",
          ed.slotdata.get_weapons()[0]["id"] == 0x042E
          and ed.slotdata.get_weapons()[0]["level"] == 1,
          str(ed.slotdata.get_weapons()[0]))
    check("A15 添加武器设置脏标记", ed._weapons_dirty is True)
    nier_editor.NierSaveEditor._refresh_weapons(ed)
    check("A15 添加后列表中有一把已获得",
          sum(1 for r in ed.weapon_tree.rows if r[1][2] == "已获得") == 1)

    msgs["warning"].clear()
    ed._add_weapon()
    check("A15 重复添加同一武器被拒绝且提示",
          bool(msgs["warning"]) and "已经拥有" in msgs["warning"][-1][1]
          and sum(1 for w in ed.slotdata.get_weapons() if not w["empty"]) == 1,
          f"warnings={msgs['warning']}")

    ed._get_selected_weapon_index = lambda: 0
    ed.weapon_level_var.set(4)
    msgs["error"].clear()
    ed._set_weapon_level()
    check("A15 GUI 改等级 4 成功",
          ed.slotdata.get_weapons()[0]["level"] == 4 and not msgs["error"],
          str(ed.slotdata.get_weapons()[0]))
    for bad in (0, 5):
        ed.weapon_level_var.set(bad)
        msgs["warning"].clear()
        ed._set_weapon_level()
        check(f"A15 GUI 非法等级 {bad} 被拒绝且不写入",
              ed.slotdata.get_weapons()[0]["level"] == 4
              and bool(msgs["warning"]))

    # 只改武器时，保存只写 SlotData，GameData 逐字节不变
    gd_before = open(gd, "rb").read()
    ed.save_folder = nier_editor.tk.StringVar(d)
    ed.cur_slot = nier_editor.tk.IntVar(0)
    ed._load_weapon_gui = True
    msgs["info"].clear()
    ed._save_all()
    check("A15 只改武器保存成功并提示", bool(msgs["info"]),
          str(msgs["info"]))
    check("A15 只改武器时 GameData 逐字节不变",
          open(gd, "rb").read() == gd_before)
    check("A15 只改武器时 SlotData 已写盘",
          SaveFile(sd).get_weapons()[0]["level"] == 4)
    check("A15 保存后武器脏标记清零", ed._weapons_dirty is False)
    check("A15 只改武器保存后无 .tmp 残留",
          not [f for f in os.listdir(d) if f.endswith(".tmp")])

    ed._get_selected_weapon_index = lambda: 0
    ed._remove_weapon()
    check("A15 GUI 删除武器后该槽为空",
          ed.slotdata.get_weapons()[0]["empty"] is True)


def _test_a17(tmp: str) -> None:
    """A17：真实存档回归（只读 fixture，复制到临时目录后验证）。"""
    print("\nA17 真实存档回归")
    fixture = "/srv/aiwork/nier-fixture"
    if not os.path.isdir(fixture):
        print("  ⏭ 未找到 /srv/aiwork/nier-fixture，跳过（不影响合成用例）")
        return
    d = os.path.join(tmp, "a17")
    os.makedirs(d)
    src_hash = {}
    for name in ("GameData.dat", "SlotData_0.dat", "SlotData_1.dat"):
        src = os.path.join(fixture, name)
        dst = os.path.join(d, name)
        shutil.copyfile(src, dst)
        src_hash[name] = hashlib.sha256(open(src, "rb").read()).hexdigest()

    gd = SaveFile(os.path.join(d, "GameData.dat"))
    s0 = SaveFile(os.path.join(d, "SlotData_0.dat"))
    s1 = SaveFile(os.path.join(d, "SlotData_1.dat"))

    check("A17 GameData 背包 64 条", len(gd.get_owned_items()) == 64,
          str(len(gd.get_owned_items())))
    check("A17 GameData 武器 0 把（全 0 占位按空槽展示）",
          sum(1 for w in gd.get_weapons() if not w["empty"]) == 0)
    check("A17 GameData 已装芯片 0 条", len(gd.get_installed_chips()) == 0)

    check("A17 SlotData_0 背包 0 条", len(s0.get_owned_items()) == 0,
          str(len(s0.get_owned_items())))
    check("A17 SlotData_0 的 13 条记录位于尸体背包（不是背包）",
          len(s0.get_owned_corpse_items()) == 13,
          str(len(s0.get_owned_corpse_items())))
    check("A17 SlotData_0 武器 1 把",
          sum(1 for w in s0.get_weapons() if not w["empty"]) == 1)
    check("A17 SlotData_0 已装芯片 15 条",
          len(s0.get_installed_chips()) == 15,
          str(len(s0.get_installed_chips())))

    check("A17 SlotData_1 背包 64 条", len(s1.get_owned_items()) == 64,
          str(len(s1.get_owned_items())))
    weapons = [w for w in s1.get_weapons() if not w["empty"]]
    check("A17 SlotData_1 武器 9 把", len(weapons) == 9, str(len(weapons)))
    check("A17 SlotData_1 武器等级集合 {1,2,3}",
          {w["level"] for w in weapons} == {1, 2, 3},
          str(sorted(w["level"] for w in weapons)))
    check("A17 SlotData_1 已装芯片 151 条",
          len(s1.get_installed_chips()) == 151,
          str(len(s1.get_installed_chips())))
    auto_names = {CHIPS.to_name(c["raw"][:12]) for c in s1.get_installed_chips()}
    check("A17 真实存档里的 5 个 Auto 芯片全部可识别",
          {"自动攻击", "自动射击", "自动闪避", "自动骇入", "自动换武器"}
          <= auto_names, str(sorted(auto_names)))
    check("A17 HUD 钓鱼提示映射为 0x012B/0x0D19/0x3A",
          CHIPS.to_bytes("HUD：钓鱼提示")[:12]
          == bytes.fromhex("2b010000190d00003a000000"))

    after_hash = {name: hashlib.sha256(
        open(os.path.join(fixture, name), "rb").read()).hexdigest()
        for name in src_hash}
    check("A17 fixture 原始文件 sha256 完全不变",
          after_hash == src_hash, str(after_hash))


def _test_a18(tmp: str) -> None:
    """A18：数据表拆分与 5 个 Auto 芯片的定义。"""
    print("\nA18 数据表 / Auto 芯片")
    check("A18 ITEM_NAMES 恰好 221 条", len(ITEM_NAMES) == 221,
          str(len(ITEM_NAMES)))
    check("A18 WEAPON_NAMES 恰好 39 把", len(WEAPON_NAMES) == 39,
          str(len(WEAPON_NAMES)))
    check("A18 道具表与武器表无交集",
          not (set(ITEM_NAMES) & set(WEAPON_NAMES)))
    check("A18 分类条目总数 = 221",
          sum(ITEM_CATEGORIES.values()) == 221, str(ITEM_CATEGORIES))
    check("A18 分类区间不再含武器分类",
          not any("武器" in c for c in CATEGORY_ORDER), str(CATEGORY_ORDER))
    check("A18 白之契约在武器表", get_weapon_name(0x042E) == "白之契约")
    check("A18 白之契约不在道具表",
          get_item_name(0x042E).startswith("未知"))
    check("A18 武器不属于任何道具分类", get_category(0x042E) == "其他")
    check("A18 搜索道具不会搜出武器", search_items("白之契约") == [])
    check("A18 道具添加下拉框数据源不含武器",
          not any(is_weapon(i) for i in ITEM_NAMES))

    expected = {
        "自动攻击": bytes.fromhex("f80000001a0d00003b0000000000000001000000"),
        "自动射击": bytes.fromhex("f90000001b0d00003c0000000000000001000000"),
        "自动闪避": bytes.fromhex("fa0000001c0d00003d0000000000000001000000"),
        "自动骇入": bytes.fromhex("fb0000001d0d00003e0000000000000001000000"),
        "自动换武器": bytes.fromhex("fc0000001e0d00003f0000000000000001000000"),
    }
    for name, head20 in expected.items():
        check(f"A18 {name} 已在系统芯片表", name in CHIPS.unique_names)
        check(f"A18 {name} 20 字节头与真实存档一致",
              CHIPS.to_bytes(name)[:20] == head20,
              CHIPS.to_bytes(name)[:20].hex())
        check(f"A18 {name} 可反查名称",
              CHIPS.to_name(head20[:12]) == name,
              CHIPS.to_name(head20[:12]))


def _test_a16(tmp: str) -> None:
    """A16：sync 目标长度不足时抛 SaveError，不扩容、不改 _save_size。"""
    print("\nA16 sync_money_items_from 不扩容")
    d = os.path.join(tmp, "a16")
    os.makedirs(d)
    gd, sd = make_saves(d)
    src = SaveFile(sd)
    end_offset = K.OFFSET_ITEMS_START + K.SLOT_MAX_ITEMS * K.ITEM_RECORD_SIZE

    dst = object.__new__(SaveFile)
    dst.filepath = gd
    dst._data = bytearray(1000)
    dst._original_size = 1000
    dst._save_size = 1000
    dst._modified = False
    dst._pending_tmp = None
    try:
        dst.sync_money_items_from(src)
        raised = False
    except SaveError:
        raised = True
    check("A16 目标长度不足时抛 SaveError", raised)
    check("A16 失败后内存长度不变（不 extend）", len(dst._data) == 1000, str(len(dst._data)))
    check("A16 失败后 _save_size 不变", dst._save_size == 1000 and not dst._modified,
          f"_save_size={dst._save_size}, modified={dst._modified}")
    check("A16 所需长度确实大于测试目标（用例有效）", end_offset > len(dst._data),
          f"need={end_offset}, have={len(dst._data)}")

    g = SaveFile(gd)
    before_len, before_save_size = len(g._data), g._save_size
    g.sync_money_items_from(src)
    check("A16 合法长度同步后仍不扩容",
          len(g._data) == before_len and g._save_size == before_save_size,
          f"{before_len}->{len(g._data)}, _save_size={g._save_size}")

def main() -> int:
    print("数据表")
    check("道具表 221 条（不含武器）", len(ITEM_NAMES) == 221,
          f"实际 {len(ITEM_NAMES)}")
    check("武器表 39 把（独立 WEAPON_NAMES）", len(WEAPON_NAMES) == 39,
          f"实际 {len(WEAPON_NAMES)}")
    check("小恢复药 = 0x0000", get_item_name(0) == "小恢复药")
    check("白之契约在武器表 = 0x042E", get_weapon_name(0x042E) == "白之契约")
    check("武器不在道具表",
          get_item_name(0x042E) != "白之契约")
    check("武器不再属于道具分类", get_category(0x042E) == "其他",
          get_category(0x042E))
    check("道具分类条目数合计 221",
          sum(ITEM_CATEGORIES.values()) == 221, str(ITEM_CATEGORIES))
    check("分类区间已删除武器分类",
          not any("武器" in c for c in CATEGORY_ORDER), str(CATEGORY_ORDER))

    tmp = tempfile.mkdtemp(prefix="nier-selftest-")
    try:
        gd, sd = make_saves(tmp)

        print("\n载入")
        g, s = SaveFile(gd), SaveFile(sd)
        check("GameData 载入", g.get_money() == 5000)
        check("SlotData 载入", s.get_money() == 5000)
        check("SlotData 背包只有 256 条",
              len(s.get_items()) == K.ITEMS_COUNT == 256,
              str(len(s.get_items())))

        print("\n写入")
        s.add_or_update_item(0x0000, 7, limit=K.ITEMS_COUNT)  # 小恢复药
        owned = dict(s.get_owned_items())
        check("小恢复药写入（id=0 不被当空槽）", owned.get(0) == 7, str(owned))
        check("道具写入只落在背包 256 条", len(owned) == 1, str(owned))

        chip = CHIPS.to_bytes("HP最大值UP +3")
        check("芯片写入", s.add_chip(chip))
        check("芯片等级回读", s.get_installed_chips()[0]["level"] == 3)
        s.remove_chip(0)
        check("芯片删除后判空", s.get_chips()[0]["empty"])
        check("删除后无已装芯片", not s.get_installed_chips())

        print("\n保存")
        before = (os.path.getsize(gd), os.path.getsize(sd))
        g.sync_money_items_from(s)
        g.set_money(8888)
        s.set_money(8888)
        g.save()
        s.save()
        after = (os.path.getsize(gd), os.path.getsize(sd))
        check("文件大小不变（不扩容）", before == after,
              f"{before} -> {after}")
        check("无残留 .tmp",
              not [f for f in os.listdir(tmp) if f.endswith(".tmp")])

        g2, s2 = SaveFile(gd), SaveFile(sd)
        check("金币回读", g2.get_money() == 8888 and s2.get_money() == 8888)
        check("道具回读", dict(s2.get_owned_items()).get(0) == 7)
        check("GameData 与 SlotData 背包区一致",
              g2.get_items(K.ITEMS_COUNT) == s2.get_items(K.ITEMS_COUNT))

        print("\n非法文件")
        bad = os.path.join(tmp, "GameData_truncated.dat")
        with open(bad, "wb") as f:
            f.write(b"\x00" * 1000)
        try:
            SaveFile(bad)
            check("截断文件被拒绝", False)
        except SaveError:
            check("截断文件被拒绝", True)

        # 回归用例（含真实存档；真实存档只复制到临时目录，结束时整体删除）
        _test_a1(tmp)
        _test_a2(tmp)
        _test_a4(tmp)
        _test_a6(tmp)
        _test_a7(tmp)
        _test_a8(tmp)
        _test_a9(tmp)
        _test_a10(tmp)
        _test_a11(tmp)
        _test_a12(tmp)
        _test_a13(tmp)
        _test_a14(tmp)
        _test_a15(tmp)
        _test_a16(tmp)
        _test_a17(tmp)
        _test_a18(tmp)
    finally:
        # 不留真实存档副本，也不留测试临时文件
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
