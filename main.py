"""
main.py — главное окно PDF Переводчика с вкладками
"""

import sys
import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
import requests
import sv_ttk

from pdf_tab import PDFTab


# ─────────────────────────────────────────────────────────────────────────────
# Константы
LANGUAGES_SOURCE = {
    "Авто": "auto",
    "Русский": "ru",
    "Английский": "en",
    "Немецкий": "de",
    "Французский": "fr",
    "Испанский": "es",
    "Итальянский": "it",
    "Китайский": "zh",
    "Японский": "ja",
}

LANGUAGES_TARGET = {
    "Русский": "ru",
    "Английский": "en",
    "Немецкий": "de",
    "Французский": "fr",
    "Испанский": "es",
    "Итальянский": "it",
    "Китайский": "zh",
    "Японский": "ja",
}

TRANSLATORS = {
    "google": "Google Translate",
    "yandex": "Яндекс.Переводчик",
    "deepl": "DeepL",
}

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

DEFAULT_SETTINGS = {
    "translator": "google",
    "source_lang": "auto",
    "target_lang": "ru",
    "font_size": 13,
    "theme": "auto",
    "api_keys": {
        "yandex_api_key": "",
        "yandex_folder_id": "",
        "deepl_api_key": "",
        "deepseek_api_key": "",
    },
    "open_tabs": [],  # список словарей {path, page, zoom}
}

# Изумрудная палитра
EMERALD = {
    "light": {
        "bg": "#f0faf5",
        "toolbar": "#e0f0e8",
        "btn": "#1a6e4a",
        "btn_fg": "#ffffff",
        "canvas_bg": "#d4e6dd",
        "text_bg": "#ffffff",
        "text_fg": "#1a2a24",
        "accent": "#2ecc71",
        "nav_bg": "#e0f0e8",
        "border": "#1a6e4a",
        "status": "#555555",
    },
    "dark": {
        "bg": "#0a120f",
        "toolbar": "#0d2a1f",
        "btn": "#1a6e4a",
        "btn_fg": "#ffffff",
        "canvas_bg": "#0d1f18",
        "text_bg": "#1a1f1c",
        "text_fg": "#e0f2e9",
        "accent": "#2ecc71",
        "nav_bg": "#0d2a1f",
        "border": "#2ecc71",
        "status": "#88998f",
    }
}


class PDFTranslatorApp:
    DEEPSEEK_URL = DEEPSEEK_URL
    DEEPSEEK_MODEL = DEEPSEEK_MODEL

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDF Переводчик")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 700)
        # Отключаем Tab-навигацию по умолчанию
        self.root.option_add('*takeFocus', 0)

        # Определяем тему
        current_hour = datetime.now().hour
        self.current_theme = "dark" if current_hour >= 20 or current_hour < 6 else "light"

        if self.current_theme == "dark":
            sv_ttk.set_theme("dark")
        else:
            sv_ttk.set_theme("light")

        # Настройки
        self._load_settings()
        self.colors = EMERALD[self.current_theme]

        # Флаги главного окна
        self._scrolling = False
        self.sync_scroll_var = tk.BooleanVar(value=True)
        self.trans_font_size = self.settings.get("font_size", 13)
        self.popup_win = None
        self._result_win_text = None

        # UI
        self._build_menu()
        self._build_toolbar()
        self._build_notebook()
        self._build_status_bar()

        # Восстанавливаем вкладки из настроек
        self._restore_tabs()

        # Горячие клавиши
        self._bind_hotkeys()

        # При закрытии сохраняем состояние
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ════════════════════════════════════════════════════════════════════════
    # Настройки
    # ════════════════════════════════════════════════════════════════════════

    def _get_settings_path(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "settings.json")

    def _load_settings(self):
        path = self._get_settings_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                settings = json.loads(json.dumps(DEFAULT_SETTINGS))
                settings.update(loaded)
                api = DEFAULT_SETTINGS["api_keys"].copy()
                api.update(loaded.get("api_keys", {}))
                settings["api_keys"] = api
                self.settings = settings
                return
            except Exception as e:
                print(f"Ошибка чтения настроек: {e}")
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))

    def _save_settings(self):
        # Сохраняем состояние вкладок
        self.settings["open_tabs"] = self._collect_tabs_state()
        path = self._get_settings_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")

    def _collect_tabs_state(self):
        """Собирает состояние всех вкладок"""
        state = []
        for tab_id in self.notebook.tabs():
            widget = self.notebook.nametowidget(tab_id)
            # Получаем PDFTab через атрибут
            tab = getattr(widget, 'pdf_tab', None)
            if tab and tab.pdf_path:
                state.append(tab.get_state())
        return state

    # ════════════════════════════════════════════════════════════════════════
    # UI
    # ════════════════════════════════════════════════════════════════════════

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        # Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📂 Открыть PDF", command=self.open_pdf_dialog)
        file_menu.add_command(label="📑 Новая вкладка", command=self.open_pdf_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Закрыть вкладку", command=self.close_current_tab)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)

        # Перевод
        trans_menu = tk.Menu(menubar, tearoff=0)

        self.translator_var = tk.StringVar(value=self.settings["translator"])
        for key, name in TRANSLATORS.items():
            trans_menu.add_radiobutton(
                label=name, variable=self.translator_var, value=key,
                command=lambda k=key: self._on_translator_change(k))

        trans_menu.add_separator()
        trans_menu.add_command(label="🌐 Языки перевода...", command=self._open_languages_window)
        trans_menu.add_separator()
        trans_menu.add_command(label="🔑 Настройки API...", command=self._open_api_settings)
        menubar.add_cascade(label="Перевод", menu=trans_menu)

        # Справка
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="📂 Открыть PDF", command=self.open_pdf_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📑 Новая вкладка", command=self.open_pdf_dialog).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)

        ttk.Button(toolbar, text="🔤 Перевести выделенное", command=self.translate_selection_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🤖 Объяснить ИИ", command=self.explain_ai_current).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)

        ttk.Label(toolbar, text="Текст:").pack(side=tk.LEFT, padx=(5, 2))
        ttk.Button(toolbar, text="A−", command=self.zoom_text_out, width=3).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="A+", command=self.zoom_text_in, width=3).pack(side=tk.LEFT)

        ttk.Checkbutton(toolbar, text="Синхр. прокрутка", variable=self.sync_scroll_var).pack(side=tk.RIGHT, padx=10)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_status_bar(self):
        nav = ttk.Frame(self.root)
        nav.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        self.status_bar = ttk.Label(nav, text="Откройте PDF-файл")
        self.status_bar.pack(side=tk.LEFT, padx=10)

    def _bind_hotkeys(self):
        self.root.bind("<Control-o>", lambda e: self.open_pdf_dialog())
        self.root.bind("<Control-t>", lambda e: self.open_pdf_dialog())
        self.root.bind("<Control-w>", lambda e: self.close_current_tab())
        self.root.bind("<Control-plus>", lambda e: self.zoom_text_in())
        self.root.bind("<Control-minus>", lambda e: self.zoom_text_out())
        # Стрелки и PageUp/Down — обрабатываются в активной вкладке
        self.root.bind("<Left>", lambda e: self._send_to_tab("prev_page"))
        self.root.bind("<Right>", lambda e: self._send_to_tab("next_page"))
        self.root.bind("<Prior>", lambda e: self._send_to_tab("prev_page"))
        self.root.bind("<Next>", lambda e: self._send_to_tab("next_page"))
        # Переключение вкладок
        self.root.bind("<Control-Tab>", lambda e: self.next_tab())
        self.root.bind("<Control-Shift-Tab>", lambda e: self.prev_tab())
        self.root.bind("<Control-Prior>", lambda e: self.prev_tab())     # Ctrl+PageUp
        self.root.bind("<Control-Next>", lambda e: self.next_tab())      # Ctrl+PageDown
        self.root.bind("<Control-w>", lambda e: self.close_current_tab())  # Ctrl+W

    def _send_to_tab(self, method_name):
        """Вызывает метод у активной вкладки"""
        tab = self.get_current_tab()
        if tab:
            getattr(tab, method_name)()

    # ════════════════════════════════════════════════════════════════════════
    # Вкладки
    # ════════════════════════════════════════════════════════════════════════

    def get_current_tab(self):
        """Возвращает активную вкладку (PDFTab) или None"""
        tab_id = self.notebook.select()
        if not tab_id:
            return None
        widget = self.notebook.nametowidget(tab_id)
        return getattr(widget, 'pdf_tab', None)

    def _add_tab(self, pdf_path=None, page=0, zoom=1.5, title=None):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title or "Новая вкладка")

        tab = PDFTab(frame, self, pdf_path)
        frame.pdf_tab = tab   # ← ДОБАВЬТЕ ЭТУ СТРОКУ — сохраняем ссылку

        if pdf_path:
            tab._load_pdf(pdf_path, page, zoom)
            self._update_tab_title(tab)

        self.notebook.select(frame)
        return tab

    def _update_tab_title(self, tab):
        """Обновляет заголовок вкладки по имени файла"""
        try:
            idx = self.notebook.index(tab.parent)
            if tab.pdf_path:
                name = os.path.basename(tab.pdf_path)
                if len(name) > 30:
                    name = name[:27] + "..."
                self.notebook.tab(idx, text=name)
            else:
                self.notebook.tab(idx, text="Новая вкладка")
        except Exception as e:
            print(f"Ошибка обновления заголовка: {e}")

    def open_pdf_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("PDF файлы", "*.pdf")])
        if not path:
            return
        
        # Если есть пустая вкладка (без pdf_path) — используем её
        for tab_id in self.notebook.tabs():
            widget = self.notebook.nametowidget(tab_id)
            tab = getattr(widget, 'pdf_tab', None)
            if tab and not tab.pdf_path:
                tab._load_pdf(path)
                self._update_tab_title(tab)
                self.notebook.select(widget)
                self._save_settings()
                return
        
        # Иначе — новая вкладка
        self._add_tab(path)
        self._save_settings()

    def close_current_tab(self):
        """Закрывает активную вкладку"""
        tab_id = self.notebook.select()
        if not tab_id:
            return
        self.notebook.forget(tab_id)
        self._save_settings()

    def _restore_tabs(self):
        tabs_state = self.settings.get("open_tabs", [])
        print(f"=== Восстанавливаю {len(tabs_state)} вкладок ===")  # ← ДОБАВЬТЕ
        if not tabs_state:
            self._add_tab()
            return
        for state in tabs_state:
            path = state.get("path", "")
            page = state.get("page", 0)
            zoom = state.get("zoom", 1.5)
            print(f"=== Вкладка: {path}, существует: {os.path.exists(path)} ===")  # ← ДОБАВЬТЕ
            if path and os.path.exists(path):
                self._add_tab(path, page, zoom)

    def _on_close(self):
        """Сохранение при закрытии"""
        self._save_settings()
        self.root.destroy()

    # ════════════════════════════════════════════════════════════════════════
    # Кнопки главного окна → активная вкладка
    # ════════════════════════════════════════════════════════════════════════

    def translate_selection_current(self):
        tab = self.get_current_tab()
        if tab:
            tab.translate_selection()

    def explain_ai_current(self):
        tab = self.get_current_tab()
        if tab:
            tab.explain_ai()

    def zoom_text_in(self):
        if self.trans_font_size < 30:
            self.trans_font_size += 1
            self.settings["font_size"] = self.trans_font_size
            self._apply_font_to_all_tabs()
            self._save_settings()

    def zoom_text_out(self):
        if self.trans_font_size > 8:
            self.trans_font_size -= 1
            self.settings["font_size"] = self.trans_font_size
            self._apply_font_to_all_tabs()
            self._save_settings()

    def _apply_font_to_all_tabs(self):
        for tab_id in self.notebook.tabs():
            widget = self.notebook.nametowidget(tab_id)
            tab = getattr(widget, 'pdf_tab', None)
            if tab:
                tab.update_font_size(self.trans_font_size)

    # ════════════════════════════════════════════════════════════════════════
    # Меню "Перевод"
    # ════════════════════════════════════════════════════════════════════════

    def _on_translator_change(self, key):
        self.settings["translator"] = key

        if key == "yandex":
            api = self.settings["api_keys"]
            if not api.get("yandex_api_key") or not api.get("yandex_folder_id"):
                messagebox.showinfo("Нужен API-ключ",
                                    "Для Яндекс.Переводчика нужен API-ключ и Folder ID.\n"
                                    "Открываю окно настроек.")
                self._open_api_settings()
        elif key == "deepl":
            if not self.settings["api_keys"].get("deepl_api_key"):
                messagebox.showinfo("Нужен API-ключ",
                                    "Для DeepL нужен API-ключ.\nОткрываю настройки.")
                self._open_api_settings()

        self._save_settings()
        self._set_status(f"Переводчик: {TRANSLATORS.get(key, key)}")

        # Обновляем все вкладки
        tab = self.get_current_tab()
        if tab and tab.pdf_doc:
            tab._clear_translation()
            tab.translate_current_page()

    def _open_languages_window(self):
        win = tk.Toplevel(self.root)
        win.title("Языки перевода")
        win.geometry("400x300")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Определяем текущие имена
        src_code = self.settings["source_lang"]
        tgt_code = self.settings["target_lang"]
        src_name = next((k for k, v in LANGUAGES_SOURCE.items() if v == src_code), "Авто")
        tgt_name = next((k for k, v in LANGUAGES_TARGET.items() if v == tgt_code), "Русский")

        ttk.Label(frame, text="С языка:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        source_combo = ttk.Combobox(frame, values=list(LANGUAGES_SOURCE.keys()),
                                     state="readonly", width=30)
        source_combo.set(src_name)
        source_combo.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(frame, text="На язык:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        target_combo = ttk.Combobox(frame, values=list(LANGUAGES_TARGET.keys()),
                                     state="readonly", width=30)
        target_combo.set(tgt_name)
        target_combo.pack(fill=tk.X, pady=(0, 20))

        def save():
            src = source_combo.get()
            tgt = target_combo.get()
            self.settings["source_lang"] = LANGUAGES_SOURCE[src]
            self.settings["target_lang"] = LANGUAGES_TARGET[tgt]
            self._save_settings()
            win.destroy()
            self._set_status(f"Перевод: {src} → {tgt}")

            # Обновляем текущую вкладку
            tab = self.get_current_tab()
            if tab and tab.pdf_doc:
                tab._clear_translation()
                tab.translate_current_page()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Сохранить", command=save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=win.destroy).pack(side=tk.RIGHT)

    def _open_api_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Настройки API")
        win.geometry("550x450")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        api = self.settings["api_keys"]

        # Яндекс
        ttk.Label(frame, text="🔑 Яндекс.Переводчик", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(frame, text="API-ключ:").pack(anchor=tk.W)
        yandex_key_var = tk.StringVar(value=api.get("yandex_api_key", ""))
        ttk.Entry(frame, textvariable=yandex_key_var, width=60).pack(fill=tk.X, pady=(0, 5))

        ttk.Label(frame, text="Folder ID:").pack(anchor=tk.W)
        yandex_folder_var = tk.StringVar(value=api.get("yandex_folder_id", ""))
        ttk.Entry(frame, textvariable=yandex_folder_var, width=60).pack(fill=tk.X, pady=(0, 15))

        # DeepL
        ttk.Label(frame, text="🔑 DeepL", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(frame, text="API-ключ:").pack(anchor=tk.W)
        deepl_key_var = tk.StringVar(value=api.get("deepl_api_key", ""))
        ttk.Entry(frame, textvariable=deepl_key_var, width=60).pack(fill=tk.X, pady=(0, 15))

        # DeepSeek
        ttk.Label(frame, text="🔑 DeepSeek (для ИИ-объяснений)", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(frame, text="API-ключ:").pack(anchor=tk.W)
        deepseek_key_var = tk.StringVar(value=api.get("deepseek_api_key", ""))
        ttk.Entry(frame, textvariable=deepseek_key_var, width=60, show="*").pack(fill=tk.X, pady=(0, 15))

        def save():
            self.settings["api_keys"]["yandex_api_key"] = yandex_key_var.get().strip()
            self.settings["api_keys"]["yandex_folder_id"] = yandex_folder_var.get().strip()
            self.settings["api_keys"]["deepl_api_key"] = deepl_key_var.get().strip()
            self.settings["api_keys"]["deepseek_api_key"] = deepseek_key_var.get().strip()
            self._save_settings()
            win.destroy()
            self._set_status("Настройки API сохранены")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Сохранить", command=save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=win.destroy).pack(side=tk.RIGHT)

    def _show_about(self):
        messagebox.showinfo("О программе",
                            "PDF Переводчик\n\n"
                            "Версия 5.0 (вкладки)\n\n"
                            "Переводчики: Google, Яндекс, DeepL\n"
                            "ИИ-объяснения: DeepSeek")

    # ════════════════════════════════════════════════════════════════════════
    # Окно результата (перевод / объяснение)
    # ════════════════════════════════════════════════════════════════════════

    def _open_result_window(self, title, original_text, translated_text=""):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("1000x600")
        win.configure(bg=self.colors["bg"])

        main_frame = tk.Frame(win, bg=self.colors["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Левая — оригинал
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        ttk.Label(left_frame, text="📖 ОРИГИНАЛ", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, padx=5, pady=5)

        left_text = tk.Text(left_frame, wrap=tk.WORD, bg="#f5f5f5", fg="#111111",
                            font=("Segoe UI", 11), padx=10, pady=10, relief=tk.FLAT)
        left_text.pack(fill=tk.BOTH, expand=True)
        left_text.insert(1.0, original_text)
        left_text.config(state=tk.DISABLED)

        ttk.Button(left_frame, text="📋 Копировать оригинал",
                   command=lambda: self._copy_to_clipboard(original_text)).pack(pady=5)

        # Правая — перевод
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        ttk.Label(right_frame, text="🌐 ПЕРЕВОД", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, padx=5, pady=5)

        self._result_win_text = tk.Text(right_frame, wrap=tk.WORD, bg="#fffff0", fg="#111111",
                                         font=("Segoe UI", 11), padx=10, pady=10, relief=tk.FLAT)
        self._result_win_text.pack(fill=tk.BOTH, expand=True)
        self._result_win_text.insert(1.0, translated_text)
        self._result_win_text.config(state=tk.NORMAL)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="📋 Копировать перевод",
                   command=lambda: self._copy_to_clipboard(self._result_win_text.get(1.0, tk.END).strip())).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 Копировать всё",
                   command=lambda: self._copy_to_clipboard(
                       f"ОРИГИНАЛ:\n{original_text}\n\nПЕРЕВОД:\n{self._result_win_text.get(1.0, tk.END).strip()}")).pack(side=tk.LEFT, padx=5)

        win.grab_set()

    # ════════════════════════════════════════════════════════════════════════
    # Вспомогательные
    # ════════════════════════════════════════════════════════════════════════

    def next_tab(self):
        """Переход на следующую вкладку (по кругу)"""
        tabs = self.notebook.tabs()
        if len(tabs) < 2:
            return
        current = self.notebook.index(self.notebook.select())
        next_idx = (current + 1) % len(tabs)
        self.notebook.select(tabs[next_idx])

    def prev_tab(self):
        """Переход на предыдущую вкладку (по кругу)"""
        tabs = self.notebook.tabs()
        if len(tabs) < 2:
            return
        current = self.notebook.index(self.notebook.select())
        prev_idx = (current - 1) % len(tabs)
        self.notebook.select(tabs[prev_idx])

    # ════════════════════════════════════════════════════════════════════════
    # Вспомогательные
    # ════════════════════════════════════════════════════════════════════════

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_bar.config(text=msg))

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status(f"Скопировано: {text[:50]}...")


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.3)
    except Exception:
        pass
    app = PDFTranslatorApp(root)
    root.mainloop()