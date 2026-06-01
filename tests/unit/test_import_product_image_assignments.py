from pathlib import Path

import pytest

from app.domain.models.enums import TicketTag
from app.infrastructure.database.models.orm_models import CategoryORM, ProductORM
from scripts.import_product_image_assignments import (
    ProductImageAssignment,
    _assignment_mismatch,
    load_assignments,
)


def _category(**overrides):
    values = {
        "name": "Casera",
        "slug": "casera",
        "ticket_tag": TicketTag.CAJA,
        "image_url": None,
        "sort_order": 1,
        "is_active": True,
    }
    values.update(overrides)
    return CategoryORM(**values)


def _product(**overrides):
    values = {
        "category_id": 1,
        "sku": "CAS-EMP-CAM-QUE-GRA",
        "name": "Camarón Queso Grande",
        "slug": "camaron-queso-grande",
        "subcategory": "Empanadas",
        "description": None,
        "price": 2500,
        "image_url": None,
        "ticket_tag": TicketTag.CAJA,
        "is_available": True,
        "sort_order": 1,
    }
    values.update(overrides)
    return ProductORM(**values)


def test_load_assignments_reads_empanadas_csv():
    path = Path("exports/empanadas_product_image_assignments.csv")

    assignments = load_assignments(path)

    assert len(assignments) == 13
    assert assignments[0].sku == "CAS-EMP-CAM-QUE-GRA"
    assert assignments[0].category == "casera"
    assert assignments[0].subcategory == "empanadas"
    assert assignments[0].image_url.endswith("/empanada-camaron-queso.webp")
    assert {assignment.sku for assignment in assignments}.isdisjoint(
        {
            "CAS-EMP-ACE-QUE-GRA",
            "CAS-EMP-ACE-QUE-MED",
            "CAS-EMP-CHOD-QUE-GRA",
            "CAS-EMP-CHOD-QUE-MED",
            "CAS-EMP-PAL-QUE-GRA",
            "CAS-EMP-PAL-QUE-MED",
            "CAS-EMP-PINO-HORNO",
        }
    )


def test_load_assignments_requires_sku_and_image_url():
    csv_path = Path("tests/fixtures/product_image_assignments_missing_image_url.csv")

    with pytest.raises(ValueError, match="image_url"):
        load_assignments(csv_path)


def test_assignment_accepts_normalized_category_subcategory_and_name():
    assignment = ProductImageAssignment(
        sku="CAS-EMP-CAM-QUE-GRA",
        name="Camaron Queso Grande",
        category="casera",
        subcategory="empanadas",
        image_url="https://img.test/empanada.webp",
    )

    assert _assignment_mismatch(_product(), _category(), assignment) == ""


def test_assignment_rejects_mismatched_safety_columns():
    assignment = ProductImageAssignment(
        sku="CAS-EMP-CAM-QUE-GRA",
        name="Jamón Queso Grande",
        category="casera",
        subcategory="empanadas",
        image_url="https://img.test/empanada.webp",
    )

    assert "name mismatch" in _assignment_mismatch(_product(), _category(), assignment)
