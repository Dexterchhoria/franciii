from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import hashlib
import secrets
import razorpay
from passlib.context import CryptContext
import jwt
from uuid import uuid4
from contextlib import asynccontextmanager


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-here')
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_dummy_key')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'dummy_secret_key')

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Create the main app
# app = FastAPI(title="Francium E-commerce API")
api_router = APIRouter(prefix="/api")


# === MODELS ===
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    password_hash: str
    full_name: str
    role: str = "customer"  # customer or admin
    phone: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int = 0

class CartItem(BaseModel):
    product_id: str
    quantity: int
    price: float

class Cart(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    items: List[CartItem] = []
    total: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    items: List[CartItem]
    total: float
    payment_status: str = "pending"  # pending, paid, failed
    order_status: str = "placed"  # placed, processing, shipped, delivered
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    shipping_address: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class RazorpayOrder(BaseModel):
    amount: int  # in paise
    currency: str = "INR"

class AddToCart(BaseModel):
    product_id: str
    quantity: int = 1

class CreateOrder(BaseModel):
    shipping_address: str

# === AUTHENTICATION ===
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_doc = await db.users.find_one({"id": user_id})
        if user_doc is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        return User(**user_doc)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# === AUTH ROUTES ===
@api_router.post("/auth/register")
async def register_user(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
        address=user_data.address
    )
    
    await db.users.insert_one(user.dict())
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@api_router.post("/auth/login")
async def login_user(user_data: UserLogin):
    user_doc = await db.users.find_one({"email": user_data.email})
    if not user_doc or not verify_password(user_data.password, user_doc["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    user = User(**user_doc)
    access_token = create_access_token(data={"sub": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }

# === PRODUCT ROUTES ===
@api_router.get("/products", response_model=List[Product])
async def get_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    skip: int = 0
):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    products = await db.products.find(query).skip(skip).limit(limit).to_list(limit)
    return [Product(**product) for product in products]

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product_doc = await db.products.find_one({"id": product_id})
    if not product_doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**product_doc)

@api_router.post("/products", response_model=Product)
async def create_product(product_data: ProductCreate, admin_user: User = Depends(get_admin_user)):
    product = Product(**product_data.dict())
    await db.products.insert_one(product.dict())
    return product

@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, product_data: ProductCreate, admin_user: User = Depends(get_admin_user)):
    update_data = product_data.dict()
    update_data["updated_at"] = datetime.utcnow()
    
    result = await db.products.update_one(
        {"id": product_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    
    updated_product = await db.products.find_one({"id": product_id})
    return Product(**updated_product)

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, admin_user: User = Depends(get_admin_user)):
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted successfully"}

# === CART ROUTES ===
@api_router.get("/cart", response_model=Cart)
async def get_cart(current_user: User = Depends(get_current_user)):
    cart_doc = await db.carts.find_one({"user_id": current_user.id})
    if not cart_doc:
        # Create empty cart
        cart = Cart(user_id=current_user.id)
        await db.carts.insert_one(cart.dict())
        return cart
    return Cart(**cart_doc)

@api_router.post("/cart/add")
async def add_to_cart(item: AddToCart, current_user: User = Depends(get_current_user)):
    # Get product
    product_doc = await db.products.find_one({"id": item.product_id})
    if not product_doc:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = Product(**product_doc)
    
    # Get or create cart
    cart_doc = await db.carts.find_one({"user_id": current_user.id})
    if not cart_doc:
        cart = Cart(user_id=current_user.id)
    else:
        cart = Cart(**cart_doc)
    
    # Add or update item in cart
    existing_item = None
    for cart_item in cart.items:
        if cart_item.product_id == item.product_id:
            existing_item = cart_item
            break
    
    if existing_item:
        existing_item.quantity += item.quantity
    else:
        cart_item = CartItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=product.price
        )
        cart.items.append(cart_item)
    
    # Calculate total
    cart.total = sum(item.quantity * item.price for item in cart.items)
    cart.updated_at = datetime.utcnow()
    
    # Update in database
    await db.carts.replace_one(
        {"user_id": current_user.id},
        cart.dict(),
        upsert=True
    )
    
    return {"message": "Item added to cart", "cart": cart}

@api_router.delete("/cart/remove/{product_id}")
async def remove_from_cart(product_id: str, current_user: User = Depends(get_current_user)):
    cart_doc = await db.carts.find_one({"user_id": current_user.id})
    if not cart_doc:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    cart = Cart(**cart_doc)
    cart.items = [item for item in cart.items if item.product_id != product_id]
    cart.total = sum(item.quantity * item.price for item in cart.items)
    cart.updated_at = datetime.utcnow()
    
    await db.carts.replace_one({"user_id": current_user.id}, cart.dict())
    return {"message": "Item removed from cart", "cart": cart}

# === ORDER ROUTES ===
@api_router.post("/orders/create")
async def create_order(order_data: CreateOrder, current_user: User = Depends(get_current_user)):
    # Get user's cart
    cart_doc = await db.carts.find_one({"user_id": current_user.id})
    if not cart_doc or not cart_doc.get("items"):
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    cart = Cart(**cart_doc)
    
    # Create Razorpay order
    razorpay_order = razorpay_client.order.create({
        "amount": int(cart.total * 100),  # Convert to paise
        "currency": "INR",
        "payment_capture": 1
    })
    
    # Create order in database
    order = Order(
        user_id=current_user.id,
        items=cart.items,
        total=cart.total,
        razorpay_order_id=razorpay_order["id"],
        shipping_address=order_data.shipping_address
    )
    
    await db.orders.insert_one(order.dict())
    
    # Clear cart
    await db.carts.update_one(
        {"user_id": current_user.id},
        {"$set": {"items": [], "total": 0.0, "updated_at": datetime.utcnow()}}
    )
    
    return {
        "order_id": order.id,
        "razorpay_order_id": razorpay_order["id"],
        "amount": razorpay_order["amount"],
        "currency": razorpay_order["currency"],
        "key": RAZORPAY_KEY_ID
    }

@api_router.post("/orders/verify-payment")
async def verify_payment(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    
    # Verify payment signature
    razorpay_order_id = body.get("razorpay_order_id")
    razorpay_payment_id = body.get("razorpay_payment_id")
    razorpay_signature = body.get("razorpay_signature")
    
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        
        # Update order status
        await db.orders.update_one(
            {"razorpay_order_id": razorpay_order_id, "user_id": current_user.id},
            {"$set": {
                "payment_status": "paid",
                "razorpay_payment_id": razorpay_payment_id,
                "order_status": "processing"
            }}
        )
        
        return {"status": "success", "message": "Payment verified successfully"}
        
    except Exception as e:
        return {"status": "failure", "message": "Payment verification failed"}

@api_router.get("/orders", response_model=List[Order])
async def get_user_orders(current_user: User = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": current_user.id}).sort("created_at", -1).to_list(100)
    return [Order(**order) for order in orders]

@api_router.get("/admin/orders", response_model=List[Order])
async def get_all_orders(admin_user: User = Depends(get_admin_user)):
    orders = await db.orders.find().sort("created_at", -1).to_list(100)
    return [Order(**order) for order in orders]

# === ADMIN ROUTES ===
@api_router.get("/admin/stats")
async def get_admin_stats(admin_user: User = Depends(get_admin_user)):
    total_products = await db.products.count_documents({})
    total_orders = await db.orders.count_documents({})
    total_users = await db.users.count_documents({"role": "customer"})
    
    # Calculate total revenue
    orders = await db.orders.find({"payment_status": "paid"}).to_list(1000)
    total_revenue = sum(order.get("total", 0) for order in orders)
    
    return {
        "total_products": total_products,
        "total_orders": total_orders,
        "total_users": total_users,
        "total_revenue": total_revenue
    }

# === CATEGORIES ===
@api_router.get("/categories")
async def get_categories():
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    categories = await db.products.aggregate(pipeline).to_list(100)
    return [{"name": cat["_id"], "count": cat["count"]} for cat in categories]


# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# @app.on_event("shutdown")
# async def shutdown_db_client():
#     client.close()

# # Initialize sample data on startup
# @app.on_event("startup")
# async def initialize_data():
#     # Create admin user if doesn't exist
#     admin_exists = await db.users.find_one({"email": "admin@francium.com"})
#     if not admin_exists:
#         admin_user = User(
#             email="admin@francium.com",
#             password_hash=hash_password("admin123"),
#             full_name="Admin User",
#             role="admin"
#         )
#         await db.users.insert_one(admin_user.dict())
#         logger.info("Admin user created: admin@francium.com / admin123")
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code

    # Create admin user if not exists
    admin_exists = await db.users.find_one({"email": "admin@francium.com"})
    if not admin_exists:
        admin_user = User(
            email="admin@francium.com",
            password_hash=hash_password("admin123"),
            full_name="Admin User",
            role="admin"
        )
        await db.users.insert_one(admin_user.dict())
        logger.info("Admin user created: admin@francium.com / admin123")
 
    # Create sample products if none exist
    product_count = await db.products.count_documents({})
    if product_count == 0:
        sample_products = [
            Product(
                name="Wireless Bluetooth Headphones",
                description="Premium wireless headphones with noise cancellation and 24-hour battery life",
                price=2999.00,
                category="Electronics",
                image_url="https://images.unsplash.com/photo-1573164574230-db1d5e960238?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwzfHxlY29tbWVyY2V8ZW58MHx8fGJsdWV8MTc1MzM1MjIxN3ww&ixlib=rb-4.1.0&q=85",
                stock=50
            ),
            Product(
                name="Smart Watch Pro",
                description="Advanced fitness tracking smartwatch with heart rate monitor and GPS",
                price=4999.00,
                category="Electronics",
                image_url="https://images.unsplash.com/photo-1615833843615-884a03a10642?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwyfHxlY29tbWVyY2V8ZW58MHx8fGJsdWV8MTc1MzM1MjIxN3ww&ixlib=rb-4.1.0&q=85",
                stock=30
            ),
            Product(
                name="Premium Blue Shirt",
                description="High-quality cotton shirt perfect for formal and casual occasions",
                price=1299.00,
                category="Fashion",
                image_url="https://images.unsplash.com/photo-1589810635657-232948472d98?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Njl8MHwxfHNlYXJjaHwyfHxzaG9wcGluZ3xlbnwwfHx8Ymx1ZXwxNzUzMzUyMjI1fDA&ixlib=rb-4.1.0&q=85",
                stock=100
            ),
            Product(
                name="Leather Laptop Bag",
                description="Stylish and durable leather laptop bag for professionals",
                price=3499.00,
                category="Accessories",
                image_url="https://images.unsplash.com/photo-1647221597996-54f3d0f73809?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwxfHxlY29tbWVyY2V8ZW58MHx8fGJsdWV8MTc1MzM1MjIxN3ww&ixlib=rb-4.1.0&q=85",
                stock=25
            ),
            Product(
                name="Designer Glasses",
                description="Trendy designer glasses with UV protection and lightweight frame",
                price=1899.00,
                category="Accessories",
                image_url="https://images.unsplash.com/photo-1615833843615-884a03a10642?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwyfHxlY29tbWVyY2V8ZW58MHx8fGJsdWV8MTc1MzM1MjIxN3ww&ixlib=rb-4.1.0&q=85",
                stock=40
            ),
            Product(
                name="Yoga Mat Premium",
                description="High-density yoga mat with excellent grip and cushioning",
                price=899.00,
                category="Sports",
                image_url="https://images.unsplash.com/photo-1530735038726-a73fd6e6a349?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Njl8MHwxfHNlYXJjaHwxfHxzaG9wcGluZ3xlbnwwfHx8Ymx1ZXwxNzUzMzUyMjI1fDA&ixlib=rb-4.1.0&q=85",
                stock=60
            )
        ]
        
        for product in sample_products:
            await db.products.insert_one(product.dict())
        
        logger.info(f"Created {len(sample_products)} sample products")
    yield  # Application runs here
    client.close()
app = FastAPI(title="Francium E-commerce API", lifespan=lifespan)

# Include router
app.include_router(api_router)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
