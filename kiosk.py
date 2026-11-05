"""카페 키오스크 (tkinter, 외부 패키지 불필요)

실행:
    python kiosk.py              # 전체 화면
    python kiosk.py --windowed   # 창 모드 (개발/테스트용)

관리자 종료: Ctrl+Shift+Q → PIN 입력
주문 내역: orders.jsonl 에 한 줄씩 저장됩니다.
"""
import argparse
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import simpledialog

# ---------------------------------------------------------------- 설정
ADMIN_PIN = "0000"
MAX_QUANTITY = 5          # 메뉴 하나당 최대 수량
IDLE_SECONDS = 60         # 무입력 시 첫 화면으로 복귀
DONE_SECONDS = 6          # 주문 완료 화면 유지 시간
ORDER_FILE = Path(__file__).with_name("orders.jsonl")

MENU = {
    "americano": {"name": "아메리카노", "price": 3000, "category": "커피", "sold_out": False},
    "latte": {"name": "카페라떼", "price": 3500, "category": "커피", "sold_out": False},
    "vanilla_latte": {"name": "바닐라라떼", "price": 4000, "category": "커피", "sold_out": False},
    "cappuccino": {"name": "카푸치노", "price": 3500, "category": "커피", "sold_out": True},
    "green_tea": {"name": "녹차라떼", "price": 4000, "category": "음료", "sold_out": False},
    "lemonade": {"name": "레몬에이드", "price": 4500, "category": "음료", "sold_out": False},
    "choco": {"name": "초코라떼", "price": 4000, "category": "음료", "sold_out": False},
    "muffin": {"name": "초코머핀", "price": 2500, "category": "디저트", "sold_out": False},
    "cookie": {"name": "쿠키", "price": 2000, "category": "디저트", "sold_out": False},
    "cake": {"name": "치즈케이크", "price": 5500, "category": "디저트", "sold_out": False},
}
CATEGORIES = ["커피", "음료", "디저트"]

# ---------------------------------------------------------------- 스타일
FONT = "Malgun Gothic"
BG = "#f6f1ea"
BROWN = "#4a2f1d"
ACCENT = "#c8782a"
CARD = "#ffffff"
GRAY = "#9b9b9b"
GREEN = "#2f8f5b"
RED = "#c0392b"


def won(n):
    return f"{n:,}원"


def font(size, bold=False):
    return (FONT, size, "bold" if bold else "normal")


def big_button(parent, text, command, bg=ACCENT, fg="white", size=20, **kw):
    return tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg, font=font(size, True),
        activebackground=bg, activeforeground=fg, relief="flat", bd=0,
        cursor="hand2", **kw,
    )


class Kiosk(tk.Tk):
    def __init__(self, windowed=False):
        super().__init__()
        self.title("카페 키오스크")
        self.configure(bg=BG)
        if windowed:
            self.geometry("1100x760")
        else:
            self.attributes("-fullscreen", True)

        self.cart = {}              # menu_id -> 수량
        self.dine_in = True
        self.category = CATEGORIES[0]
        self.idle_job = None
        self.done_job = None
        self.paying = False

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.screens = {}
        for name, build in (
            ("welcome", self.build_welcome),
            ("order", self.build_order),
            ("pay", self.build_pay),
            ("done", self.build_done),
        ):
            frame = tk.Frame(self.container, bg=BG)
            frame.grid(row=0, column=0, sticky="nsew")
            build(frame)
            self.screens[name] = frame

        self.bind_all("<ButtonPress>", lambda e: self.reset_idle())
        self.bind_all("<KeyPress>", lambda e: self.reset_idle())
        self.bind_all("<Control-Shift-Q>", lambda e: self.admin_exit())
        self.bind_all("<Control-Shift-q>", lambda e: self.admin_exit())

        self.show("welcome")

    # ------------------------------------------------------------ 공통
    def show(self, name):
        self.screens[name].tkraise()
        self.current = name
        self.reset_idle()

    def reset_idle(self):
        if self.idle_job:
            self.after_cancel(self.idle_job)
            self.idle_job = None
        if getattr(self, "current", "welcome") in ("order", "pay"):
            self.idle_job = self.after(IDLE_SECONDS * 1000, self.go_home)

    def go_home(self):
        if self.paying:             # 결제 처리 중에는 초기화하지 않음
            return
        self.cart.clear()
        self.category = CATEGORIES[0]
        self.show("welcome")

    def admin_exit(self):
        pin = simpledialog.askstring("관리자", "PIN 번호를 입력하세요", show="*", parent=self)
        if pin == ADMIN_PIN:
            self.destroy()

    # ------------------------------------------------------------ 1. 시작 화면
    def build_welcome(self, f):
        tk.Label(f, text="☕ CAFE", font=font(64, True), bg=BG, fg=BROWN).pack(pady=(120, 10))
        tk.Label(f, text="주문 방법을 선택해주세요", font=font(26), bg=BG, fg=GRAY).pack(pady=(0, 60))
        row = tk.Frame(f, bg=BG)
        row.pack()
        big_button(row, "매장에서 먹고 가기", lambda: self.start_order(True),
                   size=26, width=16, height=4).pack(side="left", padx=20)
        big_button(row, "포장해서 가기", lambda: self.start_order(False),
                   bg=BROWN, size=26, width=16, height=4).pack(side="left", padx=20)

    def start_order(self, dine_in):
        self.dine_in = dine_in
        self.cart.clear()
        self.render_menu()
        self.render_cart()
        self.show("order")

    # ------------------------------------------------------------ 2. 주문 화면
    def build_order(self, f):
        header = tk.Frame(f, bg=BROWN)
        header.pack(fill="x")
        tk.Label(header, text="메뉴를 선택해주세요", font=font(24, True),
                 bg=BROWN, fg="white").pack(side="left", padx=24, pady=16)
        tk.Button(header, text="처음으로", command=self.go_home, font=font(14, True),
                  bg=BROWN, fg="white", relief="flat", bd=0,
                  activebackground=BROWN, activeforeground="white",
                  cursor="hand2").pack(side="right", padx=24)

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2, minsize=380)
        body.grid_rowconfigure(0, weight=1)

        # 왼쪽: 카테고리 + 메뉴
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=12)
        self.tab_bar = tk.Frame(left, bg=BG)
        self.tab_bar.pack(fill="x")
        self.menu_grid = tk.Frame(left, bg=BG)
        self.menu_grid.pack(fill="both", expand=True, pady=(12, 0))
        for c in range(3):
            self.menu_grid.grid_columnconfigure(c, weight=1, uniform="col")

        # 오른쪽: 장바구니
        right = tk.Frame(body, bg=CARD)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=12)
        tk.Label(right, text="주문 내역", font=font(20, True), bg=CARD, fg=BROWN).pack(
            anchor="w", padx=16, pady=(14, 6))
        self.cart_frame = tk.Frame(right, bg=CARD)
        self.cart_frame.pack(fill="both", expand=True, padx=12)

        bottom = tk.Frame(right, bg=CARD)
        bottom.pack(fill="x", padx=16, pady=14)
        self.total_label = tk.Label(bottom, text="합계 0원", font=font(22, True),
                                    bg=CARD, fg=BROWN)
        self.total_label.pack(anchor="e", pady=(0, 10))
        btns = tk.Frame(bottom, bg=CARD)
        btns.pack(fill="x")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=2)
        big_button(btns, "전체 삭제", self.clear_cart, bg=GRAY, size=16, height=2).grid(
            row=0, column=0, sticky="ew", padx=(0, 6))
        self.pay_btn = big_button(btns, "결제하기", self.go_pay, size=16, height=2)
        self.pay_btn.grid(row=0, column=1, sticky="ew")

    def render_menu(self):
        for w in self.tab_bar.winfo_children():
            w.destroy()
        for cat in CATEGORIES:
            active = cat == self.category
            tk.Button(
                self.tab_bar, text=cat, font=font(18, True),
                bg=ACCENT if active else CARD, fg="white" if active else BROWN,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", bd=0, padx=26, pady=10, cursor="hand2",
                command=lambda c=cat: self.select_category(c),
            ).pack(side="left", padx=(0, 8))

        for w in self.menu_grid.winfo_children():
            w.destroy()
        items = [(k, v) for k, v in MENU.items() if v["category"] == self.category]
        for i, (menu_id, info) in enumerate(items):
            r, c = divmod(i, 3)
            sold = info["sold_out"]
            text = f"{info['name']}\n\n{'품절' if sold else won(info['price'])}"
            tk.Button(
                self.menu_grid, text=text, font=font(18, True),
                bg="#e4e0da" if sold else CARD, fg=GRAY if sold else BROWN,
                activebackground=CARD, relief="flat", bd=0,
                cursor="arrow" if sold else "hand2",
                state="disabled" if sold else "normal",
                disabledforeground=GRAY,
                command=lambda m=menu_id: self.add_item(m),
            ).grid(row=r, column=c, sticky="nsew", padx=6, pady=6, ipady=22)
        for r in range((len(items) + 2) // 3):
            self.menu_grid.grid_rowconfigure(r, weight=0)

    def select_category(self, cat):
        self.category = cat
        self.render_menu()

    # --- 장바구니
    def add_item(self, menu_id):
        if MENU[menu_id]["sold_out"]:
            return
        if self.cart.get(menu_id, 0) >= MAX_QUANTITY:
            self.flash(f"메뉴당 최대 {MAX_QUANTITY}개까지 주문할 수 있어요")
            return
        self.cart[menu_id] = self.cart.get(menu_id, 0) + 1
        self.render_cart()

    def change_qty(self, menu_id, delta):
        qty = self.cart.get(menu_id, 0) + delta
        if qty > MAX_QUANTITY:
            self.flash(f"메뉴당 최대 {MAX_QUANTITY}개까지 주문할 수 있어요")
            return
        if qty <= 0:
            self.cart.pop(menu_id, None)
        else:
            self.cart[menu_id] = qty
        self.render_cart()

    def clear_cart(self):
        self.cart.clear()
        self.render_cart()

    def total(self):
        return sum(MENU[m]["price"] * q for m, q in self.cart.items())

    def render_cart(self):
        for w in self.cart_frame.winfo_children():
            w.destroy()
        if not self.cart:
            tk.Label(self.cart_frame, text="메뉴를 눌러\n담아주세요", font=font(16),
                     bg=CARD, fg=GRAY).pack(expand=True)
        for menu_id, qty in self.cart.items():
            info = MENU[menu_id]
            row = tk.Frame(self.cart_frame, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=info["name"], font=font(15, True), bg=CARD, fg=BROWN,
                     anchor="w").grid(row=0, column=0, sticky="w")
            tk.Label(row, text=won(info["price"] * qty), font=font(14), bg=CARD, fg=BROWN,
                     anchor="e").grid(row=0, column=1, sticky="e")
            row.grid_columnconfigure(0, weight=1)
            ctrl = tk.Frame(row, bg=CARD)
            ctrl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
            for text, delta in (("−", -1), ("+", 1)):
                if delta == 1:
                    tk.Label(ctrl, text=str(qty), font=font(15, True), bg=CARD, width=3).pack(side="left")
                tk.Button(ctrl, text=text, font=font(15, True), width=3, bg="#ece7e0",
                          relief="flat", bd=0, cursor="hand2",
                          command=lambda m=menu_id, d=delta: self.change_qty(m, d)).pack(side="left")
        self.total_label.config(text=f"합계 {won(self.total())}")
        self.pay_btn.config(state="normal" if self.cart else "disabled",
                            bg=ACCENT if self.cart else GRAY)

    def flash(self, message):
        label = tk.Label(self, text=message, font=font(16, True), bg=BROWN, fg="white",
                         padx=24, pady=12)
        label.place(relx=0.5, rely=0.92, anchor="center")
        self.after(1800, label.destroy)

    # ------------------------------------------------------------ 3. 결제 화면
    def build_pay(self, f):
        tk.Label(f, text="결제 방법을 선택해주세요", font=font(30, True), bg=BG, fg=BROWN).pack(pady=(70, 10))
        self.pay_summary = tk.Label(f, text="", font=font(18), bg=BG, fg=GRAY, justify="center")
        self.pay_summary.pack(pady=10)
        self.pay_total = tk.Label(f, text="", font=font(34, True), bg=BG, fg=ACCENT)
        self.pay_total.pack(pady=(0, 40))
        row = tk.Frame(f, bg=BG)
        row.pack()
        self.card_btn = big_button(row, "💳 카드 결제", lambda: self.pay("카드"),
                                   size=24, width=14, height=3)
        self.card_btn.pack(side="left", padx=16)
        self.cash_btn = big_button(row, "💵 현금 결제", lambda: self.pay("현금"),
                                   bg=BROWN, size=24, width=14, height=3)
        self.cash_btn.pack(side="left", padx=16)
        self.pay_status = tk.Label(f, text="", font=font(20, True), bg=BG, fg=GREEN)
        self.pay_status.pack(pady=30)
        self.back_btn = big_button(f, "← 주문으로 돌아가기", lambda: self.show("order"),
                                   bg=GRAY, size=16, width=20, height=1)
        self.back_btn.pack()

    def go_pay(self):
        if not self.cart:
            return
        lines = [f"{MENU[m]['name']} × {q}" for m, q in self.cart.items()]
        self.pay_summary.config(text="\n".join(lines))
        self.pay_total.config(text=f"총 {won(self.total())}")
        self.pay_status.config(text="", fg=GREEN)
        self.set_pay_buttons(True)
        self.show("pay")

    def set_pay_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        for b in (self.card_btn, self.cash_btn, self.back_btn):
            b.config(state=state)

    def pay(self, method):
        if self.paying:
            return
        self.paying = True
        self.set_pay_buttons(False)
        self.pay_status.config(
            text="카드를 투입구에 넣어주세요..." if method == "카드" else "카운터에서 결제해주세요...",
            fg=GREEN)
        # 실제 단말기 연동 시 이 부분을 process_payment()로 교체하세요.
        self.after(2000, lambda: self.finish_payment(method))

    def finish_payment(self, method):
        self.paying = False
        ok = self.process_payment(method, self.total())
        if not ok:
            self.pay_status.config(text="결제에 실패했어요. 다시 시도해주세요.", fg=RED)
            self.set_pay_buttons(True)
            return
        number = self.save_order(method)
        self.done_number.config(text=f"주문번호  {number}")
        self.done_info.config(text=f"{'매장' if self.dine_in else '포장'} · {method} · {won(self.total())}")
        self.cart.clear()
        self.show("done")
        self.done_job = self.after(DONE_SECONDS * 1000, self.finish_done)

    @staticmethod
    def process_payment(method, amount):
        """결제 단말기/PG 연동 지점. 지금은 항상 성공으로 처리합니다."""
        return True

    def save_order(self, method):
        today = datetime.now().strftime("%Y-%m-%d")
        number = 1
        if ORDER_FILE.exists():
            for line in ORDER_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line)["time"].startswith(today):
                        number += 1
                except (ValueError, KeyError):
                    continue
        record = {
            "number": number,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "매장" if self.dine_in else "포장",
            "payment": method,
            "items": [{"name": MENU[m]["name"], "qty": q, "price": MENU[m]["price"]}
                      for m, q in self.cart.items()],
            "total": self.total(),
        }
        with ORDER_FILE.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        return number

    # ------------------------------------------------------------ 4. 완료 화면
    def build_done(self, f):
        tk.Label(f, text="✔", font=font(80, True), bg=BG, fg=GREEN).pack(pady=(110, 0))
        tk.Label(f, text="주문이 완료되었습니다", font=font(32, True), bg=BG, fg=BROWN).pack(pady=10)
        self.done_number = tk.Label(f, text="", font=font(54, True), bg=BG, fg=ACCENT)
        self.done_number.pack(pady=20)
        self.done_info = tk.Label(f, text="", font=font(18), bg=BG, fg=GRAY)
        self.done_info.pack()
        tk.Label(f, text="번호가 호출되면 카운터에서 받아가세요", font=font(18),
                 bg=BG, fg=BROWN).pack(pady=30)
        big_button(f, "확인", self.finish_done, size=18, width=12).pack()

    def finish_done(self):
        if self.done_job:
            self.after_cancel(self.done_job)
            self.done_job = None
        self.go_home()


def main():
    parser = argparse.ArgumentParser(description="카페 키오스크")
    parser.add_argument("--windowed", action="store_true", help="전체 화면 대신 창 모드로 실행")
    args = parser.parse_args()
    Kiosk(windowed=args.windowed).mainloop()


if __name__ == "__main__":
    main()
