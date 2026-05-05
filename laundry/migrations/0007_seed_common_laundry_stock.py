from django.db import migrations


COMMON_CATEGORIES = [
    ("Detergents & Chemicals", "Laundry detergents, conditioners, and cleaning chemicals."),
    ("Packaging & Customer Supplies", "Items used for packing and returning customer laundry."),
    ("Machine & Utility Supplies", "Supplies used for daily laundry machine operations."),
]

COMMON_ITEMS = [
    {
        "name": "Laundry Detergent",
        "category": "Detergents & Chemicals",
        "unit": "L",
        "current_stock": 10,
        "minimum_stock": 3,
        "unit_cost": 120,
    },
    {
        "name": "Fabric Conditioner",
        "category": "Detergents & Chemicals",
        "unit": "L",
        "current_stock": 8,
        "minimum_stock": 2,
        "unit_cost": 110,
    },
    {
        "name": "Color-Safe Bleach",
        "category": "Detergents & Chemicals",
        "unit": "L",
        "current_stock": 5,
        "minimum_stock": 2,
        "unit_cost": 95,
    },
    {
        "name": "Stain Remover",
        "category": "Detergents & Chemicals",
        "unit": "bottles",
        "current_stock": 6,
        "minimum_stock": 2,
        "unit_cost": 85,
    },
    {
        "name": "Disinfectant",
        "category": "Detergents & Chemicals",
        "unit": "L",
        "current_stock": 4,
        "minimum_stock": 1,
        "unit_cost": 140,
    },
    {
        "name": "Laundry Plastic Bags",
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 100,
        "minimum_stock": 30,
        "unit_cost": 2,
    },
    {
        "name": "Customer Tags",
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 100,
        "minimum_stock": 25,
        "unit_cost": 1,
    },
    {
        "name": "Hangers",
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 50,
        "minimum_stock": 15,
        "unit_cost": 5,
    },
    {
        "name": "Dryer Sheets",
        "category": "Machine & Utility Supplies",
        "unit": "boxes",
        "current_stock": 3,
        "minimum_stock": 1,
        "unit_cost": 160,
    },
]


def seed_common_laundry_stock(apps, schema_editor):
    InventoryCategory = apps.get_model("laundry", "InventoryCategory")
    InventoryItem = apps.get_model("laundry", "InventoryItem")

    categories = {}
    for name, description in COMMON_CATEGORIES:
        category, created = InventoryCategory.objects.get_or_create(
            name=name,
            defaults={"description": description},
        )
        if not created and not category.description:
            category.description = description
            category.save(update_fields=["description"])
        categories[name] = category

    for item in COMMON_ITEMS:
        InventoryItem.objects.get_or_create(
            name=item["name"],
            defaults={
                "category": categories[item["category"]],
                "unit": item["unit"],
                "current_stock": item["current_stock"],
                "minimum_stock": item["minimum_stock"],
                "unit_cost": item["unit_cost"],
                "is_active": True,
            },
        )


def unseed_common_laundry_stock(apps, schema_editor):
    InventoryItem = apps.get_model("laundry", "InventoryItem")
    InventoryCategory = apps.get_model("laundry", "InventoryCategory")

    InventoryItem.objects.filter(
        name__in=[item["name"] for item in COMMON_ITEMS],
    ).delete()
    InventoryCategory.objects.filter(
        name__in=[name for name, _description in COMMON_CATEGORIES],
        items__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("laundry", "0006_inventorycategory_inventoryitem_stockmovement"),
    ]

    operations = [
        migrations.RunPython(seed_common_laundry_stock, unseed_common_laundry_stock),
    ]
