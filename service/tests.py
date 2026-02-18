from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from cars.models import Car
from service.models import ServiceCardEntry


class ServiceCardViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="tester", password="pass12345")
        self.car = Car.objects.create(
            owner=self.user,
            brand="Volkswagen",
            model="Tiguan",
            year=2020,
            vin="TESTVIN123",
            current_mileage=100000,
        )

    def test_service_card_requires_auth(self):
        response = self.client.get(reverse("service:service_card"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_user_can_create_regular_entry(self):
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name="Масло ДВС 5W-40",
            service_date="2026-01-01",
            mileage=90000,
        )
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(
            reverse("service:service_card"),
            data={
                "element_type": "consumable",
                "item_name": "Масло ДВС 5W-40",
                "mileage": "100500",
                "cost": "6300",
            },
        )
        self.assertEqual(response.status_code, 302)
        created_entry = ServiceCardEntry.objects.get(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            item_name="Масло ДВС 5W-40",
            mileage=100500,
        )
        self.assertEqual(str(created_entry.cost), "6300.00")

        page = self.client.get(reverse("service:service_card"))
        self.assertEqual(page.status_code, 200)
        regular_section = next(section for section in page.context["sections"] if section["key"] == "regular")
        oil_rows = [row for row in regular_section["rows"] if row["item_name"] == "Масло ДВС 5W-40"]
        self.assertEqual(len(oil_rows), 1)

        oil_row = oil_rows[0]
        self.assertEqual(oil_row["mileage"], 100500)
        self.assertEqual(str(oil_row["cost"]), "6300.00")
        self.assertTrue(oil_row["interval_text"])
        self.assertEqual(oil_row["last_date"], timezone.localdate())
        self.assertIsNotNone(oil_row["next_date"])

    def test_single_entry_has_no_interval(self):
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.EXTRA,
            element_type=ServiceCardEntry.ElementType.WORK,
            item_name="Чистка форсунок",
            service_date=timezone.localdate(),
            mileage=100000,
            cost="2000.00",
        )
        self.client.login(username="tester", password="pass12345")
        page = self.client.get(reverse("service:service_card"))
        extra_section = next(section for section in page.context["sections"] if section["key"] == "extra")
        row = next(row for row in extra_section["rows"] if row["item_name"] == "Чистка форсунок")
        self.assertEqual(row["interval_text"], "")
        self.assertIsNone(row["next_date"])

    def test_plan_section_contains_items_with_interval_and_forecast_price(self):
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name="Масло ДВС 5W-40",
            service_date="2024-01-01",
            mileage=100000,
            cost="1000.00",
        )
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name="Масло ДВС 5W-40",
            service_date="2025-01-01",
            mileage=110000,
            cost="2000.00",
        )

        self.client.login(username="tester", password="pass12345")
        page = self.client.get(reverse("service:service_card"))
        plan_section = next(section for section in page.context["sections"] if section["key"] == "plan")
        self.assertEqual(plan_section["title"], "📅 План обслуживания")
        oil_row = next(row for row in plan_section["rows"] if row["item_name"] == "Масло ДВС 5W-40")
        self.assertIsNotNone(oil_row["next_date"])
        self.assertEqual(str(oil_row["forecast_cost"]), "2300.00")
