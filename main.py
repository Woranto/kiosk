"""카페 키오스크 웹 서버 (FastAPI)

실행:
    .venv\\Scripts\\python.exe -m uvicorn main:app --reload
브라우저: http://127.0.0.1:8000        (API 문서: /docs)

주문 내역은 MongoDB(.env 의 MONGODB_URI) 의 orders 컬렉션에 저장됩니다.
관리자 API(주문 조회, 품절 처리)는 X-Admin-Pin 헤더가 필요합니다.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
ADMIN_PIN = "0000"
MAX_QUANTITY = 5
CATEGORIES = ["커피", "음료", "디저트"]

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

app = FastAPI(title="카페 키오스크")

# MongoClient는 연결을 처음 사용할 때 맺는다. 접속 정보는 .env 의 MONGODB_URI 에서 읽는다.
mongo = MongoClient(os.environ.get("MONGODB_URI", ""), serverSelectionTimeoutMS=5000)
db = mongo[os.environ.get("MONGODB_DB", "kiosk")]
orders_col = db["orders"]
counters_col = db["counters"]


def next_order_number(day: str) -> int:
    """날짜별 주문번호를 원자적으로 발급한다 (동시 주문에도 중복 없음)."""
    doc = counters_col.find_one_and_update(
        {"_id": f"order-{day}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


class OrderItem(BaseModel):
    menu_id: str
    quantity: int = Field(ge=1)


class OrderRequest(BaseModel):
    dine_in: bool
    payment: Literal["카드", "현금"]
    items: list[OrderItem] = Field(min_length=1)


class SoldOutRequest(BaseModel):
    sold_out: bool


def require_admin(pin: str | None):
    if pin != ADMIN_PIN:
        raise HTTPException(status_code=401, detail="관리자 PIN이 올바르지 않습니다.")


@app.get("/api/menu")
def get_menu():
    return {
        "max_quantity": MAX_QUANTITY,
        "categories": CATEGORIES,
        "items": [{"id": menu_id, **info} for menu_id, info in MENU.items()],
    }


@app.post("/api/orders", status_code=201)
def create_order(req: OrderRequest):
    # 같은 메뉴가 여러 번 들어와도 수량을 합쳐서 검증한다.
    quantities: dict[str, int] = {}
    for item in req.items:
        quantities[item.menu_id] = quantities.get(item.menu_id, 0) + item.quantity

    lines = []
    for menu_id, qty in quantities.items():
        info = MENU.get(menu_id)
        if info is None:
            raise HTTPException(status_code=404, detail=f"없는 메뉴입니다: {menu_id}")
        if info["sold_out"]:
            raise HTTPException(status_code=409, detail=f"품절된 메뉴입니다: {info['name']}")
        if qty > MAX_QUANTITY:
            raise HTTPException(
                status_code=400,
                detail=f"{info['name']}은(는) 최대 {MAX_QUANTITY}개까지 주문할 수 있습니다.",
            )
        lines.append({"name": info["name"], "quantity": qty, "price": info["price"]})

    now = datetime.now()
    try:
        order = {
            "number": next_order_number(now.strftime("%Y-%m-%d")),
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "매장" if req.dine_in else "포장",
            "payment": req.payment,
            "items": lines,
            # 금액은 항상 서버에서 계산한다 (클라이언트가 보낸 금액은 믿지 않는다).
            "total": sum(l["price"] * l["quantity"] for l in lines),
        }
        orders_col.insert_one(dict(order))   # insert_one 이 _id 를 덧붙이므로 복사본을 넣는다
    except PyMongoError:
        raise HTTPException(status_code=503, detail="주문을 저장하지 못했습니다. 잠시 후 다시 시도해주세요.")
    return order


@app.get("/api/orders")
def list_orders(x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    try:
        return list(orders_col.find({}, {"_id": 0}).sort("time", -1).limit(200))
    except PyMongoError:
        raise HTTPException(status_code=503, detail="DB에 연결할 수 없습니다.")


@app.patch("/api/menu/{menu_id}/sold-out")
def set_sold_out(menu_id: str, body: SoldOutRequest, x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    if menu_id not in MENU:
        raise HTTPException(status_code=404, detail="없는 메뉴입니다.")
    MENU[menu_id]["sold_out"] = body.sold_out
    return {"id": menu_id, **MENU[menu_id]}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
