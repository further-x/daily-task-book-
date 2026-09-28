"""A native Windows task planner with a card-based interface."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

from task_store import DIFFICULTIES, Store


ctk.set_default_color_theme("blue")

PALETTES = {
    "海蓝": dict(bg="#F3F8FF", card="#FFFFFF", text="#152A44", muted="#657994", accent="#2F64C4", navy="#192D47", border="#D9E5F5", soft="#EAF2FF", gold="#CA861D"),
    "玫瑰": dict(bg="#FFF5F8", card="#FFFFFF", text="#45263A", muted="#93677E", accent="#A74F79", navy="#59374C", border="#F0DDE6", soft="#FCEAF1", gold="#C98927"),
    "森林": dict(bg="#F0F8F4", card="#FFFFFF", text="#183A31", muted="#648579", accent="#2F8068", navy="#1E4D3F", border="#D6E9DF", soft="#E3F3EA", gold="#C98927"),
    "深夜": dict(bg="#152035", card="#22314A", text="#F3F6FB", muted="#AEBED0", accent="#79A8FF", navy="#263E60", border="#405570", soft="#2E4668", gold="#F2B350"),
}
OLD_THEMES = {"浅色": "海蓝", "深色": "深夜", "薄荷": "森林", "暖橘": "玫瑰"}
FONT = "Microsoft YaHei UI"


def label(parent, text, size=15, weight="normal", color=None, **kwargs):
    return ctk.CTkLabel(parent, text=text, font=(FONT, size, weight), text_color=color, **kwargs)


class FormDialog(ctk.CTkToplevel):
    def __init__(self, owner, title, fields, initial=None):
        super().__init__(owner)
        self.owner = owner
        self.result = None
        self.title(title)
        self.geometry("480x640" if "备注" in fields else "480x440")
        self.resizable(False, False)
        self.configure(fg_color=owner.p["bg"])
        self.transient(owner)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _: self.destroy())
        body = ctk.CTkFrame(self, fg_color=owner.p["card"], corner_radius=22, border_width=1, border_color=owner.p["border"])
        body.pack(fill="both", expand=True, padx=22, pady=22)
        # Reserve footer space first so the form can never squeeze the buttons.
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=24, pady=20)
        self.cancel_button = owner.button(bar, "取消", self.destroy, filled=False, width=100)
        self.cancel_button.pack(side="right", padx=(10, 0))
        self.save_button = owner.button(bar, "保存", self.save, width=100)
        self.save_button.pack(side="right")
        form = ctk.CTkFrame(body, fg_color="transparent")
        form.pack(fill="both", expand=True)
        label(form, title, 22, "bold", owner.p["text"]).pack(anchor="w", padx=24, pady=(20, 10))
        self.controls = {}
        initial = initial or {}
        for key, config in fields.items():
            label(form, key, 13, "bold", owner.p["muted"]).pack(anchor="w", padx=24, pady=(8, 3))
            if config == "difficulty":
                control = ctk.CTkOptionMenu(form, values=list(DIFFICULTIES), fg_color=owner.p["soft"], button_color=owner.p["accent"], text_color=owner.p["text"], width=410, height=37)
                control.set(initial.get(key, "普通"))
            elif config == "category":
                control = ctk.CTkComboBox(form, values=owner.store.categories(), width=410, height=37,
                                         fg_color=owner.p["bg"], border_color=owner.p["border"],
                                         button_color=owner.p["accent"], text_color=owner.p["text"],
                                         dropdown_fg_color=owner.p["card"], dropdown_text_color=owner.p["text"],
                                         font=(FONT, 13), dropdown_font=(FONT, 13))
                control.set(initial.get(key, "日常"))
            elif config == "note":
                control = ctk.CTkTextbox(form, height=58, fg_color=owner.p["bg"], border_width=1, border_color=owner.p["border"], text_color=owner.p["text"], font=(FONT, 13))
                control.insert("1.0", initial.get(key, ""))
            else:
                control = ctk.CTkEntry(form, width=410, height=37, fg_color=owner.p["bg"], border_color=owner.p["border"], text_color=owner.p["text"], font=(FONT, 13))
                control.insert(0, initial.get(key, ""))
            control.pack(fill="x", padx=24)
            self.controls[key] = control
        self.after(100, lambda: self.focus_force())

    def save(self):
        values = {}
        for key, control in self.controls.items():
            values[key] = (control.get("1.0", "end") if isinstance(control, ctk.CTkTextbox) else control.get()).strip()
        self.result = values
        self.destroy()


class App(ctk.CTk):
    def __init__(self, data_path=None):
        super().__init__()
        self.store = Store(data_path)
        saved = self.store.setting("theme", "海蓝")
        self.theme_name = OLD_THEMES.get(saved, saved) if saved in OLD_THEMES or saved in PALETTES else "海蓝"
        self.page = "tasks"
        self.task_filter = "全部"
        self.cal_year = date.today().year
        self.cal_month = date.today().month
        self.title("今日清单 · 桌面版")
        self.geometry("1320x900")
        self.minsize(1024, 700)
        self._set_palette()
        self.content = ctk.CTkScrollableFrame(self, fg_color=self.p["bg"], corner_radius=0, scrollbar_button_color=self.p["border"], scrollbar_button_hover_color=self.p["accent"])
        self.content.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_page("tasks")
        self._day_seen = date.today()
        self._day_timer = self.after(1000, self._check_day)

    def close(self):
        if hasattr(self, "_day_timer"):
            self.after_cancel(self._day_timer)
        self.store.close()
        self.destroy()

    def _check_day(self):
        today = date.today()
        if today != self._day_seen:
            self._day_seen = today
            self.store.archive_previous_days(today)
            self._date_text.configure(text=f"{today.year}年{today.month}月{today.day}日  星期{'一二三四五六日'[today.weekday()]}")
            self.show_page(self.page)
        self._day_timer = self.after(1000, self._check_day)

    def _set_palette(self):
        self.p = PALETTES[self.theme_name].copy()
        custom = self.store.setting("background")
        if custom:
            self.p["bg"] = custom
        ctk.set_appearance_mode("dark" if self.theme_name == "深夜" else "light")
        self.configure(fg_color=self.p["bg"])

    def button(self, parent, text, command, filled=True, width=125, height=40, **kwargs):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=height, corner_radius=13,
                             fg_color=self.p["accent"] if filled else self.p["card"],
                             hover_color=self.p["navy"] if filled else self.p["soft"],
                             text_color="#FFFFFF" if filled else self.p["text"],
                             border_width=0 if filled else 1, border_color=self.p["border"],
                             font=(FONT, 14, "bold"), **kwargs)

    def card(self, parent, **kwargs):
        options = dict(fg_color=self.p["card"], corner_radius=24, border_width=1, border_color=self.p["border"])
        options.update(kwargs)
        return ctk.CTkFrame(parent, **options)

    def show_page(self, page):
        self.store.archive_previous_days()
        self.page = page
        palette_key = tuple(self.p.items())
        if getattr(self, "_layout_palette", None) != palette_key:
            self.content.configure(fg_color=self.p["bg"])
            for child in self.content.winfo_children():
                child.destroy()
            self._layout_palette = palette_key
            self._pages = {}
            self._page_versions = {}
            shell = ctk.CTkFrame(self.content, fg_color="transparent")
            shell.pack(fill="both", expand=True, padx=35, pady=(27, 35))
            self._header(shell)
            self._hero(shell)
            self._page_host = ctk.CTkFrame(shell, fg_color="transparent")
            self._page_host.pack(fill="both", expand=True)
            self._page_host.grid_columnconfigure(0, weight=1)
            # Build once before first display; navigation only swaps cached frames.
            for name in ("tasks", "calendar", "shop", "settings"):
                self._build_page(name)
        version = (self.store.db.total_changes, self.cal_year, self.cal_month)
        if page == "tasks":
            self._refresh_task_rows()
        elif self._page_versions.get(page) != version:
            self._build_page(page)
        for name, frame in self._pages.items():
            if name == page:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()
        for name, button in self._nav_buttons.items():
            active = name == page
            button.configure(fg_color=self.p["navy"] if active else "transparent",
                             hover_color=self.p["navy"] if active else self.p["soft"],
                             text_color="#FFFFFF" if active else self.p["muted"])
        self._refresh_hero()

    def _build_page(self, name):
        frame = ctk.CTkFrame(self._page_host, fg_color="transparent")
        builders = {"tasks": self._tasks_page, "calendar": self._calendar_page,
                    "shop": self._shop_page, "settings": self._settings_page}
        builders[name](frame)
        old = self._pages.get(name)
        self._pages[name] = frame
        self._page_versions[name] = (self.store.db.total_changes, self.cal_year, self.cal_month)
        if old:
            old.destroy()

    def _header(self, shell):
        row = ctk.CTkFrame(shell, fg_color="transparent")
        row.pack(fill="x", pady=(0, 26))
        mark = ctk.CTkFrame(row, width=54, height=54, corner_radius=17, fg_color=self.p["navy"])
        mark.pack(side="left", padx=(0, 15))
        mark.pack_propagate(False)
        label(mark, "✓", 33, "bold", "#FFCA70").pack(expand=True)
        title_box = ctk.CTkFrame(row, fg_color="transparent")
        title_box.pack(side="left")
        label(title_box, "今日清单", 25, "bold", self.p["text"]).pack(anchor="w")
        today = date.today()
        self._date_text = label(title_box, f"{today.year}年{today.month}月{today.day}日  星期{'一二三四五六日'[today.weekday()]}", 14, color=self.p["muted"])
        self._date_text.pack(anchor="w")
        nav = self.card(row, corner_radius=18)
        nav.pack(side="right")
        self._nav_buttons = {}
        for key, text in (("tasks", "我的任务"), ("calendar", "成就日历"), ("shop", "奖励商城"), ("settings", "个性设置")):
            active = key == self.page
            button = ctk.CTkButton(nav, text=text, command=lambda k=key: self.show_page(k), width=103, height=43, corner_radius=13,
                          fg_color=self.p["navy"] if active else "transparent", hover_color=self.p["navy"] if active else self.p["soft"],
                          text_color="#FFFFFF" if active else self.p["muted"], font=(FONT, 14, "bold"))
            button.pack(side="left", padx=3, pady=5)
            self._nav_buttons[key] = button

    def _hero(self, shell):
        row = ctk.CTkFrame(shell, fg_color="transparent")
        row.pack(fill="x", pady=(0, 27))
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_rowconfigure(0, minsize=190)
        progress = ctk.CTkFrame(row, fg_color=self.p["navy"], corner_radius=25, height=184)
        progress.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        progress.grid_propagate(False)
        label(progress, "TODAY'S PROGRESS", 12, "bold", "#C3D2E5").pack(anchor="w", padx=32, pady=(28, 10))
        today = date.today().isoformat()
        total = len(self.store.tasks_for_day(today))
        completed = self.store.completed_on(today)
        headline = "今天，从一件小事开始" if completed == 0 else "每一步，都值得记录"
        self._headline = label(progress, headline, 27, "bold", "#FFFFFF")
        self._headline.pack(anchor="w", padx=32)
        self._progress_text = label(progress, f"今天已完成 {completed} 项任务  ·  今日计划 {total} 项", 16, color="#DDE9F9")
        self._progress_text.pack(anchor="w", padx=32, pady=(7, 0))
        balance = self.card(row, height=184)
        balance.grid(row=0, column=1, sticky="nsew")
        balance.grid_propagate(False)
        label(balance, "我的金币", 15, color=self.p["muted"]).pack(anchor="w", padx=26, pady=(26, 3))
        self._balance_text = label(balance, f"{self.store.balance()}  🪙", 34, "bold", self.p["gold"])
        self._balance_text.pack(anchor="w", padx=26)
        self._redemption_text = label(balance, f"累计兑换 {self.store.redemption_count()} 次奖励", 13, color=self.p["muted"])
        self._redemption_text.pack(anchor="w", padx=26, pady=(3, 0))

    def _refresh_hero(self):
        today = date.today().isoformat()
        completed = self.store.completed_on(today)
        self._headline.configure(text="今天，从一件小事开始" if completed == 0 else "每一步，都值得记录")
        self._progress_text.configure(text=f"今天已完成 {completed} 项任务  ·  今日计划 {len(self.store.tasks_for_day(today))} 项")
        self._balance_text.configure(text=f"{self.store.balance()}  🪙")
        self._redemption_text.configure(text=f"累计兑换 {self.store.redemption_count()} 次奖励")

    def _section_head(self, shell, title, button_text=None, command=None):
        head = ctk.CTkFrame(shell, fg_color="transparent")
        head.pack(fill="x", pady=(0, 13))
        label(head, title, 23, "bold", self.p["text"]).pack(side="left")
        if button_text:
            self.button(head, button_text, command, width=136).pack(side="right")
        return head

    def _chip(self, parent, text, active, command):
        return ctk.CTkButton(parent, text=text, command=command, width=max(62, 28 + len(text) * 16), height=37, corner_radius=19,
                             fg_color=self.p["soft"] if active else self.p["card"], hover_color=self.p["soft"],
                             text_color=self.p["accent"] if active else self.p["muted"], border_width=1,
                             border_color=self.p["accent"] if active else self.p["border"], font=(FONT, 13))

    def _tasks_page(self, shell):
        self._section_head(shell, "任务清单", "＋ 添加任务", self.add_task)
        filters = ctk.CTkFrame(shell, fg_color="transparent")
        filters.pack(fill="x", pady=(0, 14))
        self._filter_host = filters
        self._filter_buttons = {}
        self._task_widgets = {}
        self._task_box = self.card(shell)
        self._task_box.pack(fill="x")
        self._empty_tasks = label(self._task_box, "这里还没有任务。添加一件今天想完成的小事吧。", 16, color=self.p["muted"])
        self._refresh_task_rows()

    def _refresh_task_rows(self):
        names = list(dict.fromkeys(["全部", "今天", "待完成", "已完成"] + self.store.categories()))
        for name in names:
            if name not in self._filter_buttons:
                chip = self._chip(self._filter_host, name, False, lambda n=name: self.set_task_filter(n))
                chip.pack(side="left", padx=(0, 8))
                self._filter_buttons[name] = chip
            active = name == self.task_filter
            self._filter_buttons[name].configure(fg_color=self.p["soft"] if active else self.p["card"],
                                                text_color=self.p["accent"] if active else self.p["muted"],
                                                border_color=self.p["accent"] if active else self.p["border"])
        rows = list(self.store.tasks())
        ids = {r["id"] for r in rows}
        for task_id in list(self._task_widgets):
            if task_id not in ids:
                self._task_widgets.pop(task_id)["row"].destroy()
        for task in rows:
            task_id = task["id"]
            metadata = tuple(task[k] for k in ("title", "category", "difficulty", "due_date", "notes"))
            widget = self._task_widgets.get(task_id)
            if widget and widget["metadata"] != metadata:
                widget["row"].destroy()
                widget = None
            if widget is None:
                widget = self._task_row(self._task_box, task)
                widget["metadata"] = metadata
                self._task_widgets[task_id] = widget
            done = bool(task["completed_at"])
            widget["check"].configure(text="✓" if done else "", fg_color=self.p["accent"] if done else self.p["card"],
                                      hover_color=self.p["accent"] if done else self.p["soft"], border_width=0 if done else 2)
            widget["title"].configure(text_color=self.p["muted"] if done else self.p["text"])
            coins = task["earned_coins"] if done else self.store.rewards()[task["difficulty"]]
            widget["coins"].configure(text=f"+ {coins}  🪙")
        if self.task_filter == "今天":
            rows = [r for r in rows if r["due_date"] == date.today().isoformat()]
        elif self.task_filter == "待完成":
            rows = [r for r in rows if not r["completed_at"]]
        elif self.task_filter == "已完成":
            rows = [r for r in rows if r["completed_at"]]
        elif self.task_filter != "全部":
            rows = [r for r in rows if r["category"] == self.task_filter]
        visible = {r["id"] for r in rows}
        for task_id, widget in self._task_widgets.items():
            if task_id in visible:
                if not widget["row"].winfo_manager():
                    widget["row"].pack(fill="x", padx=25, pady=5)
            else:
                widget["row"].pack_forget()
        if rows:
            self._empty_tasks.pack_forget()
        else:
            self._empty_tasks.pack(padx=28, pady=60)

    def _task_row(self, box, task):
        row = ctk.CTkFrame(box, fg_color="transparent", height=95)
        row.pack(fill="x", padx=25, pady=5)
        row.pack_propagate(False)
        done = bool(task["completed_at"])
        check = ctk.CTkButton(row, text="✓" if done else "", command=lambda t=task: self.toggle_task(t), width=33, height=33, corner_radius=17,
                      fg_color=self.p["accent"] if done else self.p["card"], hover_color=self.p["soft"],
                      border_width=0 if done else 2, border_color=self.p["accent"], text_color="#FFFFFF", font=(FONT, 18, "bold"))
        check.pack(side="left", padx=(0, 16))
        main = ctk.CTkFrame(row, fg_color="transparent")
        main.pack(side="left", fill="x", expand=True)
        title = label(main, task["title"], 16, "bold", self.p["muted"] if done else self.p["text"])
        title.pack(anchor="w", pady=(12, 3))
        tags = ctk.CTkFrame(main, fg_color="transparent")
        tags.pack(anchor="w")
        for text, bg, fg in ((task["category"], self.p["soft"], self.p["accent"]),
                             (task["difficulty"], "#FFF0D9", "#9B630E"),
                             (task["due_date"], self.p["soft"], self.p["accent"])):
            ctk.CTkLabel(tags, text=text, height=24, corner_radius=7, fg_color=bg, text_color=fg, font=(FONT, 11)).pack(side="left", padx=(0, 6))
        coins = task["earned_coins"] if done else self.store.rewards()[task["difficulty"]]
        ctk.CTkButton(row, text="×", command=lambda t=task: self.delete_task(t), width=28, height=28, fg_color="transparent", hover_color=self.p["soft"], text_color=self.p["muted"], font=(FONT, 21)).pack(side="right", padx=(0, 1))
        ctk.CTkButton(row, text="✎", command=lambda t=task: self.edit_task(t), width=30, height=28, fg_color="transparent", hover_color=self.p["soft"], text_color=self.p["muted"], font=(FONT, 18)).pack(side="right", padx=(0, 6))
        coin_label = label(row, f"+ {coins}  🪙", 14, "bold", self.p["gold"])
        coin_label.pack(side="right", padx=(0, 15))
        return {"row": row, "check": check, "title": title, "coins": coin_label}

    def set_task_filter(self, name):
        self.task_filter = name
        self.show_page("tasks")

    def _task_dialog(self, initial=None):
        fields = {"任务名称": "text", "分类标签": "category", "难度": "difficulty", "计划日期": "text", "备注": "note"}
        values = {"任务名称": initial["title"] if initial else "", "分类标签": initial["category"] if initial else "日常",
                  "难度": initial["difficulty"] if initial else "普通", "计划日期": initial["due_date"] if initial else date.today().isoformat(),
                  "备注": initial["notes"] if initial else ""}
        dialog = FormDialog(self, "编辑任务" if initial else "添加任务", fields, values)
        self.wait_window(dialog)
        if not dialog.result:
            return None
        v = dialog.result
        result = (v["任务名称"], v["分类标签"], v["难度"], v["计划日期"], v["备注"])
        try:
            Store._validate_task(*result[:4])
        except ValueError as exc:
            messagebox.showerror("无法保存", str(exc), parent=self)
            return None
        return result

    def add_task(self):
        values = self._task_dialog()
        if values:
            self.store.add_task(*values)
            self.show_page("tasks")

    def edit_task(self, task):
        task = self.store.task(task["id"])
        if task is None:
            return
        values = self._task_dialog(task)
        if values:
            self.store.edit_task(task["id"], *values)
            self.show_page("tasks")

    def toggle_task(self, task):
        current = self.store.task(task["id"])
        if current is None:
            return
        try:
            self.store.set_completed(task["id"], not bool(current["completed_at"]))
        except ValueError as exc:
            messagebox.showerror("无法撤销", str(exc), parent=self)
            return
        self.show_page("tasks")

    def delete_task(self, task):
        task = self.store.task(task["id"])
        if task is None:
            return
        detail = "\n只从任务清单移除，已获得的金币和日历记录会保留。" if task["completed_at"] else ""
        if messagebox.askyesno("删除任务", f"确定删除“{task['title']}”吗？{detail}", parent=self):
            self.store.delete_task(task["id"])
            self.show_page("tasks")

    def _calendar_page(self, shell):
        head = self._section_head(shell, "成就日历")
        controls = ctk.CTkFrame(head, fg_color="transparent")
        controls.pack(side="right")
        self.button(controls, "‹", lambda: self.move_month(-1), filled=False, width=36, height=37).pack(side="left", padx=(0, 7))
        years = [y for y, _, _ in self.store.yearly_stats()]
        first_year = min(years + [date.today().year, self.cal_year])
        year_values = [str(y) for y in range(first_year, max(date.today().year, self.cal_year) + 2)]
        year_menu = ctk.CTkOptionMenu(controls, values=year_values, width=105, height=37,
                                      fg_color=self.p["card"], button_color=self.p["card"], button_hover_color=self.p["soft"],
                                      text_color=self.p["text"], dropdown_fg_color=self.p["card"], command=self.set_cal_year)
        year_menu.set(str(self.cal_year))
        year_menu.pack(side="left", padx=(0, 7))
        month_menu = ctk.CTkOptionMenu(controls, values=[f"{m} 月" for m in range(1, 13)], width=85, height=37,
                                       fg_color=self.p["card"], button_color=self.p["card"], button_hover_color=self.p["soft"],
                                       text_color=self.p["text"], dropdown_fg_color=self.p["card"], command=self.set_cal_month)
        month_menu.set(f"{self.cal_month} 月")
        month_menu.pack(side="left", padx=(0, 7))
        self.button(controls, "›", lambda: self.move_month(1), filled=False, width=36, height=37).pack(side="left")
        stats = self.store.daily_stats(self.cal_year)
        month_prefix = f"{self.cal_year:04d}-{self.cal_month:02d}"
        month_stats = [v for day, v in stats.items() if day.startswith(month_prefix)]
        month_count = sum(v[0] for v in month_stats)
        month_coins = sum(v[1] for v in month_stats)
        year_coins = sum(v[1] for v in stats.values())
        summary = ctk.CTkFrame(shell, fg_color="transparent")
        summary.pack(fill="x", pady=(0, 18))
        summary.grid_rowconfigure(0, minsize=104)
        for col, (caption, value) in enumerate((("本月完成", f"{month_count} 项"), ("本月获得", f"{month_coins} 🪙"), (f"{self.cal_year} 年累计", f"{year_coins} 🪙"))):
            summary.grid_columnconfigure(col, weight=1)
            card = self.card(summary, height=103)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
            card.grid_propagate(False)
            label(card, caption, 14, color=self.p["muted"]).pack(anchor="w", padx=22, pady=(18, 0))
            label(card, value, 22, "bold", self.p["text"]).pack(anchor="w", padx=22)
        cal = self.card(shell)
        cal.pack(fill="x")
        inside = ctk.CTkFrame(cal, fg_color="transparent")
        inside.pack(fill="x", padx=22, pady=20)
        for col, dayname in enumerate(("周一", "周二", "周三", "周四", "周五", "周六", "周日")):
            inside.grid_columnconfigure(col, weight=1, uniform="day")
            label(inside, dayname, 13, color=self.p["muted"]).grid(row=0, column=col, pady=(0, 12))
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.cal_year, self.cal_month)
        for week_index, week in enumerate(weeks, start=1):
            inside.grid_rowconfigure(week_index, minsize=104)
            for col, number in enumerate(week):
                if not number:
                    continue
                day = f"{self.cal_year:04d}-{self.cal_month:02d}-{number:02d}"
                completed, earned = stats.get(day, (0, 0))
                color = self._heat_color(earned)
                fg = "#FFFFFF" if earned >= 30 else self.p["text"]
                cell = ctk.CTkFrame(inside, height=102, fg_color=color, corner_radius=15,
                                    border_width=2 if day == date.today().isoformat() else 1,
                                    border_color=self.p["accent"] if day == date.today().isoformat() else self.p["border"])
                cell.grid(row=week_index, column=col, sticky="nsew", padx=4, pady=4)
                cell.grid_propagate(False)
                label(cell, str(number), 16, "bold", fg).pack(anchor="w", padx=12, pady=(9, 1))
                if completed:
                    label(cell, f"{completed} 项完成", 11, color=fg).pack(anchor="w", padx=12)
                    label(cell, f"+ {earned} 🪙", 11, color=fg).pack(anchor="w", padx=12)
        label(shell, "颜色越深，表示当天获得的金币越多。按任务实际完成日期统计。", 13, color=self.p["muted"]).pack(anchor="w", pady=(12, 12))
        history = self.card(shell)
        history.pack(fill="x")
        label(history, "历年记录", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(18, 7))
        years = self.store.yearly_stats()
        if years:
            for year, count, coins in years:
                label(history, f"{year} 年     完成 {count} 项任务     获得 {coins} 金币", 14, color=self.p["muted"]).pack(anchor="w", padx=24, pady=(0, 8))
        else:
            label(history, "完成任务后，这里会保存历年成绩。", 14, color=self.p["muted"]).pack(anchor="w", padx=24, pady=(0, 16))

    def _heat_color(self, earned):
        if earned <= 0:
            return self.p["card"]
        if self.theme_name == "深夜":
            palette = ("#324B6D", "#3D628E", "#497AB1", "#3B6AAF", "#27518E")
        else:
            palette = ("#EBF3FF", "#D5E6FF", "#A8CAFF", "#5F96E8", "#2F64C4")
        for limit, color in zip((5, 15, 30, 60, float("inf")), palette):
            if earned <= limit:
                return color
        return palette[-1]

    def move_month(self, amount):
        index = self.cal_year * 12 + self.cal_month - 1 + amount
        self.cal_year, m = divmod(index, 12)
        self.cal_month = m + 1
        self.show_page("calendar")

    def set_cal_year(self, value):
        self.cal_year = int(value)
        self.show_page("calendar")

    def set_cal_month(self, value):
        self.cal_month = int(value.split()[0])
        self.show_page("calendar")

    def _shop_page(self, shell):
        self._section_head(shell, "给自己的小奖励", "＋ 添加奖励", self.add_item)
        items = list(self.store.items())
        if items:
            grid = ctk.CTkFrame(shell, fg_color="transparent")
            grid.pack(fill="x")
            grid.grid_columnconfigure(0, weight=1, uniform="item")
            grid.grid_columnconfigure(1, weight=1, uniform="item")
            for index, item in enumerate(items):
                self._item_card(grid, item, index)
            for row in range((len(items) + 1) // 2):
                grid.grid_rowconfigure(row, minsize=268)
        else:
            empty = self.card(shell)
            empty.pack(fill="x")
            label(empty, "还没有奖励。可以加一杯奶茶、一次 KTV，或任何你想送给自己的东西。", 16, color=self.p["muted"]).pack(padx=30, pady=55)
        history = self.card(shell)
        history.pack(fill="x", pady=(20, 0))
        top = ctk.CTkFrame(history, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(18, 10))
        label(top, "兑换记录", 18, "bold", self.p["text"]).pack(side="left")
        label(top, f"累计兑换 {self.store.redemption_count()} 次", 14, "bold", self.p["accent"]).pack(side="right")
        records = self.store.redemptions(50)
        if not records:
            label(history, "还没有兑换记录。", 14, color=self.p["muted"]).pack(anchor="w", padx=24, pady=(0, 22))
        for index, record in enumerate(records):
            line = ctk.CTkFrame(history, fg_color="transparent")
            line.pack(fill="x", padx=24, pady=6)
            label(line, record["item_name"], 14, "bold", self.p["text"]).pack(side="left")
            label(line, f"− {record['cost']} 🪙", 13, "bold", self.p["gold"]).pack(side="right")
            label(line, record["redeemed_at"].replace("T", " ")[:16], 12, color=self.p["muted"]).pack(side="right", padx=(0, 20))
            if index < len(records)-1:
                ctk.CTkFrame(history, height=1, fg_color=self.p["border"]).pack(fill="x", padx=24)
        if records:
            ctk.CTkFrame(history, height=10, fg_color="transparent").pack()

    def _item_icon(self, name):
        if any(word in name for word in ("奶茶", "咖啡", "饮料")):
            return "🧋"
        if any(word in name.lower() for word in ("ktv", "唱歌", "音乐")):
            return "🎤"
        if any(word in name for word in ("电影", "剧")):
            return "🎬"
        if any(word in name for word in ("游戏", "电玩")):
            return "🎮"
        if any(word in name for word in ("旅行", "出游")):
            return "🧳"
        return "🎁"

    def _item_card(self, grid, item, index):
        row, col = divmod(index, 2)
        card = self.card(grid, height=268)
        card.grid(row=row, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=(0, 16))
        card.grid_propagate(False)
        label(card, self._item_icon(item["name"]), 30).pack(anchor="w", padx=24, pady=(16, 0))
        label(card, item["name"], 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(1, 0))
        label(card, item["description"] or "给自己一点开心的时间", 13, color=self.p["muted"]).pack(anchor="w", padx=24)
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.pack(fill="x", padx=24, pady=(10, 0))
        label(line, f"{item['cost']} 🪙", 16, "bold", self.p["gold"]).pack(side="left")
        self.button(line, "兑换", lambda i=item: self.redeem_item(i), width=90, height=36).pack(side="right")
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(9, 0))
        label(bottom, f"累计兑换 {self.store.redemption_count(item['name'], item['id'])} 次", 11, color=self.p["muted"]).pack(side="right")
        ctk.CTkButton(bottom, text="✎", command=lambda i=item: self.edit_item(i), width=25, height=24,
                      fg_color="transparent", hover_color=self.p["soft"], text_color=self.p["muted"], font=(FONT, 16)).pack(side="left")
        ctk.CTkButton(bottom, text="×", command=lambda i=item: self.remove_item(i), width=25, height=24,
                      fg_color="transparent", hover_color=self.p["soft"], text_color=self.p["muted"], font=(FONT, 19)).pack(side="left")

    def _item_dialog(self, initial=None):
        fields = {"奖励名称": "text", "金币价格": "text", "说明": "text"}
        values = {"奖励名称": initial["name"] if initial else "", "金币价格": str(initial["cost"]) if initial else "", "说明": initial["description"] if initial else ""}
        dialog = FormDialog(self, "编辑奖励" if initial else "添加奖励", fields, values)
        self.wait_window(dialog)
        if not dialog.result:
            return None
        v = dialog.result
        try:
            cost = int(v["金币价格"])
            if not v["奖励名称"] or cost <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("无法保存", "请输入奖励名称和大于 0 的整数金币价格。", parent=self)
            return None
        return (v["奖励名称"], cost, v["说明"])

    def add_item(self):
        values = self._item_dialog()
        if values:
            self.store.add_item(*values)
            self.show_page("shop")

    def edit_item(self, item):
        values = self._item_dialog(item)
        if values:
            self.store.edit_item(item["id"], *values)
            self.show_page("shop")

    def remove_item(self, item):
        if messagebox.askyesno("移除奖励", f"确定移除“{item['name']}”吗？已有兑换记录会保留。", parent=self):
            self.store.remove_item(item["id"])
            self.show_page("shop")

    def redeem_item(self, item):
        if not messagebox.askyesno("确认兑换", f"花费 {item['cost']} 金币兑换“{item['name']}”？", parent=self):
            return
        try:
            self.store.redeem(item["id"])
        except ValueError as exc:
            messagebox.showerror("兑换失败", str(exc), parent=self)
        else:
            self.show_page("shop")
            messagebox.showinfo("兑换成功", "已记入兑换记录和累计次数。", parent=self)

    def _settings_page(self, shell):
        self._section_head(shell, "个性设置")
        grid = ctk.CTkFrame(shell, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="setting")
        grid.grid_columnconfigure(1, weight=1, uniform="setting")
        grid.grid_rowconfigure(0, minsize=292)
        grid.grid_rowconfigure(1, minsize=205)
        themes = self.card(grid, height=278)
        themes.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 16))
        themes.grid_propagate(False)
        label(themes, "选择主题", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(20, 14))
        swatches = ctk.CTkFrame(themes, fg_color="transparent")
        swatches.pack(anchor="w", padx=24)
        for name, palette in PALETTES.items():
            ctk.CTkButton(swatches, text="✓" if name == self.theme_name else "", command=lambda n=name: self.change_theme(n),
                          width=48, height=48, corner_radius=24, fg_color=palette["navy"] if name == "深夜" else palette["accent"], hover_color=palette["navy"],
                          text_color="#FFFFFF", border_width=2 if name == self.theme_name else 0,
                          border_color=self.p["text"], font=(FONT, 18, "bold")).pack(side="left", padx=(0, 11))
        label(themes, "海蓝 · 玫瑰 · 森林 · 深夜", 13, color=self.p["muted"]).pack(anchor="w", padx=24, pady=(10, 9))
        bar = ctk.CTkFrame(themes, fg_color="transparent")
        bar.pack(anchor="w", padx=24)
        self.button(bar, "自选背景色", self.choose_background, filled=False, width=118, height=35).pack(side="left", padx=(0, 8))
        self.button(bar, "恢复背景", self.clear_background, filled=False, width=110, height=35).pack(side="left")
        rewards = self.card(grid, height=278)
        rewards.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 16))
        rewards.grid_propagate(False)
        label(rewards, "完成任务获得金币", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(20, 11))
        self.reward_entries = {}
        for name in DIFFICULTIES:
            line = ctk.CTkFrame(rewards, fg_color="transparent")
            line.pack(fill="x", padx=24, pady=3)
            label(line, name, 14, color=self.p["text"]).pack(side="left")
            label(line, "🪙", 16, color=self.p["gold"]).pack(side="right")
            entry = ctk.CTkEntry(line, width=75, height=32, fg_color=self.p["bg"], border_color=self.p["border"], text_color=self.p["text"])
            entry.insert(0, str(self.store.rewards()[name]))
            entry.pack(side="right", padx=(0, 9))
            self.reward_entries[name] = entry
        footer = ctk.CTkFrame(rewards, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(8, 0))
        label(footer, "已完成记录的金币不会改变。", 12, color=self.p["muted"]).pack(side="left")
        self.button(footer, "保存", self.save_rewards, width=74, height=33).pack(side="right")
        offline = self.card(grid, height=175)
        offline.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        offline.grid_propagate(False)
        label(offline, "离线使用", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(20, 9))
        label(offline, "这份桌面版已包含完整页面，断网也能使用。\n任务、金币和兑换记录都保存在这台电脑上。", 13, color=self.p["muted"], justify="left").pack(anchor="w", padx=24)
        backup = self.card(grid, height=175)
        backup.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        backup.grid_propagate(False)
        label(backup, "数据备份", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(20, 7))
        label(backup, "换设备或清除程序数据前，请导出备份文件。", 13, color=self.p["muted"]).pack(anchor="w", padx=24)
        buttons = ctk.CTkFrame(backup, fg_color="transparent")
        buttons.pack(anchor="w", padx=24, pady=(16, 0))
        self.button(buttons, "导出备份", self.export_backup, filled=False, width=110, height=36).pack(side="left", padx=(0, 9))
        self.button(buttons, "导入备份", self.import_backup, filled=False, width=110, height=36).pack(side="left")
        rules = self.card(shell)
        rules.pack(fill="x", pady=(18, 0))
        label(rules, "任务与金币规则", 18, "bold", self.p["text"]).pack(anchor="w", padx=24, pady=(18, 7))
        label(rules, "已完成任务会在第二天自动从清单移除；金币和日历记录保留在点击完成的日期。", 13, color=self.p["muted"]).pack(anchor="w", padx=24)
        debt_row = ctk.CTkFrame(rules, fg_color="transparent")
        debt_row.pack(fill="x", padx=24, pady=(14, 18))
        label(debt_row, "允许欠金币额度", 14, color=self.p["text"]).pack(side="left", padx=(0, 12))
        self.debt_entry = ctk.CTkEntry(debt_row, width=90, height=35, fg_color=self.p["bg"], border_color=self.p["border"], text_color=self.p["text"])
        self.debt_entry.insert(0, str(self.store.debt_limit()))
        self.debt_entry.pack(side="left")
        label(debt_row, "设为 100 时最低余额为 −100；设为 0 则不允许欠币。", 12, color=self.p["muted"]).pack(side="left", padx=12)
        self.button(debt_row, "保存额度", self.save_debt_limit, width=100, height=35).pack(side="right")
        reset = self.card(shell)
        reset.pack(fill="x", pady=(18, 0))
        reset_row = ctk.CTkFrame(reset, fg_color="transparent")
        reset_row.pack(fill="x", padx=24, pady=18)
        text = ctk.CTkFrame(reset_row, fg_color="transparent")
        text.pack(side="left")
        label(text, "恢复出厂设置", 18, "bold", self.p["text"]).pack(anchor="w")
        label(text, "清空任务、金币、日历和兑换记录、商城，并恢复默认设置。", 13, color=self.p["muted"]).pack(anchor="w")
        self.reset_button = ctk.CTkButton(reset_row, text="恢复出厂设置", command=self.factory_reset,
                                          fg_color="#B33C47", hover_color="#912B35", text_color="#FFFFFF",
                                          height=40, corner_radius=13, font=(FONT, 14, "bold"))
        self.reset_button.pack(side="right")
        label(shell, f"本机数据位置：{self.store.path}", 12, color=self.p["muted"]).pack(anchor="w", pady=(15, 0))

    def save_debt_limit(self):
        try:
            limit = int(self.debt_entry.get())
            self.store.set_debt_limit(limit)
        except ValueError as exc:
            messagebox.showerror("无法保存", str(exc) if self.debt_entry.get().isdigit() else "请输入 0 到 100000 的整数。", parent=self)
            return
        messagebox.showinfo("已保存", f"最低金币余额已设为 −{limit}。", parent=self)

    def factory_reset(self):
        confirmed = messagebox.askyesno(
            "警告：恢复出厂设置",
            "这会清空全部任务（包括已移除的完成记录）、金币、日历统计、商城和兑换记录，并恢复默认主题与金币设置。\n\n此操作无法撤销。建议先导出备份。\n\n确定恢复出厂设置吗？",
            icon="warning", default="no", parent=self,
        )
        if not confirmed:
            return
        self.store.factory_reset()
        self.theme_name = "海蓝"
        self.task_filter = "全部"
        self.cal_year, self.cal_month = date.today().year, date.today().month
        self._layout_palette = None
        self._set_palette()
        self.show_page("tasks")
        messagebox.showinfo("已恢复出厂设置", "当前程序的数据已清空，设置已恢复默认值。", parent=self)

    def change_theme(self, name):
        self.theme_name = name
        self.store.set_setting("theme", name)
        self.store.set_setting("background", "")
        self._set_palette()
        self.show_page("settings")

    def choose_background(self):
        selected = colorchooser.askcolor(title="选择背景颜色", initialcolor=self.p["bg"])[1]
        if selected:
            self.store.set_setting("background", selected)
            self._set_palette()
            self.show_page("settings")

    def clear_background(self):
        self.store.set_setting("background", "")
        self._set_palette()
        self.show_page("settings")

    def save_rewards(self):
        values = {}
        for name, entry in self.reward_entries.items():
            try:
                amount = int(entry.get())
                if not 0 <= amount <= 100000:
                    raise ValueError
            except ValueError:
                messagebox.showerror("无法保存", f"{name}的金币数请输入 0 到 100000 的整数。", parent=self)
                return
            values[name] = amount
        for name, amount in values.items():
            self.store.set_setting(f"reward_{name}", str(amount))
        messagebox.showinfo("已保存", "新奖励将用于以后完成的任务。", parent=self)

    def export_backup(self):
        target = filedialog.asksaveasfilename(parent=self, title="导出数据备份", defaultextension=".db",
                                              filetypes=[("数据库备份", "*.db")],
                                              initialfile=f"今日清单备份-{date.today().isoformat()}.db")
        if not target:
            return
        try:
            with sqlite3.connect(target) as destination:
                self.store.db.backup(destination)
            messagebox.showinfo("备份完成", f"已导出到：\n{target}", parent=self)
        except (OSError, sqlite3.Error) as exc:
            messagebox.showerror("备份失败", str(exc), parent=self)

    def import_backup(self):
        source_path = filedialog.askopenfilename(parent=self, title="导入数据备份", filetypes=[("数据库备份", "*.db"), ("所有文件", "*.*")])
        if not source_path:
            return
        if Path(source_path).resolve() == self.store.path.resolve():
            messagebox.showerror("无法导入", "选择的是当前正在使用的数据文件。", parent=self)
            return
        try:
            with sqlite3.connect(source_path) as source:
                tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"tasks", "shop", "redemptions", "settings"}.issubset(tables):
                    raise ValueError("这不是今日清单的有效备份文件。")
                if not messagebox.askyesno("确认导入", "导入会替换当前任务、金币和商城数据。程序会先自动备份现有数据。继续吗？", parent=self):
                    return
                safety = self.store.path.parent / f"导入前自动备份-{datetime.now():%Y%m%d-%H%M%S}.db"
                with sqlite3.connect(safety) as destination:
                    self.store.db.backup(destination)
                source.backup(self.store.db)
                self.store._init_schema()
            self.show_page("settings")
            messagebox.showinfo("导入完成", f"已导入备份。原数据自动备份在：\n{safety}", parent=self)
        except (OSError, sqlite3.Error, ValueError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
