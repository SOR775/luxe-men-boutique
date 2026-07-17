"""
Seed script for mens_boutique.
Populates Category, Brand, Collection, Product, ProductVariant, ProductImage,
Warehouse, Stock, StockMovement, plus a sample customer, wishlist item, and reviews.

Images are pulled from the Pexels API using real, descriptive search phrases
(e.g. "navy tuxedo jacket man") rather than single loose tags, so photos
actually resemble the product they're attached to.

Usage (from your project root, with venv activated):
    python seed_data.py

Requires:
    pip install requests
    A PEXELS_API_KEY in your environment (get one free at pexels.com/api)
"""

import os
import uuid
import hashlib
import secrets
import django
import requests
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model

from products.models import (
    Category, Brand, Collection, Product, ProductVariant, ProductImage,
    WishlistItem, ProductReview,
)
from inventory.models import Warehouse, Stock, StockMovement

User = get_user_model()


# ---------------------------------------------------------------------------
# Pexels image helper
# ---------------------------------------------------------------------------
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
PEXELS_SEARCH_URL = 'https://api.pexels.com/v1/search'

if not PEXELS_API_KEY:
    raise RuntimeError(
        "PEXELS_API_KEY is not set. Add it to your .env file "
        "(and make sure your settings module loads it, e.g. via "
        "python-dotenv or django-environ) before running this script."
    )

PEXELS_HEADERS = {'Authorization': PEXELS_API_KEY}

# In-memory cache so identical queries (e.g. two products reusing a brand
# lookup) don't burn extra API calls in a single run.
_search_cache: dict[str, list[dict]] = {}


def fetch_image(query: str, seed: str, width: int = 900, height: int = 1200) -> ContentFile | None:
    """
    Search Pexels for a real, relevant photo and return it as a ContentFile.

    `query` should be a natural-language search phrase, e.g.
    "navy tuxedo jacket man" or "leather brogue shoes" — specific phrases
    return far more relevant results than single comma-joined tags.

    `seed` determines which result gets picked (deterministically, so
    re-running the script gives the same image each time) and becomes
    the saved filename.
    """
    try:
        if query in _search_cache:
            results = _search_cache[query]
        else:
            resp = requests.get(
                PEXELS_SEARCH_URL,
                headers=PEXELS_HEADERS,
                params={'query': query, 'per_page': 6, 'orientation': 'portrait'},
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get('photos', [])
            _search_cache[query] = results

        if not results:
            print(f"  [warn] no Pexels results for '{query}' (seed: {seed})")
            return None

        # deterministic pick based on seed, so re-runs are stable but
        # different products/variants don't all get the exact same photo
        idx = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(results)
        photo = results[idx]
        photo_url = photo['src']['large']  # ~940px wide, good for product pages

        img_resp = requests.get(photo_url, timeout=20)
        img_resp.raise_for_status()

        if len(img_resp.content) < 2000:
            print(f"  [warn] image for seed '{seed}' looked too small/broken, skipping")
            return None

        return ContentFile(img_resp.content, name=f"{seed}.jpg")
    except requests.RequestException as e:
        print(f"  [warn] could not fetch image for '{query}' (seed: {seed}): {e}")
        return None


def seed():
    # -----------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------
    print("Creating superuser...")
    admin_email = os.environ.get('SEED_ADMIN_EMAIL', 'admin@luxemen.com')
    admin_password = os.environ.get('SEED_ADMIN_PASSWORD')
    if not User.objects.filter(email=admin_email).exists():
        if not admin_password:
            if os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('.prod'):
                # Never auto-create an admin account in production without an
                # explicit, operator-supplied password.
                print("  [skip] SEED_ADMIN_PASSWORD not set — skipping superuser creation in production.")
                admin_password = None
            else:
                admin_password = secrets.token_urlsafe(12)
                print(f"  [dev only] Generated random admin password: {admin_password}")
        if admin_password:
            User.objects.create_superuser(
                email=admin_email, username='admin', password=admin_password,
                first_name='Admin', last_name='User'
            )
            print(f"  Superuser created: {admin_email} (password not logged)")

    print("Creating sample customers...")
    customers = []
    for first, last, email in [
        ('John', 'Customer', 'john.customer@example.com'),
        ('Michael', 'Otieno', 'michael.otieno@example.com'),
        ('David', 'Kariuki', 'david.kariuki@example.com'),
    ]:
        username = email.split('@')[0]
        customer, created = User.objects.get_or_create(
            email=email,
            defaults={'first_name': first, 'last_name': last, 'username': username},
        )
        if created:
            if os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('.prod'):
                demo_password = secrets.token_urlsafe(12)
                print(f"  Customer created: {email} (random password, not logged)")
            else:
                demo_password = 'customer123'
                print(f"  Customer created: {email} / customer123 [dev only]")
            customer.set_password(demo_password)
            customer.save()
        customers.append(customer)
    primary_customer = customers[0]

    # -----------------------------------------------------------------
    # Brands
    # image_query = natural-language phrase for the brand's logo/hero shot
    # -----------------------------------------------------------------
    print("Creating brands...")
    brand_data = [
        {'name': 'Corneliani', 'description': 'Italian luxury tailoring since 1958.',
         'image_query': 'tailor fitting suit fabric'},
        {'name': 'Crockett & Jones', 'description': 'English shoemakers, Northampton since 1879.',
         'image_query': 'leather shoemaker workshop'},
        {'name': "Drake's", 'description': 'London-based menswear and accessories house.',
         'image_query': 'menswear necktie flat lay'},
        {'name': 'Loro Piana', 'description': 'Italian house renowned for rare, luxurious fabrics.',
         'image_query': 'cashmere wool fabric texture'},
        {'name': "Church's", 'description': 'Heritage English footwear, handcrafted since 1873.',
         'image_query': 'oxford leather shoes closeup'},
        {'name': 'Turnbull & Asser', 'description': 'Jermyn Street shirtmakers to royalty since 1885.',
         'image_query': 'white dress shirt cotton'},
        {'name': 'Barbour', 'description': 'British heritage outerwear, famed for waxed cotton jackets.',
         'image_query': 'waxed cotton jacket countryside'},
    ]
    brands = {}
    for b in brand_data:
        brand, created = Brand.objects.get_or_create(name=b['name'], defaults={'description': b['description']})
        if created:
            logo = fetch_image(b['image_query'], f"brand-{brand.slug}", 400, 400)
            if logo:
                brand.logo.save(logo.name, logo, save=True)
        brands[b['name']] = brand

    # -----------------------------------------------------------------
    # Collections
    # -----------------------------------------------------------------
    print("Creating collections...")
    collection_data = [
        {
            'name': 'Autumn 2026',
            'description': 'Rich textures and tailored silhouettes for the new season.',
            'start_date': '2026-09-01',
            'end_date': '2026-11-30',
            'image_query': 'autumn menswear street style',
        },
        {
            'name': 'Winter Essentials 2026',
            'description': 'Cold-weather staples built to last — knitwear, outerwear, and boots.',
            'start_date': '2026-12-01',
            'end_date': '2027-02-28',
            'image_query': 'man winter coat snow',
        },
        {
            'name': 'Spring Formal 2027',
            'description': 'Lightweight tailoring for weddings, events, and warm-weather occasions.',
            'start_date': '2027-03-01',
            'end_date': '2027-05-31',
            'image_query': 'man linen suit wedding outdoor',
        },
    ]
    collections = {}
    for c in collection_data:
        collection, created = Collection.objects.get_or_create(
            name=c['name'],
            defaults={
                'description': c['description'],
                'start_date': c['start_date'],
                'end_date': c['end_date'],
            },
        )
        if created:
            img = fetch_image(c['image_query'], f"collection-{collection.slug}", 1200, 600)
            if img:
                collection.image.save(img.name, img, save=True)
        collections[c['name']] = collection

    # -----------------------------------------------------------------
    # Categories
    # -----------------------------------------------------------------
    print("Creating categories...")
    cat_data = [
        {'name': 'Suits', 'description': 'Tailored suits for every occasion.',
         'image_query': "men's suit tailored"},
        {'name': 'Shoes', 'description': 'Handcrafted formal and casual footwear.',
         'image_query': "men's leather dress shoes"},
        {'name': 'Shirts', 'description': 'Dress and casual shirts.',
         'image_query': "men's dress shirt"},
        {'name': 'Accessories', 'description': 'Ties, belts, cufflinks and more.',
         'image_query': "men's tie and accessories flat lay"},
        {'name': 'Outerwear', 'description': 'Coats, jackets, and blazers for every season.',
         'image_query': "men's coat jacket"},
        {'name': 'Knitwear', 'description': 'Sweaters, cardigans, and cashmere knits.',
         'image_query': "men's sweater knitwear"},
        {'name': 'Trousers', 'description': 'Tailored and casual trousers.',
         'image_query': "men's tailored trousers"},
        {'name': 'Watches', 'description': "Men's dress and sport watches.",
         'image_query': "men's dress watch wrist"},
    ]
    categories = {}
    for c in cat_data:
        cat, created = Category.objects.get_or_create(name=c['name'], defaults={'description': c['description']})
        if created:
            img = fetch_image(c['image_query'], f"category-{cat.slug}", 800, 500)
            if img:
                cat.image.save(img.name, img, save=True)
        categories[c['name']] = cat

    # -----------------------------------------------------------------
    # Warehouse
    # -----------------------------------------------------------------
    print("Creating warehouse(s)...")
    warehouse, _ = Warehouse.objects.get_or_create(
        name='Main Warehouse',
        defaults={'address': 'Industrial Area, Nairobi, Kenya'},
    )
    warehouse_mombasa, _ = Warehouse.objects.get_or_create(
        name='Mombasa Depot',
        defaults={'address': 'Port Reitz Road, Mombasa, Kenya'},
    )

    # -----------------------------------------------------------------
    # Products (full field set)
    # image_query = natural-language search phrase for this product's photos
    # -----------------------------------------------------------------
    print("Creating products...")

    product_defs = [
        {
            'name': 'Midnight Blue Tuxedo',
            'category': categories['Suits'],
            'brand': brands['Corneliani'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('5.00'),
            'compare_at_price': Decimal('5.00'),
            'description': (
                'Premium Italian wool tuxedo with satin peak lapels, tailored '
                'for a sharp, modern silhouette. Fully canvassed construction '
                'ensures the jacket moves naturally and holds its shape for years.'
            ),
            'meta_title': 'Midnight Blue Tuxedo | Corneliani',
            'meta_description': 'Shop the Midnight Blue Tuxedo — Italian wool, satin lapels, fully canvassed.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man navy blue tuxedo suit',
            'variants': [
                {'sku': 'TUX-MB-40R', 'size': '40R', 'color': 'Midnight Blue', 'material': 'Italian Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.40'), 'qty': 6},
                {'sku': 'TUX-MB-42R', 'size': '42R', 'color': 'Midnight Blue', 'material': 'Italian Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.45'), 'qty': 10},
                {'sku': 'TUX-MB-44R', 'size': '44R', 'color': 'Midnight Blue', 'material': 'Italian Wool',
                 'price_adjustment': Decimal('1500.00'), 'weight': Decimal('1.50'), 'qty': 4},
            ],
        },
        {
            'name': 'Charcoal Two-Piece Suit',
            'category': categories['Suits'],
            'brand': brands['Corneliani'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('5.00'),
            'compare_at_price': None,
            'description': (
                'A versatile charcoal grey suit cut from a durable wool-blend '
                'twill, equally at home in the boardroom or at evening events.'
            ),
            'meta_title': 'Charcoal Two-Piece Suit | Corneliani',
            'meta_description': 'Charcoal grey wool-blend suit for business and formal wear.',
            'is_featured': True,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man charcoal grey suit business',
            'variants': [
                {'sku': 'SUT-CH-38R', 'size': '38R', 'color': 'Charcoal', 'material': 'Wool Blend',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.35'), 'qty': 8},
                {'sku': 'SUT-CH-40R', 'size': '40R', 'color': 'Charcoal', 'material': 'Wool Blend',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.40'), 'qty': 12},
                {'sku': 'SUT-CH-42L', 'size': '42L', 'color': 'Charcoal', 'material': 'Wool Blend',
                 'price_adjustment': Decimal('800.00'), 'weight': Decimal('1.45'), 'qty': 5},
            ],
        },
        {
            'name': 'Beige Linen Suit',
            'category': categories['Suits'],
            'brand': brands['Corneliani'],
            'collection': collections['Spring Formal 2027'],
            'base_price': Decimal('5.00'),
            'compare_at_price': None,
            'description': (
                'Breathable Irish linen suit in a warm beige tone, unstructured '
                'shoulder for a relaxed drape — built for destination weddings '
                'and warm-weather events.'
            ),
            'meta_title': 'Beige Linen Suit | Corneliani',
            'meta_description': 'Lightweight Irish linen suit for warm-weather occasions.',
            'is_featured': False,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man beige linen suit summer',
            'variants': [
                {'sku': 'SUT-LN-40R', 'size': '40R', 'color': 'Beige', 'material': 'Irish Linen',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.10'), 'qty': 9},
                {'sku': 'SUT-LN-42R', 'size': '42R', 'color': 'Beige', 'material': 'Irish Linen',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.15'), 'qty': 7},
            ],
        },
        {
            'name': 'Oxford Leather Brogues',
            'category': categories['Shoes'],
            'brand': brands['Crockett & Jones'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('15000.00'),
            'compare_at_price': None,
            'description': (
                'Handcrafted calfskin leather brogues with a Goodyear-welted sole, '
                'built in Northampton using techniques passed down for generations.'
            ),
            'meta_title': 'Oxford Leather Brogues | Crockett & Jones',
            'meta_description': 'Handcrafted calfskin brogues with Goodyear-welted soles.',
            'is_featured': False,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'brown leather brogue shoes',
            'variants': [
                {'sku': 'SHO-OX-42', 'size': '42', 'color': 'Tan', 'material': 'Calfskin Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.90'), 'qty': 8},
                {'sku': 'SHO-OX-44', 'size': '44', 'color': 'Tan', 'material': 'Calfskin Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.95'), 'qty': 15},
                {'sku': 'SHO-OX-44-BLK', 'size': '44', 'color': 'Black', 'material': 'Calfskin Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.95'), 'qty': 12},
            ],
        },
        {
            'name': "Chelsea Boots",
            'category': categories['Shoes'],
            'brand': brands["Church's"],
            'collection': collections['Winter Essentials 2026'],
            'base_price': Decimal('18500.00'),
            'compare_at_price': Decimal('21000.00'),
            'description': (
                'Classic elastic-sided Chelsea boots in black calf leather, '
                'finished with a leather sole and stacked heel.'
            ),
            'meta_title': "Chelsea Boots | Church's",
            'meta_description': 'Black calf leather Chelsea boots with leather sole.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'black leather chelsea boots',
            'variants': [
                {'sku': 'BOO-CH-41', 'size': '41', 'color': 'Black', 'material': 'Calf Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.00'), 'qty': 6},
                {'sku': 'BOO-CH-43', 'size': '43', 'color': 'Black', 'material': 'Calf Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.05'), 'qty': 10},
            ],
        },
        {
            'name': 'Classic White Dress Shirt',
            'category': categories['Shirts'],
            'brand': brands["Drake's"],
            'collection': None,
            'base_price': Decimal('6500.00'),
            'compare_at_price': Decimal('7800.00'),
            'description': (
                'A wardrobe essential — 100% Egyptian cotton dress shirt with a '
                'spread collar and mother-of-pearl buttons.'
            ),
            'meta_title': "Classic White Dress Shirt | Drake's",
            'meta_description': 'Egyptian cotton dress shirt with spread collar.',
            'is_featured': True,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man white dress shirt',
            'variants': [
                {'sku': 'SHT-WH-S', 'size': 'S', 'color': 'White', 'material': 'Egyptian Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.30'), 'qty': 20},
                {'sku': 'SHT-WH-M', 'size': 'M', 'color': 'White', 'material': 'Egyptian Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.32'), 'qty': 25},
                {'sku': 'SHT-WH-L', 'size': 'L', 'color': 'White', 'material': 'Egyptian Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.34'), 'qty': 18},
            ],
        },
        {
            'name': 'Sky Blue Oxford Shirt',
            'category': categories['Shirts'],
            'brand': brands['Turnbull & Asser'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('7200.00'),
            'compare_at_price': None,
            'description': (
                'Soft-woven Oxford cotton shirt in sky blue, button-down collar, '
                'ideal for smart-casual wear on its own or under a blazer.'
            ),
            'meta_title': 'Sky Blue Oxford Shirt | Turnbull & Asser',
            'meta_description': 'Sky blue Oxford cotton shirt with button-down collar.',
            'is_featured': False,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man light blue oxford shirt',
            'variants': [
                {'sku': 'SHT-SB-M', 'size': 'M', 'color': 'Sky Blue', 'material': 'Oxford Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.31'), 'qty': 16},
                {'sku': 'SHT-SB-L', 'size': 'L', 'color': 'Sky Blue', 'material': 'Oxford Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.33'), 'qty': 14},
                {'sku': 'SHT-SB-XL', 'size': 'XL', 'color': 'Sky Blue', 'material': 'Oxford Cotton',
                 'price_adjustment': Decimal('300.00'), 'weight': Decimal('0.35'), 'qty': 9},
            ],
        },
        {
            'name': 'Silk Woven Tie',
            'category': categories['Accessories'],
            'brand': brands["Drake's"],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('4200.00'),
            'compare_at_price': None,
            'description': (
                'A finely woven silk tie in a subtle houndstooth pattern, '
                'hand-finished in a classic 8cm width.'
            ),
            'meta_title': "Silk Woven Tie | Drake's",
            'meta_description': 'Hand-finished silk tie in houndstooth.',
            'is_featured': False,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'silk necktie flat lay',
            'variants': [
                {'sku': 'TIE-HT-NVY', 'size': '', 'color': 'Navy', 'material': 'Silk',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.08'), 'qty': 30},
                {'sku': 'TIE-HT-BUR', 'size': '', 'color': 'Burgundy', 'material': 'Silk',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.08'), 'qty': 22},
            ],
        },
        {
            'name': 'Full-Grain Leather Belt',
            'category': categories['Accessories'],
            'brand': brands["Church's"],
            'collection': None,
            'base_price': Decimal('5800.00'),
            'compare_at_price': None,
            'description': (
                'Hand-stitched full-grain leather belt with a solid brass buckle, '
                'built to age gracefully with wear.'
            ),
            'meta_title': "Full-Grain Leather Belt | Church's",
            'meta_description': 'Hand-stitched leather belt with brass buckle.',
            'is_featured': False,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'brown leather belt buckle',
            'variants': [
                {'sku': 'BLT-BR-34', 'size': '34', 'color': 'Brown', 'material': 'Full-Grain Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.25'), 'qty': 20},
                {'sku': 'BLT-BR-36', 'size': '36', 'color': 'Brown', 'material': 'Full-Grain Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.26'), 'qty': 18},
                {'sku': 'BLT-BK-36', 'size': '36', 'color': 'Black', 'material': 'Full-Grain Leather',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.26'), 'qty': 18},
            ],
        },
        {
            'name': 'Waxed Cotton Field Jacket',
            'category': categories['Outerwear'],
            'brand': brands['Barbour'],
            'collection': collections['Winter Essentials 2026'],
            'base_price': Decimal('100.00'),
            'compare_at_price': Decimal('50.00'),
            'description': (
                'Weatherproof waxed cotton jacket with a corduroy collar and '
                'tartan lining — a British countryside classic built for decades '
                'of use and re-waxing.'
            ),
            'meta_title': 'Waxed Cotton Field Jacket | Barbour',
            'meta_description': 'Weatherproof waxed cotton jacket with tartan lining.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man olive green field jacket',
            'variants': [
                {'sku': 'JKT-WX-M', 'size': 'M', 'color': 'Olive', 'material': 'Waxed Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.20'), 'qty': 10},
                {'sku': 'JKT-WX-L', 'size': 'L', 'color': 'Olive', 'material': 'Waxed Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.25'), 'qty': 12},
                {'sku': 'JKT-WX-XL', 'size': 'XL', 'color': 'Olive', 'material': 'Waxed Cotton',
                 'price_adjustment': Decimal('500.00'), 'weight': Decimal('1.30'), 'qty': 6},
            ],
        },
        {
            'name': 'Camel Wool Overcoat',
            'category': categories['Outerwear'],
            'brand': brands['Loro Piana'],
            'collection': collections['Winter Essentials 2026'],
            'base_price': Decimal('68000.00'),
            'compare_at_price': None,
            'description': (
                'Single-breasted overcoat in luxurious camel wool, cut for a '
                'clean, elongated line — the ultimate cold-weather layering piece.'
            ),
            'meta_title': 'Camel Wool Overcoat | Loro Piana',
            'meta_description': 'Single-breasted camel wool overcoat.',
            'is_featured': True,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man camel wool overcoat',
            'variants': [
                {'sku': 'COT-CM-40R', 'size': '40R', 'color': 'Camel', 'material': 'Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.80'), 'qty': 4},
                {'sku': 'COT-CM-42R', 'size': '42R', 'color': 'Camel', 'material': 'Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('1.85'), 'qty': 5},
            ],
        },
        {
            'name': 'Cashmere Crew Neck Sweater',
            'category': categories['Knitwear'],
            'brand': brands['Loro Piana'],
            'collection': collections['Winter Essentials 2026'],
            'base_price': Decimal('200.00'),
            'compare_at_price': Decimal('100.00'),
            'description': (
                'Two-ply cashmere crew neck sweater, spun from fine highland '
                'fibers for exceptional softness and warmth without bulk.'
            ),
            'meta_title': 'Cashmere Crew Neck Sweater | Loro Piana',
            'meta_description': 'Two-ply cashmere crew neck sweater.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man grey cashmere sweater',
            'variants': [
                {'sku': 'SWT-CS-M-GRY', 'size': 'M', 'color': 'Grey', 'material': 'Cashmere',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.45'), 'qty': 11},
                {'sku': 'SWT-CS-L-GRY', 'size': 'L', 'color': 'Grey', 'material': 'Cashmere',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.48'), 'qty': 9},
                {'sku': 'SWT-CS-M-NVY', 'size': 'M', 'color': 'Navy', 'material': 'Cashmere',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.45'), 'qty': 8},
            ],
        },
        {
            'name': 'Merino Wool Half-Zip',
            'category': categories['Knitwear'],
            'brand': brands['Corneliani'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('14500.00'),
            'compare_at_price': None,
            'description': (
                'Fine-gauge merino wool half-zip sweater, breathable and '
                'temperature-regulating — layers cleanly under a blazer.'
            ),
            'meta_title': 'Merino Wool Half-Zip | Corneliani',
            'meta_description': 'Merino wool half-zip sweater.',
            'is_featured': False,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man green half zip sweater',
            'variants': [
                {'sku': 'SWT-MW-M', 'size': 'M', 'color': 'Bottle Green', 'material': 'Merino Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.40'), 'qty': 13},
                {'sku': 'SWT-MW-L', 'size': 'L', 'color': 'Bottle Green', 'material': 'Merino Wool',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.42'), 'qty': 10},
            ],
        },
        {
            'name': 'Tailored Wool Trousers',
            'category': categories['Trousers'],
            'brand': brands['Corneliani'],
            'collection': collections['Autumn 2026'],
            'base_price': Decimal('12500.00'),
            'compare_at_price': None,
            'description': (
                'Flat-front tailored trousers in a fine wool twill, finished '
                'with a clean break and a comfortable half-lined waistband.'
            ),
            'meta_title': 'Tailored Wool Trousers | Corneliani',
            'meta_description': 'Flat-front tailored wool trousers.',
            'is_featured': False,
            'is_trending': False,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man charcoal wool trousers',
            'variants': [
                {'sku': 'TRS-WL-32', 'size': '32', 'color': 'Charcoal', 'material': 'Wool Twill',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.60'), 'qty': 14},
                {'sku': 'TRS-WL-34', 'size': '34', 'color': 'Charcoal', 'material': 'Wool Twill',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.62'), 'qty': 16},
                {'sku': 'TRS-WL-36', 'size': '36', 'color': 'Charcoal', 'material': 'Wool Twill',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.64'), 'qty': 10},
            ],
        },
        {
            'name': 'Cotton Chinos',
            'category': categories['Trousers'],
            'brand': brands["Drake's"],
            'collection': None,
            'base_price': Decimal('800.00'),
            'compare_at_price': Decimal('900.00'),
            'description': (
                'Garment-dyed cotton chinos with a slim straight leg — a smart-'
                'casual staple that pairs with everything from a blazer to a tee.'
            ),
            'meta_title': "Cotton Chinos | Drake's",
            'meta_description': 'Garment-dyed cotton chinos, slim straight leg.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'man khaki chino pants',
            'variants': [
                {'sku': 'CHN-KH-30', 'size': '30', 'color': 'Khaki', 'material': 'Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.50'), 'qty': 18},
                {'sku': 'CHN-KH-32', 'size': '32', 'color': 'Khaki', 'material': 'Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.52'), 'qty': 22},
                {'sku': 'CHN-NV-32', 'size': '32', 'color': 'Navy', 'material': 'Cotton',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.52'), 'qty': 20},
            ],
        },
        {
            'name': 'Automatic Dress Watch',
            'category': categories['Watches'],
            'brand': brands['Corneliani'],
            'collection': collections['Spring Formal 2027'],
            'base_price': Decimal('54000.00'),
            'compare_at_price': None,
            'description': (
                'Slim automatic dress watch with a sunburst dial, sapphire '
                'crystal, and a hand-stitched calfskin strap — understated '
                'enough for a suit, sharp enough to notice.'
            ),
            'meta_title': 'Automatic Dress Watch | Corneliani',
            'meta_description': 'Slim automatic dress watch with calfskin strap.',
            'is_featured': True,
            'is_trending': True,
            'visibility': Product.Visibility.PUBLISHED,
            'image_query': 'men automatic dress watch closeup',
            'variants': [
                {'sku': 'WCH-DR-SLV', 'size': '', 'color': 'Silver/Brown Strap', 'material': 'Stainless Steel',
                 'price_adjustment': Decimal('0.00'), 'weight': Decimal('0.12'), 'qty': 5},
                {'sku': 'WCH-DR-GLD', 'size': '', 'color': 'Gold/Black Strap', 'material': 'Stainless Steel',
                 'price_adjustment': Decimal('4000.00'), 'weight': Decimal('0.13'), 'qty': 3},
            ],
        },
    ]

    all_products = []

    for pdef in product_defs:
        product, created = Product.objects.get_or_create(
            name=pdef['name'],
            defaults={
                'category': pdef['category'],
                'brand': pdef['brand'],
                'collection': pdef['collection'],
                'base_price': pdef['base_price'],
                'compare_at_price': pdef['compare_at_price'],
                'description': pdef['description'],
                'meta_title': pdef['meta_title'],
                'meta_description': pdef['meta_description'],
                'is_featured': pdef['is_featured'],
                'is_trending': pdef['is_trending'],
                'visibility': pdef['visibility'],
            },
        )
        all_products.append(product)

        if not created:
            print(f"  Skipping '{product.name}' (already exists)")
            continue

        print(f"  Created product: {product.name}")

        base_query = pdef['image_query']

        # ---- Variants + Stock + StockMovement ----
        # Alternate warehouses so stock isn't all piled in one place.
        for i, vdef in enumerate(pdef['variants']):
            variant = ProductVariant.objects.create(
                product=product,
                sku=vdef['sku'],
                barcode=f"BC{uuid.uuid4().hex[:10].upper()}",
                size=vdef['size'],
                color=vdef['color'],
                material=vdef['material'],
                price_adjustment=vdef['price_adjustment'],
                weight=vdef['weight'],
                length=Decimal('30.00'),
                width=Decimal('20.00'),
                height=Decimal('10.00'),
                is_active=True,
            )

            wh = warehouse if i % 2 == 0 else warehouse_mombasa
            stock, _ = Stock.objects.get_or_create(
                variant=variant,
                warehouse=wh,
                defaults={'low_stock_threshold': 5},
            )
            StockMovement.objects.create(
                stock=stock,
                movement_type=StockMovement.MovementType.PURCHASE,
                quantity=vdef['qty'],
                reference='Initial Stock',
                notes='Seeded initial inventory.',
            )

            # ---- Variant-specific image (first variant only, to save requests) ----
            # Append the color into the query so a "Black" variant searches
            # differently from a "Tan" one of the same product.
            if i == 0:
                variant_query = f"{base_query} {vdef['color']}" if vdef['color'] else base_query
                img = fetch_image(variant_query, f"{variant.sku}", 900, 1200)
                if img:
                    ProductImage.objects.create(
                        product=product,
                        variant=variant,
                        image=img,
                        alt_text=f"{product.name} - {variant.color}",
                        is_primary=False,
                        order=1,
                    )

        # ---- General product images (2 per product, first marked primary) ----
        for i in range(2):
            img = fetch_image(base_query, f"{product.slug}-{i}", 900, 1200)
            if img:
                ProductImage.objects.create(
                    product=product,
                    image=img,
                    alt_text=f"{product.name} view {i + 1}",
                    is_primary=(i == 0),
                    order=i,
                )

    # -----------------------------------------------------------------
    # Wishlist + Reviews (sample customers interacting with products)
    # -----------------------------------------------------------------
    print("Creating wishlist items and reviews...")

    review_seed = [
        ('Midnight Blue Tuxedo', 5, 'Impeccable fit and finish — worth every shilling.'),
        ('Oxford Leather Brogues', 5, 'These only get better looking with age. True Goodyear welt.'),
        ('Waxed Cotton Field Jacket', 4, 'Great jacket, runs slightly large — size down if in doubt.'),
        ('Cashmere Crew Neck Sweater', 5, 'Softest sweater I own. Worth the splurge.'),
        ('Cotton Chinos', 4, 'Good everyday chino, fit is true to size.'),
        ('Automatic Dress Watch', 5, 'Understated and elegant, keeps great time.'),
    ]

    by_name = {p.name: p for p in all_products}
    for idx, (pname, rating, comment) in enumerate(review_seed):
        product = by_name.get(pname)
        if not product:
            continue
        reviewer = customers[idx % len(customers)]
        WishlistItem.objects.get_or_create(user=reviewer, product=product)
        ProductReview.objects.get_or_create(
            user=reviewer,
            product=product,
            defaults={'rating': rating, 'comment': comment},
        )

    print("Database seeded successfully!")


if __name__ == '__main__':
    seed()