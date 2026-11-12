"""
pdf_tab.py — класс вкладки PDF (одна книга)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import fitz
from PIL import Image, ImageTk
from deep_translator import GoogleTranslator
import re
import threading
import io
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Константы переводчиков (для UI)
TRANSLATORS_UI = {
    "google": "Google Translate",
    "yandex": "Яндекс.Переводчик",
    "deepl": "DeepL",
}


class PDFTab:
    """Одна вкладка с PDF и переводом"""

    def __init__(self, parent, app, pdf_path=None):
        """
        parent — tk.Frame, куда добавляется вкладка (обычно notebook)
        app — ссылка на главное окно (PDFTranslatorApp)
        pdf_path — путь к PDF (опционально)
        """
        self.app = app
        self.parent = parent

        # PDF
        self.pdf_doc = None
        self.pdf_path = pdf_path or ""
        self.current_page = 0
        self.zoom = 1.5
        self.rotation = 0  # глобальный угол поворота для всех страниц
        self.page_image = None
        self.page_photo = None
        self.image_item = None

        # Выделение
        self.sel_start = None
        self.sel_rect_id = None
        self.selection_rect = None
        self.highlight_rect_id = None

        # Прокрутка
        self._scrolling = False

        # Перевод
        self.is_translating = False
        self.translate_timer = None

        # Обрезка
        self.crop_top = tk.IntVar(value=0)
        self.crop_bottom = tk.IntVar(value=0)
        self.crop_left = tk.IntVar(value=0)
        self.crop_right = tk.IntVar(value=0)
        self._crop_top_line_id = None
        self._crop_bottom_line_id = None
        self._crop_left_line_id = None
        self._crop_right_line_id = None
        # Для перетаскивания
        self._dragging_line = None  # "top", "bottom", "left", "right" или None

        # Плавающее окно
        self.popup_win = None

        # Флаг: контент построен
        self._build_ui()

        # Если PDF передан сразу — открываем
        if self.pdf_path:
            self._load_pdf(self.pdf_path)

    def set_status(self, msg):
        """Устанавливает статус этой вкладки"""
        try:
            self.status_label.config(text=msg)
        except:
            pass

    # ════════════════════════════════════════════════════════════════════════
    # Построение интерфейса вкладки
    # ════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        """Строит UI внутри родительского фрейма"""
        colors = self.app.colors

        # Основная область (PanedWindow)
        self.paned = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # Левая панель (PDF)
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=1)

        self.pdf_canvas = tk.Canvas(left_frame, bg=colors["canvas_bg"],
                                     highlightthickness=0, cursor="crosshair")
        self.pdf_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        pdf_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._on_pdf_scroll_y)
        pdf_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pdf_canvas.configure(yscrollcommand=pdf_scroll.set)

        # Правая панель (перевод)
        right_frame = ttk.Frame(self.paned)
        self.paned.add(right_frame, weight=1)

        text_frame = ttk.Frame(right_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.trans_text = tk.Text(text_frame, wrap=tk.WORD,
                                   bg=colors["text_bg"], fg=colors["text_fg"],
                                   font=("Segoe UI", self.app.settings.get("font_size", 13)),
                                   padx=20, pady=20,
                                   insertbackground=colors["text_fg"],
                                   selectbackground=colors["accent"],
                                   relief=tk.FLAT, state=tk.DISABLED)
        self.trans_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        text_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._on_trans_scroll_y)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.trans_text.configure(yscrollcommand=text_scroll.set)

        # Нижняя навигация вкладки
        nav = ttk.Frame(self.parent)
        nav.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(2, 5))

        ttk.Button(nav, text="◀", command=self.prev_page, width=3).pack(side=tk.LEFT, padx=2)
        self.page_label = ttk.Label(nav, text="— / —", width=15)
        self.page_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(nav, text="▶", command=self.next_page, width=3).pack(side=tk.LEFT, padx=2)

        ttk.Label(nav, text="Стр:").pack(side=tk.LEFT, padx=(15, 2))
        self.page_entry = ttk.Entry(nav, width=5)
        self.page_entry.pack(side=tk.LEFT)
        self.page_entry.bind("<Return>", self.go_to_page)
        ttk.Button(nav, text="→", command=self.go_to_page, width=3).pack(side=tk.LEFT, padx=2)

        ttk.Label(nav, text="Зум:").pack(side=tk.LEFT, padx=(15, 2))
        ttk.Button(nav, text="−", command=self.zoom_out, width=3).pack(side=tk.LEFT)
        ttk.Button(nav, text="+", command=self.zoom_in, width=3).pack(side=tk.LEFT)
        self.zoom_label = ttk.Label(nav, text="150%", width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        ttk.Label(nav, text="Поворот:").pack(side=tk.LEFT, padx=(15, 2))
        ttk.Button(nav, text="↺", command=self.rotate_ccw, width=3).pack(side=tk.LEFT)
        ttk.Button(nav, text="↻", command=self.rotate_cw, width=3).pack(side=tk.LEFT)

        # Привязки мыши
        self.pdf_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.pdf_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.pdf_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.pdf_canvas.bind("<Motion>", self._on_canvas_motion)
        self.pdf_canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.pdf_canvas.bind("<ButtonRelease-3>", self._on_right_click)
        self.pdf_canvas.bind("<MouseWheel>", self._on_mousewheel_pdf)
        self.pdf_canvas.bind("<Button-4>", self._on_mousewheel_pdf)
        self.pdf_canvas.bind("<Button-5>", self._on_mousewheel_pdf)

        # Статус вкладки
        self.status_label = ttk.Label(nav, text="Готов", foreground=self.app.colors["status"])
        self.status_label.pack(side=tk.RIGHT, padx=10)

    # ════════════════════════════════════════════════════════════════════════
    # Загрузка PDF
    # ════════════════════════════════════════════════════════════════════════

    def _load_pdf(self, path, page=0, zoom=1.5):
        """Загружает PDF, переходит на указанную страницу"""
        try:
            self.pdf_doc = fitz.open(path)
            self.pdf_path = path
            self.current_page = min(page, len(self.pdf_doc) - 1)
            self.zoom = zoom
            self.rotation = 0  # ← сброс поворота
            self.render_page()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть PDF:\n{e}")

    def get_state(self):
        """Возвращает состояние вкладки для сохранения в settings.json"""
        return {
            "path": self.pdf_path,
            "page": self.current_page,
            "zoom": self.zoom,
        }

    # ════════════════════════════════════════════════════════════════════════
    # Отображение страницы
    # ════════════════════════════════════════════════════════════════════════

    def render_page(self):
        if not self.pdf_doc:
            return
        page = self.pdf_doc[self.current_page]
        # Применяем поворот
        page.set_rotation(self.rotation)
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pil_img = Image.open(io.BytesIO(pix.tobytes("ppm")))
        self.page_image = pil_img
        self.page_photo = ImageTk.PhotoImage(pil_img)
        w, h = pil_img.size
        self.pdf_canvas.config(scrollregion=(0, 0, w, h))
        if self.image_item:
            self.pdf_canvas.delete(self.image_item)
        self.image_item = self.pdf_canvas.create_image(0, 0, anchor=tk.NW, image=self.page_photo)

        self._clear_selection()
        self._clear_highlight()
        self._crop_top_line_id = None
        self._crop_bottom_line_id = None
        self._update_crop_lines()

        n = len(self.pdf_doc)
        self.page_label.config(text=f"{self.current_page + 1} / {n}")
        self.page_entry.delete(0, tk.END)
        self.page_entry.insert(0, str(self.current_page + 1))
        self.zoom_label.config(text=f"{int(self.zoom * 100)}%")

        # Отложенный перевод
        if self.translate_timer:
            self.app.root.after_cancel(self.translate_timer)
        self.translate_timer = self.app.root.after(300, self.translate_current_page)

    def prev_page(self):
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self._clear_translation()
            self.render_page()

    def next_page(self):
        if self.pdf_doc and self.current_page < len(self.pdf_doc) - 1:
            self.current_page += 1
            self._clear_translation()
            self.render_page()

    def go_to_page(self, event=None):
        if not self.pdf_doc:
            return
        try:
            page_num = int(self.page_entry.get()) - 1
            if 0 <= page_num < len(self.pdf_doc):
                self.current_page = page_num
                self._clear_translation()
                self.render_page()
            else:
                messagebox.showwarning("Вне диапазона", f"Страница от 1 до {len(self.pdf_doc)}")
        except ValueError:
            messagebox.showwarning("Ошибка", "Введите число")

    def zoom_in(self):
        if self.zoom < 4.0:
            self.zoom = round(self.zoom + 0.25, 2)
            self.render_page()

    def zoom_out(self):
        if self.zoom > 0.5:
            self.zoom = round(self.zoom - 0.25, 2)
            self.render_page()

    def rotate_cw(self):
        """Поворот по часовой стрелке на 90°"""
        self.rotation = (self.rotation + 90) % 360
        self._clear_translation()
        self.render_page()
        # Перевод перезапустится автоматически через translate_timer в render_page

    def rotate_ccw(self):
        """Поворот против часовой стрелки на 90°"""
        self.rotation = (self.rotation - 90) % 360
        self._clear_translation()
        self.render_page()

    # ════════════════════════════════════════════════════════════════════════
    # Выделение
    # ════════════════════════════════════════════════════════════════════════

    def _canvas_to_img(self, cx, cy):
        return int(self.pdf_canvas.canvasx(cx)), int(self.pdf_canvas.canvasy(cy))

    def _sel_start(self, event):
        self._clear_selection()
        self.sel_start = self._canvas_to_img(event.x, event.y)

    def _sel_drag(self, event):
        if not self.sel_start:
            return
        cur = self._canvas_to_img(event.x, event.y)
        if self.sel_rect_id:
            self.pdf_canvas.delete(self.sel_rect_id)
        x0, y0 = self.sel_start
        x1, y1 = cur
        self.sel_rect_id = self.pdf_canvas.create_rectangle(
            x0, y0, x1, y1, outline="#e6a817", width=2, fill="#FFD700", stipple="gray25")

    def _sel_end(self, event):
        if not self.sel_start:
            return
        x0, y0 = self.sel_start
        x1, y1 = self._canvas_to_img(event.x, event.y)
        self.selection_rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        w = self.selection_rect[2] - self.selection_rect[0]
        h = self.selection_rect[3] - self.selection_rect[1]
        if w < 5 or h < 5:
            self._clear_selection()
            return
        self.set_status(f"Выделено: {w}×{h} пикс.")
        self.sel_start = None

    def _clear_selection(self):
        if self.sel_rect_id:
            self.pdf_canvas.delete(self.sel_rect_id)
            self.sel_rect_id = None
        self.selection_rect = None
        self.sel_start = None

    def _get_selection_text(self):
        if not self.pdf_doc or not self.selection_rect:
            return ""
        x0, y0, x1, y1 = self.selection_rect
        rect = fitz.Rect(x0 / self.zoom, y0 / self.zoom, x1 / self.zoom, y1 / self.zoom)
        return self.pdf_doc[self.current_page].get_text("text", clip=rect).strip()

    # ════════════════════════════════════════════════════════════════════════
    # Обрезка
    # ════════════════════════════════════════════════════════════════════════

    def _update_crop_lines(self):
        """Рисует 4 линии обрезки"""
        # Удаляем старые линии
        for attr in ['_crop_top_line_id', '_crop_bottom_line_id',
                     '_crop_left_line_id', '_crop_right_line_id']:
            line_id = getattr(self, attr, None)
            if line_id:
                self.pdf_canvas.delete(line_id)
                setattr(self, attr, None)

        if not self.page_image:
            return

        w, h = self.page_image.size
        top = self.crop_top.get()
        bottom = self.crop_bottom.get()
        left = self.crop_left.get()
        right = self.crop_right.get()

        # Верхняя линия
        if top > 0 or True:  # всегда рисуем
            self._crop_top_line_id = self.pdf_canvas.create_line(
                0, top, w, top,
                fill="#e53935", width=5, tags=("crop_line", "crop_top"))

        # Нижняя линия
        bottom_y = h - bottom
        self._crop_bottom_line_id = self.pdf_canvas.create_line(
            0, bottom_y, w, bottom_y,
            fill="#e53935", width=5, tags=("crop_line", "crop_bottom"))

        # Левая линия
        self._crop_left_line_id = self.pdf_canvas.create_line(
            left, 0, left, h,
            fill="#e53935", width=5, tags=("crop_line", "crop_left"))

        # Правая линия
        right_x = w - right
        self._crop_right_line_id = self.pdf_canvas.create_line(
            right_x, 0, right_x, h,
            fill="#e53935", width=5, tags=("crop_line", "crop_right"))

    def _reset_crop(self):
        """Сбрасывает все линии в 0"""
        self.crop_top.set(0)
        self.crop_bottom.set(0)
        self.crop_left.set(0)
        self.crop_right.set(0)
        self._update_crop_lines()
        # Перезапускаем перевод
        if self.pdf_doc:
            self._clear_translation()
            self.translate_current_page()

    def _on_canvas_motion(self, event):
        """Отслеживает наведение на линию обрезки"""
        if not self.page_image:
            return
        if self._dragging_line:
            return  # уже тянем — не меняем курсор
        
        x = self.pdf_canvas.canvasx(event.x)
        y = self.pdf_canvas.canvasy(event.y)
        line = self._detect_line_near(x, y)
        
        if line in ("top", "bottom"):
            self.pdf_canvas.config(cursor="sb_v_double_arrow")
        elif line in ("left", "right"):
            self.pdf_canvas.config(cursor="sb_h_double_arrow")
        else:
            self.pdf_canvas.config(cursor="crosshair")
        
        # Подсветка линии
        self._highlight_line(line)

    def _detect_line_near(self, x, y, threshold=8):
        """Определяет, какая линия рядом с координатами"""
        if not self.page_image:
            return None
        w, h = self.page_image.size
        
        top_y = self.crop_top.get()
        bottom_y = h - self.crop_bottom.get()
        left_x = self.crop_left.get()
        right_x = w - self.crop_right.get()
        
        # Приоритет: горизонтальные линии (верх/низ) — проверяем расстояние по Y
        if abs(y - top_y) < threshold:
            return "top"
        if abs(y - bottom_y) < threshold:
            return "bottom"
        if abs(x - left_x) < threshold:
            return "left"
        if abs(x - right_x) < threshold:
            return "right"
        return None

    def _highlight_line(self, line):
        """Подсвечивает линию при наведении"""
        mapping = {
            "top": "_crop_top_line_id",
            "bottom": "_crop_bottom_line_id",
            "left": "_crop_left_line_id",
            "right": "_crop_right_line_id",
        }
        for key, attr in mapping.items():
            line_id = getattr(self, attr, None)
            if not line_id:
                continue
            if key == line:
                self.pdf_canvas.itemconfig(line_id, fill="#ff0000", width=7)
            else:
                self.pdf_canvas.itemconfig(line_id, fill="#e53935", width=5)

    def _on_canvas_press(self, event):
        """Нажатие мыши — начало перетаскивания линии или выделения"""
        x = self.pdf_canvas.canvasx(event.x)
        y = self.pdf_canvas.canvasy(event.y)
        line = self._detect_line_near(x, y)
        
        if line:
            self._dragging_line = line
            self._drag_start_x = x
            self._drag_start_y = y
            return  # не начинаем выделение
    
        # Иначе — обычное выделение
        self._sel_start(event)

    def _on_canvas_drag(self, event):
        """Движение мыши — перетаскивание линии или выделения"""
        if self._dragging_line:
            self._drag_line(event)
        else:
            self._sel_drag(event)

    def _on_canvas_release(self, event):
        """Отпускание мыши"""
        if self._dragging_line:
            self._dragging_line = None
            self._update_crop_lines()
            # Перезапуск перевода
            if self.pdf_doc:
                self._clear_translation()
                self.translate_current_page()
            return
        
        self._sel_end(event)

    def _drag_line(self, event):
        """Двигает выбранную линию"""
        if not self.page_image:
            return
        
        x = self.pdf_canvas.canvasx(event.x)
        y = self.pdf_canvas.canvasy(event.y)
        w, h = self.page_image.size
        
        if self._dragging_line == "top":
            new_y = max(0, min(int(y), h - self.crop_bottom.get() - 10))
            self.crop_top.set(new_y)
        elif self._dragging_line == "bottom":
            new_y = max(0, min(int(h - y), h - self.crop_top.get() - 10))
            self.crop_bottom.set(new_y)
        elif self._dragging_line == "left":
            new_x = max(0, min(int(x), w - self.crop_right.get() - 10))
            self.crop_left.set(new_x)
        elif self._dragging_line == "right":
            new_x = max(0, min(int(w - x), w - self.crop_left.get() - 10))
            self.crop_right.set(new_x)
        
        self._update_crop_lines()

    def _on_canvas_double_click(self, event):
        """Двойной клик — сброс линии"""
        x = self.pdf_canvas.canvasx(event.x)
        y = self.pdf_canvas.canvasy(event.y)
        line = self._detect_line_near(x, y)
        
        if line == "top":
            self.crop_top.set(0)
        elif line == "bottom":
            self.crop_bottom.set(0)
        elif line == "left":
            self.crop_left.set(0)
        elif line == "right":
            self.crop_right.set(0)
        else:
            return
        
        self._update_crop_lines()
        if self.pdf_doc:
            self._clear_translation()
            self.translate_current_page()

    def _get_crop_rect_pdf(self):
        if not self.pdf_doc or not self.page_image:
            return None
        top_px = self.crop_top.get()
        bottom_px = self.crop_bottom.get()
        left_px = self.crop_left.get()
        right_px = self.crop_right.get()
        
        if top_px == 0 and bottom_px == 0 and left_px == 0 and right_px == 0:
            return None
        
        img_w, img_h = self.page_image.size
        x0 = left_px / self.zoom
        y0 = top_px / self.zoom
        x1 = (img_w - right_px) / self.zoom
        y1 = (img_h - bottom_px) / self.zoom
        
        page = self.pdf_doc[self.current_page]
        return fitz.Rect(x0, y0, x1, y1)

    # ════════════════════════════════════════════════════════════════════════
    # Получение текста с абзацами
    # ════════════════════════════════════════════════════════════════════════

    def _get_page_text(self):
        if not self.pdf_doc:
            return ""
        clip_rect = self._get_crop_rect_pdf()
        page = self.pdf_doc[self.current_page]
        if clip_rect:
            raw_text = page.get_text("text", clip=clip_rect)
        else:
            raw_text = page.get_text("text")
        if not raw_text.strip():
            return ""
        return self._restore_paragraphs_by_indent(raw_text, page, clip_rect)

    def _restore_paragraphs_by_indent(self, text, page, clip_rect=None):
        if not page:
            return text
        blocks = page.get_text("dict")["blocks"]
        lines_with_info = []
        for block in blocks:
            if block["type"] == 0:
                for line in block["lines"]:
                    x0 = line["bbox"][0]
                    x1 = line["bbox"][2]
                    y0 = line["bbox"][1]
                    if clip_rect:
                        if y0 < clip_rect.y0 or y0 > clip_rect.y1:
                            continue
                        if x1 < clip_rect.x0 or x0 > clip_rect.x1:
                            continue
                        x0 = x0 - clip_rect.x0
                    text_line = " ".join([span["text"] for span in line["spans"]])
                    if text_line.strip():
                        lines_with_info.append((x0, text_line))
        if len(lines_with_info) < 2:
            return text
        indents = sorted([x0 for x0, _ in lines_with_info])
        normal_indent = indents[len(indents) // 2]
        paragraph_threshold = normal_indent + 5
        result = []
        for i, (x0, line_text) in enumerate(lines_with_info):
            if i > 0 and x0 > paragraph_threshold:
                result.append("")
            result.append(line_text)
        return '\n'.join(result)

    # ════════════════════════════════════════════════════════════════════════
    # Перевод
    # ════════════════════════════════════════════════════════════════════════

    def translate_current_page(self):
        if not self.pdf_doc:
            return
        if self.is_translating:
            return
        self.set_status("Перевожу…")
        threading.Thread(target=self._translate_page_thread, daemon=True).start()

    def _translate_page_thread(self):
        if self.is_translating:
            return
        self.is_translating = True
        try:
            text = self._get_page_text()
            if not text.strip():
                self.app.root.after(0, lambda: self._show_translation("Текст не найден"))
                return
            result = self._do_translate(text)
            self.app.root.after(0, lambda: self._show_translation(result))
            self.app.root.after(0, lambda: self.set_status("Перевод готов"))
        except Exception as e:
            print(f"Ошибка: {e}")
        finally:
            self.is_translating = False

    def _do_translate(self, text, src=None):
        """Диспетчер: выбирает переводчик из настроек главного окна"""
        if not text or not text.strip():
            return ""
        
        if src is None:
            src = self.app.settings.get("source_lang", "auto")
        
        translator = self.app.settings.get("translator", "google")
        target = self.app.settings.get("target_lang", "ru")
        
        if translator == "google":
            return self._translate_google(text, src, target)
        elif translator == "yandex":
            return self._translate_yandex(text, src, target)
        elif translator == "deepl":
            return self._translate_deepl(text, src, target)
        else:
            return self._translate_google(text, src, target)

    def _translate_google(self, text, src, target):
        try:
            paragraphs = re.split(r'\n\s*\n', text.strip())
            translated = []
            translator = GoogleTranslator(source=src, target=target)
            for para in paragraphs:
                if not para.strip():
                    translated.append("")
                    continue
                cleaned = ' '.join(para.split())
                if cleaned:
                    try:
                        t = translator.translate(cleaned)
                        translated.append(t if t else "")
                    except Exception as e:
                        print(f"Google error: {e}")
                        translated.append("")
            safe = [p for p in translated if p is not None]
            return '\n\n'.join(safe)
        except Exception as e:
            return f"[Google ошибка: {e}]"

    def _translate_yandex(self, text, src, target):
        api_key = self.app.settings["api_keys"].get("yandex_api_key", "")
        folder_id = self.app.settings["api_keys"].get("yandex_folder_id", "")
        
        if not api_key or not folder_id:
            self.app.root.after(0, self.app._open_api_settings)
            return "[Яндекс: укажите API-ключ и Folder ID]"
        
        url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}"
        }
        
        paragraphs = re.split(r'\n\s*\n', text.strip())
        translated = []
        source_code = None if src == "auto" else src
        
        for para in paragraphs:
            if not para.strip():
                translated.append("")
                continue
            cleaned = ' '.join(para.split())
            if not cleaned:
                translated.append("")
                continue
            
            body = {
                "folderId": folder_id,
                "texts": [cleaned],
                "targetLanguageCode": target,
            }
            if source_code:
                body["sourceLanguageCode"] = source_code
            
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=30)
                resp.raise_for_status()
                result = resp.json()["translations"][0]["text"]
                translated.append(result)
            except Exception as e:
                print(f"Яндекс ошибка: {e}")
                translated.append(f"[Яндекс ошибка: {e}]")
        
        return '\n\n'.join(translated)

    def _translate_deepl(self, text, src, target):
        api_key = self.app.settings["api_keys"].get("deepl_api_key", "")
        if not api_key:
            self.app.root.after(0, self.app._open_api_settings)
            return "[DeepL: укажите API-ключ]"
        
        target_lang = target.upper()
        
        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": api_key,
            "text": text,
            "target_lang": target_lang
        }
        if src != "auto":
            params["source_lang"] = src.upper()
        
        try:
            resp = requests.post(url, data=params, timeout=60)
            resp.raise_for_status()
            return resp.json()["translations"][0]["text"]
        except Exception as e:
            return f"[DeepL ошибка: {e}]"

    # ════════════════════════════════════════════════════════════════════════
    # Отображение перевода
    # ════════════════════════════════════════════════════════════════════════

    def _clear_translation(self):
        self.trans_text.config(state=tk.NORMAL)
        self.trans_text.delete("1.0", tk.END)
        self.trans_text.config(state=tk.DISABLED)

    def _show_translation(self, text):
        self.trans_text.config(state=tk.NORMAL)
        self.trans_text.delete("1.0", tk.END)
        self.trans_text.insert(tk.END, text)
        self.trans_text.config(state=tk.DISABLED)

    def update_font_size(self, size):
        """Обновляет размер шрифта в правой панели"""
        self.trans_text.configure(font=("Segoe UI", size))

    # ════════════════════════════════════════════════════════════════════════
    # ПКМ — плавающее окно перевода
    # ════════════════════════════════════════════════════════════════════════

    def _on_right_click(self, event):
        if not self.selection_rect:
            return
        text = self._get_selection_text()
        if text.strip():
            self._show_floating_translation(event, text)

    def _show_floating_translation(self, event, text):
        self._close_popup()
        
        self.popup_win = tk.Toplevel(self.app.root)
        self.popup_win.title("Перевод")
        self.popup_win.overrideredirect(True)
        self.popup_win.attributes("-topmost", True)
        
        x = event.x_root + 15
        y = event.y_root + 15
        self.popup_win.geometry(f"450x350+{x}+{y}")
        
        frame = tk.Frame(self.popup_win, bg="#f5f5f5", relief=tk.RAISED, bd=1)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Оригинал:", font=("Segoe UI", 9, "bold"), bg="#f5f5f5").pack(anchor=tk.W, padx=8, pady=2)
        tk.Label(frame, text=text[:500], wraplength=420, justify=tk.LEFT, bg="#f5f5f5").pack(fill=tk.X, padx=8, pady=2)
        
        tk.Label(frame, text="Перевод:", font=("Segoe UI", 9, "bold"), bg="#f5f5f5").pack(anchor=tk.W, padx=8, pady=2)
        trans_label = tk.Label(frame, text="⏳ Загрузка...", wraplength=420, justify=tk.LEFT, bg="#ffffcc")
        trans_label.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        tk.Button(frame, text="✖", command=self._close_popup,
                  bg="#ff6666", fg="white", width=2, relief=tk.FLAT).place(x=425, y=2)
        
        def do_translate():
            try:
                result = self._do_translate(text)
                trans_label.config(text=result, bg="#ffffcc")
            except Exception as e:
                trans_label.config(text=f"Ошибка: {e}", bg="#ffcccc")
        threading.Thread(target=do_translate, daemon=True).start()
        
        def close_on_click(e):
            if self.popup_win and not (self.popup_win.winfo_containing(e.x_root, e.y_root) == self.popup_win):
                self._close_popup()
        self.app.root.bind("<Button-1>", close_on_click, add="+")

    def _close_popup(self):
        if hasattr(self, 'popup_win') and self.popup_win:
            try:
                self.popup_win.destroy()
            except:
                pass
            self.popup_win = None

    # ════════════════════════════════════════════════════════════════════════
    # Кнопки из главного окна (вызываются через активную вкладку)
    # ════════════════════════════════════════════════════════════════════════

    def translate_selection(self):
        """Перевод выделенного (кнопка главного окна)"""
        text = self._get_selection_text()
        if not text:
            messagebox.showwarning("Внимание", "Выделите область на PDF")
            return
        self.app._open_result_window("Перевод выделенного", text, "⏳ Загрузка...")
        threading.Thread(target=self._do_translate_selection, args=(text,), daemon=True).start()

    def _do_translate_selection(self, text):
        result = self._do_translate(text)

        def update_ui():
            if hasattr(self.app, '_result_win_text') and self.app._result_win_text:
                self.app._result_win_text.config(state=tk.NORMAL)
                self.app._result_win_text.delete("1.0", tk.END)
                self.app._result_win_text.insert(1.0, result)
        self.app.root.after(0, update_ui)

    def explain_ai(self):
        """Объяснение через DeepSeek (кнопка главного окна)"""
        text = self._get_selection_text()
        if not text:
            messagebox.showwarning("Внимание", "Выделите область на PDF")
            return
        api_key = self.app.settings["api_keys"].get("deepseek_api_key", "")
        if not api_key:
            messagebox.showwarning("Внимание", "Введите DeepSeek API-ключ в настройках")
            self.app._open_api_settings()
            return
        self.app._open_result_window("Объяснение от ИИ", text, "⏳ Отправляю запрос...")
        threading.Thread(target=self._do_explain_ai, args=(text, api_key), daemon=True).start()

    def _do_explain_ai(self, text, api_key):
        prompt = f"Перескажи этот текст своими словами на русском, кратко и понятно. Только пересказ, без лишних слов. Текст: {text}"
        try:
            resp = requests.post(
                self.app.DEEPSEEK_URL,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {api_key}"},
                json={"model": self.app.DEEPSEEK_MODEL, "max_tokens": 1024,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            result = f"[Ошибка: {e}]"

        def update_ui():
            if hasattr(self.app, '_result_win_text') and self.app._result_win_text:
                self.app._result_win_text.config(state=tk.NORMAL)
                self.app._result_win_text.delete("1.0", tk.END)
                self.app._result_win_text.insert(1.0, f"Оригинал:\n{text}\n\n{'─'*50}\n\nОбъяснение ИИ:\n{result}")
        self.app.root.after(0, update_ui)

    # ════════════════════════════════════════════════════════════════════════
    # Синхронная прокрутка
    # ════════════════════════════════════════════════════════════════════════

    def _pdf_yscroll_set(self, first, last):
        if self.app.sync_scroll_var.get() and not self._scrolling:
            self._scrolling = True
            self.trans_text.yview_moveto(first)
            self._scrolling = False

    def _trans_yscroll_set(self, first, last):
        if self.app.sync_scroll_var.get() and not self._scrolling:
            self._scrolling = True
            self.pdf_canvas.yview_moveto(first)
            self._scrolling = False

    def _on_pdf_scroll_y(self, *args):
        self.pdf_canvas.yview(*args)

    def _on_trans_scroll_y(self, *args):
        self.trans_text.yview(*args)

    def _on_mousewheel_pdf(self, event):
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        if event.state & 0x4:
            self.zoom_in() if delta < 0 else self.zoom_out()
        else:
            self.pdf_canvas.yview_scroll(delta * 3, "units")
            if self.app.sync_scroll_var.get():
                self.trans_text.yview_scroll(delta * 3, "units")

    # ════════════════════════════════════════════════════════════════════════
    # Подсветка
    # ════════════════════════════════════════════════════════════════════════

    def _highlight_in_pdf(self, coords):
        self._clear_highlight()
        if not coords:
            return
        x0, y0, x1, y1 = [c * self.zoom for c in coords]
        pad = 30
        rx0, ry0 = max(0, x0 - pad), max(0, y0 - 4)
        rx1, ry1 = x1 + pad * 4, y1 + 4
        self.highlight_rect_id = self.pdf_canvas.create_rectangle(
            rx0, ry0, rx1, ry1, outline="#e6a817", width=3, fill="#FFD700", stipple="gray12")
        _, h = self.page_image.size if self.page_image else (1, 1)
        if h > 0:
            frac = (ry0 - self.pdf_canvas.winfo_height() / 4) / h
            self.pdf_canvas.yview_moveto(max(0, frac))

    def _clear_highlight(self):
        if self.highlight_rect_id:
            self.pdf_canvas.delete(self.highlight_rect_id)
            self.highlight_rect_id = None