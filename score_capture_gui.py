import os
import sys
import time
import cv2
import mss
import numpy as np
from skimage.metrics import structural_similarity as compare_ssim
from PIL import Image
import configparser
import tkinter as tk
from tkinter import ttk, messagebox

# --- 설정 파일 및 전역 변수 ---
CONFIG_FILE = 'config.ini'
OUTPUT_FOLDER = "captured_scores"

# --- 메인 애플리케이션 클래스 ---
class ScoreCaptureApp:
    def __init__(self, root):
        # --- 기본 설정 ---
        self.root = root
        self.root.title("악보 자동 캡처")
        self.root.geometry("320x220") # 창 크기
        self.root.resizable(False, False) # 창 크기 조절 불가

        # --- 상태 변수 ---
        self.capture_area = None
        self.is_capturing = False
        self.last_captured_image_gray = None
        self.captured_image_files = []

        # --- UI 위젯 생성 ---
        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        # --- 프레임 설정 ---
        frame = ttk.Frame(self.root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- 설정 값 입력 UI ---
        ttk.Label(frame, text="민감도 (0.0-1.0):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.similarity_var = tk.StringVar(value="0.9")
        self.similarity_entry = ttk.Entry(frame, textvariable=self.similarity_var, width=10)
        self.similarity_entry.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(frame, text="시작 딜레이 (초):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.delay_var = tk.StringVar(value="3")
        self.delay_entry = ttk.Entry(frame, textvariable=self.delay_var, width=10)
        self.delay_entry.grid(row=1, column=1, sticky=tk.W)

        # --- 버튼 UI ---
        self.select_button = ttk.Button(frame, text="1. 캡처 영역 선택", command=self.select_capture_area)
        self.select_button.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        self.start_button = ttk.Button(frame, text="2. 캡처 시작", command=self.start_capture, state=tk.DISABLED)
        self.start_button.grid(row=3, column=0, sticky=(tk.W, tk.E))

        self.stop_button = ttk.Button(frame, text="종료 및 PDF 생성", command=self.stop_and_create_pdf, state=tk.DISABLED)
        self.stop_button.grid(row=3, column=1, sticky=(tk.W, tk.E))

        # --- 상태 표시줄 ---
        self.status_var = tk.StringVar(value="영역을 먼저 선택해주세요.")
        status_label = ttk.Label(self.root, textvariable=self.status_var, padding="10 5", relief=tk.SUNKEN)
        status_label.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.S))

    def update_status(self, message):
        self.status_var.set(message)
        self.root.update_idletasks()

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
            threshold = config.get('Settings', 'similarity_threshold', fallback='0.9')
            self.similarity_var.set(threshold)

    def save_config(self):
        config = configparser.ConfigParser()
        config['Settings'] = {'similarity_threshold': self.similarity_var.get()}
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def select_capture_area(self):
        self.update_status("캡처할 영역을 드래그하세요...")
        self.root.withdraw() # 메인 창 잠시 숨기기
        time.sleep(0.5)

        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
            screenshot = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
        
        selector = AreaSelector(screenshot)
        self.capture_area = selector.select_area("캡처할 '악보 전체 영역'을 마우스로 드래그하세요.")
        
        self.root.deiconify() # 메인 창 다시 보이기

        if self.capture_area:
            self.update_status("영역 선택 완료. 캡처를 시작하세요.")
            self.start_button.config(state=tk.NORMAL)
        else:
            self.update_status("영역 선택이 취소되었습니다.")

    def start_capture(self):
        try:
            delay = int(self.delay_var.get())
            threshold = float(self.similarity_var.get())
        except ValueError:
            messagebox.showerror("입력 오류", "민감도와 딜레이는 숫자로 입력해야 합니다.")
            return

        self.save_config() # 현재 설정값 저장

        self.is_capturing = True
        self.start_button.config(state=tk.DISABLED)
        self.select_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # 카운트다운
        def countdown(count):
            if count > 0:
                self.update_status(f"{count}초 후 캡처를 시작합니다...")
                self.root.after(1000, countdown, count - 1)
            else:
                self.update_status("캡처 진행 중...")
                self.capture_loop()
        
        countdown(delay)

    def capture_loop(self):
        if not self.is_capturing:
            return

        with mss.mss() as sct:
            sct_img = sct.grab(self.capture_area)
            current_image_bgr = np.array(sct_img)
            current_image_gray = cv2.cvtColor(current_image_bgr, cv2.COLOR_BGRA2GRAY)

            if self.last_captured_image_gray is None:
                self.update_status("첫 악보 감지! 캡처합니다.")
                self.last_captured_image_gray = current_image_gray
                self.save_image(current_image_bgr)
            else:
                score, _ = compare_ssim(self.last_captured_image_gray, current_image_gray, full=True)
                if score < float(self.similarity_var.get()):
                    self.update_status(f"새로운 악보 감지! (유사도: {score:.2f})")
                    self.last_captured_image_gray = current_image_gray
                    self.save_image(current_image_bgr)
        
        self.root.after(1000, self.capture_loop) # 1초 뒤에 다시 실행

    def save_image(self, image_bgr):
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
        filename = os.path.join(OUTPUT_FOLDER, f"score_page_{len(self.captured_image_files) + 1:03d}.png")
        cv2.imwrite(filename, cv2.cvtColor(image_bgr, cv2.COLOR_BGRA2BGR))
        self.captured_image_files.append(filename)

    def stop_and_create_pdf(self):
        self.is_capturing = False
        self.update_status("PDF 생성 중... 잠시만 기다려주세요.")

        if self.captured_image_files:
            image_list = [Image.open(f) for f in self.captured_image_files]
            widths, heights = zip(*(i.size for i in image_list))
            total_height = sum(heights)
            max_width = max(widths)
            stitched_image = Image.new('RGB', (max_width, total_height))
            y_offset = 0
            for img in image_list:
                stitched_image.paste(img, (0, y_offset))
                y_offset += img.size[1]
            
            pdf_filename = "final_sheet_music_stitched.pdf"
            stitched_image.save(pdf_filename, "PDF", resolution=100.0)
            messagebox.showinfo("성공", f"'{pdf_filename}' 파일이 성공적으로 생성되었습니다.")
        else:
            messagebox.showwarning("알림", "캡처된 이미지가 없어 PDF를 생성하지 않았습니다.")
        
        # 상태 초기화
        self.reset_state()

    def reset_state(self):
        self.last_captured_image_gray = None
        self.captured_image_files = []
        self.start_button.config(state=tk.NORMAL if self.capture_area else tk.DISABLED)
        self.select_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_status("준비 완료. 영역을 선택하거나 캡처를 시작하세요.")

# --- 영역 선택 클래스 (이전과 동일) ---
class AreaSelector:
    # (이전 버전의 AreaSelector 클래스 코드를 그대로 여기에 붙여넣으세요)
    def __init__(self, screen_shot):
        self.image = screen_shot
        self.point1 = None
        self.point2 = None
        self.rect_done = False

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.point1 = (x, y)
            self.rect_done = False
        elif event == cv2.EVENT_MOUSEMOVE and self.point1:
            img_copy = self.image.copy()
            cv2.rectangle(img_copy, self.point1, (x, y), (0, 255, 0), 2)
            cv2.imshow("Area Selector", img_copy)
        elif event == cv2.EVENT_LBUTTONUP:
            self.point2 = (x, y)
            self.rect_done = True

    def select_area(self, instructions):
        self.point1 = None
        self.point2 = None
        self.rect_done = False
        # cv2.WINDOW_NORMAL을 사용하면 창 크기 조절이 가능해짐
        cv2.namedWindow("Area Selector", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Area Selector", self.mouse_callback)
        img_with_text = self.image.copy()
        cv2.putText(img_with_text, instructions, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Area Selector", img_with_text)
        while not self.rect_done:
            if cv2.waitKey(1) & 0xFF == 27:
                cv2.destroyAllWindows()
                return None
        cv2.destroyAllWindows()
        left = min(self.point1[0], self.point2[0])
        top = min(self.point1[1], self.point2[1])
        width = abs(self.point1[0] - self.point2[0])
        height = abs(self.point1[1] - self.point2[1])
        return {'top': top, 'left': left, 'width': width, 'height': height}

# --- 프로그램 실행 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ScoreCaptureApp(root)
    root.mainloop()