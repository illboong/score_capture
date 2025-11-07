import os
import sys
import time
import cv2
import mss
import numpy as np
from skimage.metrics import structural_similarity as compare_ssim
from PIL import Image, ImageDraw, ImageFont, ImageTk
import imagehash
import configparser
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as bttk

# --- 설정 파일 및 전역 변수 ---
CONFIG_FILE = 'config.ini'
OUTPUT_FOLDER = "captured_scores"

# --- 메인 애플리케이션 클래스 ---
class ScoreCaptureApp:
    def __init__(self, root):
        self.root = root
        self.root.title("악보 자동 캡처 v2.0")
        self.root.geometry("960x600")
        self.root.resizable(False, False)

        self.capture_area = None
        self.is_capturing = False
        self.last_captured_image_gray = None
        self.last_captured_image_hash = None
        self.captured_image_files = []

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        main_frame = bttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        left_pane = bttk.Frame(main_frame, padding="10")
        left_pane.grid(row=0, column=0, sticky="ns")

        settings_frame = bttk.Labelframe(left_pane, text="캡처 설정", padding=10)
        settings_frame.pack(fill="x", pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)

        bttk.Label(settings_frame, text="민감도 (0.0-1.0):").grid(row=0, column=0, sticky="w", pady=5)
        self.similarity_var = tk.StringVar(value="0.9")
        self.similarity_entry = bttk.Entry(settings_frame, textvariable=self.similarity_var, width=8)
        self.similarity_entry.grid(row=0, column=1, sticky="e")

        bttk.Label(settings_frame, text="시작 딜레이 (초):").grid(row=1, column=0, sticky="w", pady=5)
        self.delay_var = tk.StringVar(value="3")
        self.delay_entry = bttk.Entry(settings_frame, textvariable=self.delay_var, width=8)
        self.delay_entry.grid(row=1, column=1, sticky="e")

        button_frame = bttk.Frame(left_pane)
        button_frame.pack(fill="x", pady=10)
        
        self.select_button = bttk.Button(button_frame, text="1. 캡처 영역 선택", command=self.select_capture_area, bootstyle="primary-outline")
        self.select_button.pack(fill="x", pady=5)

        self.start_button = bttk.Button(button_frame, text="2. 캡처 시작", command=self.start_capture, state=tk.DISABLED, bootstyle="success")
        self.start_button.pack(fill="x", pady=5)
        
        self.stop_button = bttk.Button(button_frame, text="캡처 중지", command=self.stop_capture, state=tk.DISABLED, bootstyle="warning")
        self.stop_button.pack(fill="x", pady=5)

        self.create_pdf_button = bttk.Button(button_frame, text="3. 선택 파일로 PDF 생성", command=self.create_pdf, state=tk.DISABLED, bootstyle="danger")
        self.create_pdf_button.pack(fill="x", pady=20)

        right_pane = bttk.Labelframe(main_frame, text="캡처 결과 확인", padding="10")
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right_pane.rowconfigure(1, weight=1)
        right_pane.columnconfigure(0, weight=1)

        list_frame = bttk.Frame(right_pane)
        list_frame.grid(row=0, column=0, sticky="ew")
        list_frame.columnconfigure(0, weight=1)
        self.preview_listbox = tk.Listbox(list_frame, height=8)
        self.preview_listbox.grid(row=0, column=0, sticky="ew")
        self.preview_listbox.bind("<<ListboxSelect>>", self.show_preview)
        
        delete_button = bttk.Button(list_frame, text="선택 삭제", command=self.delete_selected_image, bootstyle="secondary-outline")
        delete_button.grid(row=0, column=1, sticky="ne", padx=(10, 0))
        
        preview_display_frame = bttk.Frame(right_pane, relief="sunken", borderwidth=1)
        preview_display_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        preview_display_frame.grid_propagate(False)
        preview_display_frame.rowconfigure(0, weight=1)
        preview_display_frame.columnconfigure(0, weight=1)

        self.preview_label = bttk.Label(preview_display_frame, text="목록에서 이미지를 선택하세요", anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        # ★★★★★ 오류 수정된 부분 ★★★★★
        # 1. StringVar를 self.status_var에 먼저 생성하고 저장합니다.
        self.status_var = tk.StringVar(value="영역을 먼저 선택해주세요.")
        
        # 2. 저장된 self.status_var를 Label의 textvariable로 사용합니다.
        status_label = bttk.Label(self.root, textvariable=self.status_var, padding="10 5", anchor='center', relief="sunken")
        status_label.grid(row=1, column=0, sticky="ew")
        # ★★★★★ 수정 완료 ★★★★★

    def show_preview(self, event=None):
        selected_indices = self.preview_listbox.curselection()
        if not selected_indices: return
        filepath = self.captured_image_files[selected_indices[0]]

        try:
            image = Image.open(filepath)
            container = self.preview_label.master
            container.update_idletasks()
            preview_width = container.winfo_width()
            preview_height = container.winfo_height()
            image.thumbnail((preview_width, preview_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo
        except Exception as e:
            self.preview_label.config(image="", text=f"미리보기를 로드할 수 없습니다:\n{e}")
            self.preview_label.image = None

    def delete_selected_image(self):
        selected_indices = self.preview_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("알림", "삭제할 항목을 선택해주세요.")
            return

        for index in reversed(selected_indices):
            filepath_to_delete = self.captured_image_files.pop(index)
            self.preview_listbox.delete(index)
            try:
                if os.path.exists(filepath_to_delete):
                    os.remove(filepath_to_delete)
            except Exception as e:
                print(f"파일 삭제 오류: {filepath_to_delete}, {e}")

        self.preview_label.config(image="", text="목록에서 이미지를 선택하세요")
        self.preview_label.image = None
        
        if not self.captured_image_files:
            self.create_pdf_button.config(state=tk.DISABLED)
        self.update_status(f"{len(selected_indices)}개 항목 삭제 완료.")

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
            self.similarity_var.set(config.get('Settings', 'similarity_threshold', fallback='0.9'))
            
    def save_config(self):
        config = configparser.ConfigParser()
        config['Settings'] = {'similarity_threshold': self.similarity_var.get()}
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def save_image(self, image_bgr):
        pil_img = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        current_hash = imagehash.phash(pil_img)
        if self.last_captured_image_hash is not None and (current_hash - self.last_captured_image_hash < 4):
            self.update_status(f"중복 페이지 감지. 건너뜁니다.")
            return
        self.last_captured_image_hash = current_hash
        image_to_save = cv2.cvtColor(image_bgr, cv2.COLOR_BGRA2BGR)
        
        if not os.path.exists(OUTPUT_FOLDER): os.makedirs(OUTPUT_FOLDER)
        
        filename = os.path.join(OUTPUT_FOLDER, f"score_page_{len(self.captured_image_files) + 1:03d}.png")
        cv2.imwrite(filename, image_to_save)
        self.captured_image_files.append(filename)
        
        self.preview_listbox.insert(tk.END, os.path.basename(filename))
        self.preview_listbox.see(tk.END)

    def reset_state(self):
        self.last_captured_image_gray = None
        self.last_captured_image_hash = None
        self.captured_image_files.clear()
        self.preview_listbox.delete(0, tk.END)
        self.preview_label.config(image="", text="목록에서 이미지를 선택하세요")
        self.preview_label.image = None
        self.start_button.config(state=tk.NORMAL if self.capture_area else tk.DISABLED)
        self.select_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.create_pdf_button.config(state=tk.DISABLED)
        self.update_status("준비 완료. 영역을 선택하거나 캡처를 시작하세요.")

    def update_status(self, message):
        self.status_var.set(message)
        self.root.update_idletasks()

    def start_capture(self):
        try:
            delay = int(self.delay_var.get())
        except ValueError:
            messagebox.showerror("입력 오류", "딜레이는 숫자로 입력해야 합니다.")
            return
        self.save_config()
        self.is_capturing = True
        self.start_button.config(state=tk.DISABLED)
        self.select_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.create_pdf_button.config(state=tk.DISABLED)
        def countdown(count):
            if count > 0:
                self.update_status(f"{count}초 후 캡처를 시작합니다...")
                self.root.after(1000, countdown, count - 1)
            else:
                self.update_status("캡처 진행 중... (중지하려면 '캡처 중지' 클릭)")
                self.capture_loop()
        countdown(delay)

    def stop_capture(self):
        self.is_capturing = False
        self.select_button.config(state=tk.NORMAL)
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        if self.captured_image_files:
            self.create_pdf_button.config(state=tk.NORMAL)
        self.update_status("캡처 중지. 목록을 편집하거나 PDF를 생성하세요.")

    def create_pdf(self):
        self.update_status("PDF 생성 중... 잠시만 기다려주세요."); self.root.update_idletasks()
        active_files = self.captured_image_files.copy()
        if not active_files:
            messagebox.showwarning("알림", "캡처된 이미지가 없어 PDF를 생성할 수 없습니다."); self.reset_state(); return
        try:
            image_objects = [Image.open(f).convert("RGB") for f in active_files]
            base_width = image_objects[0].width; a4_ratio = 297 / 210; page_height = int(base_width * a4_ratio)
            final_pages = []; current_page = Image.new('RGB', (base_width, page_height), 'white'); y_offset = 0
            for img in image_objects:
                if img.width != base_width: new_img = Image.new('RGB', (base_width, img.height), 'white'); new_img.paste(img, ((base_width - img.width) // 2, 0)); img = new_img
                if y_offset + img.height > page_height: final_pages.append(current_page); current_page = Image.new('RGB', (base_width, page_height), 'white'); y_offset = 0
                current_page.paste(img, (0, y_offset)); y_offset += img.height
            final_pages.append(current_page)
            total_pages = len(final_pages); pages_with_numbers = []
            try: font = ImageFont.truetype("arial.ttf", size=16)
            except IOError: font = ImageFont.load_default()
            for i, page in enumerate(final_pages, 1):
                draw = ImageDraw.Draw(page); page_num_text = f"{i} / {total_pages}"; bbox = draw.textbbox((0, 0), page_num_text, font=font)
                text_width = bbox[2] - bbox[0]; text_height = bbox[3] - bbox[1]
                x = (base_width - text_width) / 2; y = page_height - text_height - 10
                draw.text((x, y), page_num_text, font=font, fill="black"); pages_with_numbers.append(page)
            if pages_with_numbers:
                pdf_filename = filedialog.asksaveasfilename(title="PDF 파일로 저장", defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")], initialfile="악보.pdf")
                if pdf_filename:
                    pages_with_numbers[0].save(pdf_filename, save_all=True, append_images=pages_with_numbers[1:])
                    messagebox.showinfo("성공", f"'{os.path.basename(pdf_filename)}' 파일이 성공적으로 생성되었습니다.")
                    self._cleanup_captured_images()
                else: self.update_status("PDF 저장이 취소되었습니다.")
            else: messagebox.showwarning("알림", "PDF로 변환할 페이지가 없습니다.")
        except Exception as e: messagebox.showerror("오류", f"PDF 생성 중 오류가 발생했습니다:\n{e}")
        self.reset_state()

    def select_capture_area(self):
        self.update_status("캡처할 영역을 드래그하세요..."); self.root.withdraw(); time.sleep(0.5)
        with mss.mss() as sct: sct_img = sct.grab(sct.monitors[0]); screenshot = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
        selector = AreaSelector(screenshot); self.capture_area = selector.select_area("캡처할 '악보 전체 영역'을 마우스로 드래그하세요."); self.root.deiconify()
        if self.capture_area: self.update_status("영역 선택 완료. 캡처를 시작하세요."); self.start_button.config(state=tk.NORMAL)
        else: self.update_status("영역 선택이 취소되었습니다.")

    def capture_loop(self):
        if not self.is_capturing: return
        with mss.mss() as sct:
            sct_img = sct.grab(self.capture_area); current_image_bgr = np.array(sct_img)
            current_image_gray = cv2.cvtColor(current_image_bgr, cv2.COLOR_BGRA2GRAY)
            if self.last_captured_image_gray is None:
                self.update_status("첫 악보 감지! 캡처합니다."); self.last_captured_image_gray = current_image_gray; self.save_image(current_image_bgr)
            else:
                try:
                    score, _ = compare_ssim(self.last_captured_image_gray, current_image_gray, full=True)
                    if score < float(self.similarity_var.get()): self.update_status(f"새로운 악보 감지! (유사도: {score:.2f})"); self.last_captured_image_gray = current_image_gray; self.save_image(current_image_bgr)
                except ValueError: self.update_status("캡처 영역 크기 변경 감지. 재시도합니다."); self.last_captured_image_gray = current_image_gray
        self.root.after(1000, self.capture_loop)
    
    def _cleanup_captured_images(self):
        self.update_status("임시 캡처 파일을 삭제하는 중...")
        if os.path.exists(OUTPUT_FOLDER):
            for f in os.listdir(OUTPUT_FOLDER):
                try: os.remove(os.path.join(OUTPUT_FOLDER, f))
                except Exception as e: print(f"경고: 파일 삭제 실패 '{f}': {e}")
            try: os.rmdir(OUTPUT_FOLDER)
            except Exception as e: print(f"경고: 폴더 삭제 실패 '{OUTPUT_FOLDER}': {e}")
        self.captured_image_files.clear()

class AreaSelector:
    def __init__(self, screen_shot): self.image = screen_shot; self.point1 = None; self.point2 = None; self.rect_done = False
    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN: self.point1 = (x, y); self.rect_done = False
        elif event == cv2.EVENT_MOUSEMOVE and self.point1: img_copy = self.image.copy(); cv2.rectangle(img_copy, self.point1, (x, y), (0, 255, 0), 2); cv2.imshow("Area Selector", img_copy)
        elif event == cv2.EVENT_LBUTTONUP: self.point2 = (x, y); self.rect_done = True
    def select_area(self, instructions):
        cv2.namedWindow("Area Selector", cv2.WINDOW_NORMAL); screen_h, screen_w, _ = self.image.shape
        cv2.resizeWindow("Area Selector", int(screen_w * 0.7), int(screen_h * 0.7)); cv2.setMouseCallback("Area Selector", self.mouse_callback)
        img_with_text = self.image.copy(); cv2.putText(img_with_text, instructions, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Area Selector", img_with_text)
        while not self.rect_done:
            if cv2.waitKey(1) & 0xFF == 27: cv2.destroyAllWindows(); return None
        cv2.destroyAllWindows(); left = min(self.point1[0], self.point2[0]); top = min(self.point1[1], self.point2[1])
        width = abs(self.point1[0] - self.point2[0]); height = abs(self.point1[1] - self.point2[1])
        if width == 0 or height == 0: return None
        return {'top': top, 'left': left, 'width': width, 'height': height}

if __name__ == "__main__":
    root = bttk.Window(themename="litera")
    app = ScoreCaptureApp(root)
    root.mainloop()