"""Initialize database schema + seed data."""
import asyncio
import shutil
import os
from pathlib import Path
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from database import Base
from models import User, Shop, Table, Category, Product
from auth import hash_password
from config import DATABASE_URL

SEED_CATEGORIES = [
    {"name": "Alfajores", "icon": "cupcake", "sort_order": 1},
    {"name": "Empanadas", "icon": "sandwich", "sort_order": 2},
    {"name": "Pastries and Facturas", "icon": "croissant", "sort_order": 3},
    {"name": "Boxes and Assortments", "icon": "box", "sort_order": 4},
]

SEED_PRODUCTS = [
    {"c": "Alfajores", "n": "Alfajores de maicena", "s": "alfajores-de-maicena", "p": 12.90},
    {"c": "Alfajores", "n": "Banana split alfajor", "s": "banana-split-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Classic alfajor", "s": "classic-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Dulce de leche and almond alfajor", "s": "dulce-de-leche-almond-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Dulce de leche and walnuts alfajor", "s": "dulce-de-leche-walnuts-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Mango and passion fruit alfajor", "s": "mango-passion-fruit-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Meringue surprise alfajor", "s": "meringue-surprise-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Peanut and dulce de leche alfajor", "s": "peanut-dulce-de-leche-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Pistachio alfajor", "s": "pistachio-alfajor", "p": 12.90},
    {"c": "Alfajores", "n": "Raspberry madness alfajor", "s": "raspberry-madness-alfajor", "p": 11.25},
    {"c": "Alfajores", "n": "Strawberry cheesecake alfajor", "s": "raspberry-madness-alfajor-copy", "p": 11.25},
    {"c": "Empanadas", "n": "Caprese empanadas", "s": "caprese-empanada", "p": 24.50},
    {"c": "Empanadas", "n": "Cheeseburger empanadas", "s": "cheeseburger-empanadas", "p": 24.50},
    {"c": "Empanadas", "n": "Spicy meat empanadas", "s": "copy-of-empanada-carne-x6", "p": 24.50},
    {"c": "Empanadas", "n": "Chorizo and cheese empanadas", "s": "empanada-chorizo-queso", "p": 24.50},
    {"c": "Empanadas", "n": "Meat empanadas", "s": "empanada-de-carne", "p": 24.50},
    {"c": "Empanadas", "n": "Spinach and cheese empanadas", "s": "empanada-espinaca", "p": 24.50},
    {"c": "Empanadas", "n": "Corn and cheese empanadas", "s": "empanada-humita", "p": 24.50},
    {"c": "Empanadas", "n": "Spicy chicken empanadas", "s": "empanada-pollo-picante", "p": 24.50},
    {"c": "Empanadas", "n": "Onion and cheese empanadas", "s": "empanada-queso-cebolla", "p": 24.50},
    {"c": "Empanadas", "n": "Four cheese empanadas", "s": "empanadas-de-cuatro-queso", "p": 24.50},
    {"c": "Empanadas", "n": "Chicken empanadas", "s": "empanadas-de-pollo", "p": 24.50},
    {"c": "Empanadas", "n": "Ham and cheese empanadas", "s": "ham-cheese", "p": 24.50},
    {"c": "Empanadas", "n": "Tuna empanadas", "s": "tuna-empanadas", "p": 24.50},
    {"c": "Empanadas", "n": "Vegan empanadas", "s": "vegan-empanadas-x6", "p": 24.50},
    {"c": "Pastries and Facturas", "n": "Bake off medialunas de manteca", "s": "bake-off-medialunas-de-manteca", "p": 13.90},
    {"c": "Pastries and Facturas", "n": "Canoncitos de dulce de leche", "s": "canoncitos-de-dulce-de-leche", "p": 3.75},
    {"c": "Pastries and Facturas", "n": "Churrinche", "s": "churrinche", "p": 2.50},
    {"c": "Pastries and Facturas", "n": "Cremona", "s": "cremona-1", "p": 8.50},
    {"c": "Pastries and Facturas", "n": "Chipa x12", "s": "cremona-copy", "p": 11.90},
    {"c": "Pastries and Facturas", "n": "Medialuna con dulce de leche", "s": "medialuna-con-dulce-de-leche", "p": 3.50},
    {"c": "Pastries and Facturas", "n": "Medialunas de grasa", "s": "medialunas-de-grasa", "p": 2.50},
    {"c": "Pastries and Facturas", "n": "Monito de grasa con dulce de leche", "s": "monito-de-grasa-con-dulce-de-leche", "p": 4.50},
    {"c": "Pastries and Facturas", "n": "Pionono", "s": "pepas", "p": 4.50},
    {"c": "Pastries and Facturas", "n": "Facturas de grasa", "s": "pionono", "p": 4.25},
    {"c": "Pastries and Facturas", "n": "Tortitas negras", "s": "tortitas-negras", "p": 3.25},
    {"c": "Pastries and Facturas", "n": "Vigilante", "s": "vigilante", "p": 3.00},
    {"c": "Boxes and Assortments", "n": "Alfajores tasting box", "s": "alfajores-tasting-box-limited-edition", "p": 32.90},
    {"c": "Boxes and Assortments", "n": "Best seller empanadas assortment x12", "s": "best-seller-empanadas-assortment-x12", "p": 47.90},
    {"c": "Boxes and Assortments", "n": "Classic empanadas assortment x12", "s": "empanadas-mixed-box", "p": 47.90},
    {"c": "Boxes and Assortments", "n": "HBD alfajores box!", "s": "happy-birthday-box-1", "p": 34.50},
    {"c": "Boxes and Assortments", "n": "Alfajores Pick box", "s": "pickbox", "p": 32.90},
]


async def init_database():
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS tab_tracker"))
        await conn.run_sync(Base.metadata.create_all)
        print("Schema + tables created")

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT count(*) FROM tab_tracker.users"))
        if result.scalar() > 0:
            print("Already seeded, skipping")
            await engine.dispose()
            return

    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("tab123"),
            display_name="Bakery Admin",
            is_admin=True,
        )
        session.add(admin)

        cashier = User(
            username="cashier",
            password_hash=hash_password("tab123"),
            display_name="Cashier",
            is_admin=False,
        )
        session.add(cashier)
        await session.flush()
        print("Users: admin, cashier (password: tab123)")

        shop = Shop(name="ABC Shop (with tables)", has_tables=True)
        session.add(shop)
        await session.flush()

        for i in range(1, 13):
            table = Table(shop_id=shop.id, name=f"T{i}", seats=4, sort_order=i)
            session.add(table)
        print("12 tables created (T1-T12)")

        cat_map = {}
        for cat_data in SEED_CATEGORIES:
            cat = Category(**cat_data)
            session.add(cat)
            await session.flush()
            cat_map[cat_data["name"]] = cat.id
        print(f"{len(SEED_CATEGORIES)} categories created")

        img_dir = Path(__file__).parent / "static" / "images" / "products"
        img_dir.mkdir(parents=True, exist_ok=True)

        product_count = 0
        for prod in SEED_PRODUCTS:
            slug = prod["s"]
            image_path = None
            for ext in ['.jpg', '.png', '.webp']:
                src = f"/tmp/abc_images/{slug}{ext}"
                if os.path.exists(src):
                    dst = img_dir / f"{slug}{ext}"
                    shutil.copy2(src, dst)
                    image_path = f"/images/products/{slug}{ext}"
                    break

            product = Product(
                category_id=cat_map[prod["c"]],
                name=prod["n"],
                slug=slug,
                price=Decimal(str(prod["p"])),
                image_path=image_path,
                is_active=True,
                sort_order=product_count,
            )
            session.add(product)
            product_count += 1

        print(f"{product_count} products created")
        await session.commit()
        print("Seed complete!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
