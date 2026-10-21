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
from item_data import get_item_name, get_category, is_weapon, ITEM_NAMES
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
    # 芯片区：全 0xFF = 空
    s[K.OFFSET_CHIPS_START:K.OFFSET_CHIPS_START + K.MAX_CHIPS * K.CHIP_RECORD_SIZE] = (
        b"\xff" * (K.MAX_CHIPS * K.CHIP_RECORD_SIZE)
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
    ed._chips_dirty = False
    ed._refresh_money = lambda: None
    ed._refresh_items = lambda: None
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
    ed._chips_dirty = False
    ed._refresh_money = lambda: None
    ed._refresh_items = lambda: None
    ed._refresh_chips = lambda: None
    ed.item_amount_var = nier_editor.tk.StringVar("1")
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
    """A12：武器增/减/设数量强制 1、重复添加不累加、列表显示 1。"""
    print("\nA12 武器数量（GUI 对象级）")
    d = os.path.join(tmp, "a12")
    os.makedirs(d)
    gd, sd = make_saves(d)
    _install_gui_stubs()
    import nier_editor
    _prepare_gui_stubs(nier_editor)
    msgs = _capture_messagebox(nier_editor)

    weapon = 0x042E  # 白之契约
    ed = _make_editor(nier_editor, gd, sd)
    ed.gamedata.set_item(0, weapon, 1)
    ed.slotdata.set_item(0, weapon, 1)
    ed._get_selected_item_index = lambda: (0, weapon, ed.slotdata.get_item(weapon))
    ed.item_amount_var.set("10")

    for direction in (1, -1, 0):
        msgs["warning"].clear()
        try:
            ed._mod_item(direction)
            crashed = False
        except Exception:
            crashed = True
        check(f"A12 武器 direction={direction} 强制数量 1 并提示不可堆叠",
              not crashed and ed.slotdata.get_item(weapon) == 1
              and ed.gamedata.get_item(weapon) == 1
              and bool(msgs["warning"])
              and "武器" in msgs["warning"][-1][0],
              f"amount={ed.slotdata.get_item(weapon)}, warnings={msgs['warning']}")

    ed2 = _make_editor(nier_editor, gd, sd)
    ed2.item_add_var = nier_editor.tk.StringVar("白之契约 (0x042E)")
    msgs["warning"].clear()
    ed2._add_item()
    check("A12 下拉框添加武器使用数量 1",
          ed2.slotdata.get_item(weapon) == 1,
          f"amount={ed2.slotdata.get_item(weapon)}")
    msgs["warning"].clear()
    ed2._add_item()
    check("A12 重复添加同一武器不会累加到 2",
          ed2.slotdata.get_item(weapon) == 1
          and bool(msgs["warning"])
          and "武器" in msgs["warning"][-1][0],
          f"amount={ed2.slotdata.get_item(weapon)}, warnings={msgs['warning']}")

    ed3 = _make_editor(nier_editor, gd, sd)
    ed3.item_tree = _FakeTree()
    ed3.item_search_var = nier_editor.tk.StringVar("")
    ed3.item_cat_var = nier_editor.tk.StringVar("全部")
    ed3.show_all_var = nier_editor.tk.BooleanVar(False)
    ed3.slotdata.set_item(0, weapon, 5)  # 模拟旧存档里的非法堆叠
    nier_editor.NierSaveEditor._refresh_items(ed3)  # 实例上 _refresh_items 已被替身覆盖
    weapon_rows = [r for r in ed3.item_tree.rows
                   if r[1] and r[1][2] == f"0x{weapon:04X}"]
    check("A12 道具列表武器行数量列显示 1",
          len(weapon_rows) == 1 and weapon_rows[0][1][1] == 1,
          str([r[1] for r in weapon_rows]))


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
    check("道具 + 武器共 260 条", len(ITEM_NAMES) == 260, f"实际 {len(ITEM_NAMES)}")
    check("武器 39 把", sum(1 for i in ITEM_NAMES if is_weapon(i)) == 39)
    check("小恢复药 = 0x0000", get_item_name(0) == "小恢复药")
    check("白之契约 = 0x042E", get_item_name(0x042E) == "白之契约")
    check("武器分类正确", get_category(0x042E) == "武器·小型剑", get_category(0x042E))

    tmp = tempfile.mkdtemp(prefix="nier-selftest-")
    gd, sd = make_saves(tmp)

    print("\n载入")
    g, s = SaveFile(gd), SaveFile(sd)
    check("GameData 载入", g.get_money() == 5000)
    check("SlotData 载入", s.get_money() == 5000)
    check("SlotData 道具只有 512 条", len(s.get_items()) == K.SLOT_MAX_ITEMS, str(len(s.get_items())))

    print("\n写入")
    s.add_or_update_item(0x0000, 7, limit=K.SLOT_MAX_ITEMS)      # 小恢复药
    s.add_or_update_item(0x042E, 1, limit=K.SLOT_MAX_ITEMS)      # 白之契约
    owned = dict(s.get_owned_items())
    check("小恢复药写入（id=0 不被当空槽）", owned.get(0) == 7, str(owned))
    check("武器写入", owned.get(0x042E) == 1)
    check("武器名称", get_item_name(0x042E) == "白之契约")

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
    check("文件大小不变（不扩容）", before == after, f"{before} -> {after}")
    check("无残留 .tmp", not [f for f in os.listdir(tmp) if f.endswith(".tmp")])

    g2, s2 = SaveFile(gd), SaveFile(sd)
    check("金币回读", g2.get_money() == 8888 and s2.get_money() == 8888)
    check("道具回读", dict(s2.get_owned_items()).get(0x042E) == 1)
    check("GameData 与 SlotData 道具区一致",
          g2.get_items(K.SLOT_MAX_ITEMS) == s2.get_items(K.SLOT_MAX_ITEMS))

    print("\n非法文件")
    bad = os.path.join(tmp, "GameData_truncated.dat")
    with open(bad, "wb") as f:
        f.write(b"\x00" * 1000)
    try:
        SaveFile(bad)
        check("截断文件被拒绝", False)
    except SaveError:
        check("截断文件被拒绝", True)

    # 本次修复新增的回归用例（A1 用无 GUI 的对象级复现）
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
    _test_a16(tmp)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
