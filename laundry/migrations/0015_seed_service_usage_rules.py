from django.db import migrations


CATEGORIES = {
    "Detergents & Chemicals": "Laundry detergents, conditioners, and cleaning chemicals.",
    "Packaging & Customer Supplies": "Items used for packing and returning customer laundry.",
    "Machine & Utility Supplies": "Supplies used for daily laundry machine operations.",
}

ITEM_DEFAULTS = {
    "Laundry Detergent": {
        "category": "Detergents & Chemicals",
        "unit": "ml",
        "current_stock": 10000,
        "minimum_stock": 3000,
        "unit_cost": 0.12,
    },
    "Fabric Conditioner": {
        "category": "Detergents & Chemicals",
        "unit": "ml",
        "current_stock": 8000,
        "minimum_stock": 2000,
        "unit_cost": 0.11,
    },
    "Color-Safe Bleach": {
        "category": "Detergents & Chemicals",
        "unit": "ml",
        "current_stock": 5000,
        "minimum_stock": 2000,
        "unit_cost": 0.095,
    },
    "Disinfectant": {
        "category": "Detergents & Chemicals",
        "unit": "ml",
        "current_stock": 4000,
        "minimum_stock": 1000,
        "unit_cost": 0.14,
    },
    "Laundry Plastic Bags": {
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 100,
        "minimum_stock": 30,
        "unit_cost": 2,
    },
    "Customer Tags": {
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 100,
        "minimum_stock": 25,
        "unit_cost": 1,
    },
    "Dryer Sheets": {
        "category": "Machine & Utility Supplies",
        "unit": "pcs",
        "current_stock": 300,
        "minimum_stock": 100,
        "unit_cost": 1.6,
    },
    "Hangers": {
        "category": "Packaging & Customer Supplies",
        "unit": "pcs",
        "current_stock": 50,
        "minimum_stock": 15,
        "unit_cost": 5,
    },
}

SERVICE_USAGE_RULES = [
    ("WASH_DRY_FOLD", "Laundry Detergent", 30, 0),
    ("WASH_DRY_FOLD", "Fabric Conditioner", 15, 0),
    ("WASH_DRY_FOLD", "Color-Safe Bleach", 10, 0),
    ("WASH_DRY_FOLD", "Disinfectant", 5, 0),
    ("WASH_DRY_FOLD", "Laundry Plastic Bags", 0, 1),
    ("WASH_DRY_FOLD", "Customer Tags", 0, 1),
    ("WASH_DRY_FOLD", "Dryer Sheets", 0, 1),
    ("WASH_DRY", "Laundry Detergent", 30, 0),
    ("WASH_DRY", "Fabric Conditioner", 15, 0),
    ("WASH_DRY", "Laundry Plastic Bags", 0, 1),
    ("WASH_DRY", "Customer Tags", 0, 1),
    ("WASH", "Laundry Detergent", 30, 0),
    ("WASH", "Fabric Conditioner", 15, 0),
    ("WASH", "Customer Tags", 0, 1),
    ("DRY_ONLY", "Dryer Sheets", 0, 1),
    ("DRY_ONLY", "Customer Tags", 0, 1),
    ("IRON", "Customer Tags", 0, 1),
    ("IRON", "Hangers", 0, 2),
    ("EXPRESS", "Laundry Detergent", 30, 0),
]


def convert_seeded_item_units(item, target_unit):
    update_fields = []

    if target_unit == "ml" and item.unit == "L":
        item.current_stock = item.current_stock * 1000
        item.minimum_stock = item.minimum_stock * 1000
        if item.unit_cost:
            item.unit_cost = item.unit_cost / 1000
        update_fields += ["current_stock", "minimum_stock", "unit_cost"]

    if target_unit == "pcs" and item.name == "Dryer Sheets" and item.unit == "boxes":
        item.current_stock = item.current_stock * 100
        item.minimum_stock = item.minimum_stock * 100
        if item.unit_cost:
            item.unit_cost = item.unit_cost / 100
        update_fields += ["current_stock", "minimum_stock", "unit_cost"]

    if item.unit != target_unit:
        item.unit = target_unit
        update_fields.append("unit")

    if update_fields:
        item.save(update_fields=list(dict.fromkeys(update_fields)))


def seed_service_usage_rules(apps, schema_editor):
    InventoryCategory = apps.get_model("laundry", "InventoryCategory")
    InventoryItem = apps.get_model("laundry", "InventoryItem")
    ServiceInventoryUsage = apps.get_model("laundry", "ServiceInventoryUsage")

    categories = {}
    for name, description in CATEGORIES.items():
        category, created = InventoryCategory.objects.get_or_create(
            name=name,
            defaults={"description": description},
        )
        if not created and not category.description:
            category.description = description
            category.save(update_fields=["description"])
        categories[name] = category

    items = {}
    for name, defaults in ITEM_DEFAULTS.items():
        item, _created = InventoryItem.objects.get_or_create(
            name=name,
            defaults={
                "category": categories[defaults["category"]],
                "unit": defaults["unit"],
                "current_stock": defaults["current_stock"],
                "minimum_stock": defaults["minimum_stock"],
                "unit_cost": defaults["unit_cost"],
                "is_active": True,
            },
        )
        convert_seeded_item_units(item, defaults["unit"])
        if item.category_id is None:
            item.category = categories[defaults["category"]]
            item.save(update_fields=["category"])
        items[name] = item

    for service_type, item_name, quantity_per_kg, fixed_quantity in SERVICE_USAGE_RULES:
        ServiceInventoryUsage.objects.update_or_create(
            service_type=service_type,
            item=items[item_name],
            defaults={
                "quantity_per_kg": quantity_per_kg,
                "fixed_quantity": fixed_quantity,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("laundry", "0014_ready_for_pickup_walkin"),
    ]

    operations = [
        migrations.RunPython(seed_service_usage_rules, migrations.RunPython.noop),
    ]
