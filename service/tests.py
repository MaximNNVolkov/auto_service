from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from datetime import date, timedelta

from django.utils import timezone

from cars.models import Car
from service import services
from service.models import CustomServiceItem, ServiceCardEntry


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
                "service_date": timezone.localdate().isoformat(),
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

    def test_user_can_add_custom_item_and_reuse_later(self):
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(
            reverse("service:service_card"),
            data={
                "element_type": "work",
                "item_name": "Чистка форсунок",
                "custom_item_name": "Замена лампы ближнего света",
                "custom_section": "extra",
                "service_date": timezone.localdate().isoformat(),
                "mileage": "101000",
                "cost": "1200",
            },
        )
        self.assertEqual(response.status_code, 302)

        created_entry = ServiceCardEntry.objects.get(
            car=self.car,
            item_name="Замена лампы ближнего света",
            mileage=101000,
        )
        self.assertEqual(created_entry.section, ServiceCardEntry.Section.EXTRA)

        custom_item = CustomServiceItem.objects.get(
            car=self.car,
            element_type=ServiceCardEntry.ElementType.WORK,
            name="Замена лампы ближнего света",
        )
        self.assertEqual(custom_item.section, ServiceCardEntry.Section.EXTRA)

        repeat_response = self.client.post(
            reverse("service:service_card"),
            data={
                "element_type": "work",
                "item_name": "Замена лампы ближнего света",
                "custom_item_name": "",
                "custom_section": "",
                "service_date": timezone.localdate().isoformat(),
                "mileage": "101500",
                "cost": "1300",
            },
        )
        self.assertEqual(repeat_response.status_code, 302)
        self.assertEqual(
            ServiceCardEntry.objects.filter(
                car=self.car,
                item_name="Замена лампы ближнего света",
            ).count(),
            2,
        )

    def test_existing_custom_item_can_be_saved_without_custom_fields(self):
        CustomServiceItem.objects.create(
            car=self.car,
            element_type=ServiceCardEntry.ElementType.WORK,
            section=ServiceCardEntry.Section.CHASSIS,
            name="Замена рулевого наконечника",
        )
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(
            reverse("service:service_card"),
            data={
                "element_type": "work",
                "item_name": "Замена рулевого наконечника",
                "custom_item_name": "",
                "custom_section": "",
                "service_date": timezone.localdate().isoformat(),
                "mileage": "102500",
                "cost": "3400",
            },
        )
        self.assertEqual(response.status_code, 302)
        created_entry = ServiceCardEntry.objects.get(
            car=self.car,
            item_name="Замена рулевого наконечника",
            mileage=102500,
        )
        self.assertEqual(created_entry.section, ServiceCardEntry.Section.CHASSIS)

    def _post_entry(self, **overrides):
        data = {
            "element_type": "consumable",
            "item_name": "Масло ДВС 5W-40",
            "service_date": timezone.localdate().isoformat(),
            "mileage": "100500",
            "cost": "6300",
        }
        data.update(overrides)
        return self.client.post(reverse("service:service_card"), data=data)

    def test_entry_can_be_saved_with_past_date(self):
        self.client.login(username="tester", password="pass12345")
        response = self._post_entry(service_date="2025-05-10", mileage="95000")
        self.assertEqual(response.status_code, 302)
        entry = ServiceCardEntry.objects.get(car=self.car, mileage=95000)
        self.assertEqual(entry.service_date, date(2025, 5, 10))

    def test_future_date_is_rejected(self):
        self.client.login(username="tester", password="pass12345")
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self._post_entry(service_date=tomorrow.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertIn("service_date", response.context["work_form"].errors)
        self.assertFalse(ServiceCardEntry.objects.exists())

    def test_mileage_lower_than_earlier_entry_is_rejected(self):
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name="Масляный фильтр",
            service_date="2025-01-01",
            mileage=120000,
        )
        self.client.login(username="tester", password="pass12345")
        response = self._post_entry(service_date="2025-06-01", mileage="110000")
        self.assertEqual(response.status_code, 200)
        self.assertIn("mileage", response.context["work_form"].errors)

    def test_mileage_higher_than_later_entry_is_rejected(self):
        ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name="Масляный фильтр",
            service_date="2025-06-01",
            mileage=90000,
        )
        self.client.login(username="tester", password="pass12345")
        response = self._post_entry(service_date="2025-01-01", mileage="95000")
        self.assertEqual(response.status_code, 200)
        self.assertIn("mileage", response.context["work_form"].errors)

    def test_car_mileage_is_updated_only_when_higher(self):
        self.client.login(username="tester", password="pass12345")
        self._post_entry(mileage="105000")
        self.car.refresh_from_db()
        self.assertEqual(self.car.current_mileage, 105000)

        self._post_entry(service_date="2024-01-01", mileage="80000")
        self.car.refresh_from_db()
        self.assertEqual(self.car.current_mileage, 105000)


class EntryManagementTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="tester", password="pass12345")
        self.other = user_model.objects.create_user(username="other", password="pass12345")
        self.car = Car.objects.create(
            owner=self.user, brand="Volkswagen", model="Tiguan", year=2020, vin="VIN1", current_mileage=100000
        )
        self.second_car = Car.objects.create(
            owner=self.user, brand="Skoda", model="Octavia", year=2018, vin="VIN2", current_mileage=50000
        )
        self.foreign_car = Car.objects.create(
            owner=self.other, brand="Lada", model="Vesta", year=2021, vin="VIN3", current_mileage=30000
        )
        self.entry = self._create_entry(self.car, "2025-01-01", 90000)
        self.client.login(username="tester", password="pass12345")

    @staticmethod
    def _create_entry(car, service_date, mileage, item_name="Масло ДВС 5W-40"):
        return ServiceCardEntry.objects.create(
            car=car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name=item_name,
            service_date=service_date,
            mileage=mileage,
            cost="1000.00",
        )

    def test_first_car_is_selected_by_default(self):
        response = self.client.get(reverse("service:service_card"))
        self.assertEqual(response.context["car"], self.car)
        self.assertContains(response, 'name="car"')

    def test_car_can_be_selected(self):
        response = self.client.get(reverse("service:service_card"), {"car": self.second_car.pk})
        self.assertEqual(response.context["car"], self.second_car)

    def test_foreign_car_is_not_accessible(self):
        response = self.client.get(reverse("service:service_card"), {"car": self.foreign_car.pk})
        self.assertEqual(response.status_code, 404)

    def test_entry_is_created_for_selected_car(self):
        response = self.client.post(
            reverse("service:service_card") + f"?car={self.second_car.pk}",
            data={
                "element_type": "consumable",
                "item_name": "Масло ДВС 5W-40",
                "service_date": timezone.localdate().isoformat(),
                "mileage": "51000",
                "cost": "5000",
            },
        )
        self.assertRedirects(response, reverse("service:service_card") + f"?car={self.second_car.pk}")
        self.assertTrue(ServiceCardEntry.objects.filter(car=self.second_car, mileage=51000).exists())

    def test_entry_list_shows_only_selected_car_entries(self):
        self._create_entry(self.second_car, "2025-02-01", 40000, item_name="Салонный фильтр")
        response = self.client.get(reverse("service:entry_list"))
        self.assertEqual(list(response.context["entries"]), [self.entry])

    def test_edit_page_is_rendered(self):
        response = self.client.get(reverse("service:entry_edit", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="2025-01-01"')

    def test_entry_can_be_edited(self):
        response = self.client.post(
            reverse("service:entry_edit", args=[self.entry.pk]),
            data={"service_date": "2025-01-05", "mileage": "105000", "cost": "1500"},
        )
        self.assertRedirects(response, reverse("service:entry_list") + f"?car={self.car.pk}")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.service_date, date(2025, 1, 5))
        self.assertEqual(self.entry.mileage, 105000)
        self.car.refresh_from_db()
        self.assertEqual(self.car.current_mileage, 105000)

    def test_edit_mileage_is_checked_against_other_entries_only(self):
        self._create_entry(self.car, "2025-06-01", 95000)
        response = self.client.post(
            reverse("service:entry_edit", args=[self.entry.pk]),
            data={"service_date": "2025-01-01", "mileage": "96000", "cost": "1000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("mileage", response.context["form"].errors)

        response = self.client.post(
            reverse("service:entry_edit", args=[self.entry.pk]),
            data={"service_date": "2025-01-01", "mileage": "91000", "cost": "1000"},
        )
        self.assertEqual(response.status_code, 302)

    def test_entry_can_be_deleted(self):
        response = self.client.post(reverse("service:entry_delete", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServiceCardEntry.objects.filter(pk=self.entry.pk).exists())

    def test_delete_requires_post(self):
        response = self.client.get(reverse("service:entry_delete", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ServiceCardEntry.objects.filter(pk=self.entry.pk).exists())

    def test_foreign_entry_cannot_be_edited_or_deleted(self):
        foreign_entry = self._create_entry(self.foreign_car, "2025-01-01", 20000)
        edit = self.client.get(reverse("service:entry_edit", args=[foreign_entry.pk]))
        delete = self.client.post(reverse("service:entry_delete", args=[foreign_entry.pk]))
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertTrue(ServiceCardEntry.objects.filter(pk=foreign_entry.pk).exists())


class IntervalCalculationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="tester", password="pass12345")
        self.car = Car.objects.create(
            owner=user, brand="Volkswagen", model="Tiguan", year=2020, vin="VIN1", current_mileage=100000
        )

    def _entry(self, service_date, mileage, item_name="Масло ДВС 5W-40"):
        return ServiceCardEntry.objects.create(
            car=self.car,
            section=ServiceCardEntry.Section.REGULAR,
            element_type=ServiceCardEntry.ElementType.CONSUMABLE,
            item_name=item_name,
            service_date=service_date,
            mileage=mileage,
            cost="1000.00",
        )

    def _rows(self):
        entries = list(self.car.service_card_entries.all())
        return services.build_section_rows(
            entries,
            daily_mileage=services.calculate_daily_mileage(entries),
            current_mileage=self.car.current_mileage,
            today=date(2024, 1, 1),
        )

    def test_mileage_interval_is_calculated(self):
        self._entry(date(2022, 1, 1), 50000)
        self._entry(date(2023, 1, 1), 60000)
        row = self._rows()[0]
        self.assertEqual(row["interval_km"], 10000)
        self.assertEqual(row["next_mileage"], 70000)
        self.assertEqual(row["interval_text"], "365 дн. / 10000 км")

    def test_next_date_uses_earliest_of_time_and_mileage(self):
        # Масло меняли раз в 2 года / 10 000 км, а машина проходит ~10 000 км в год:
        # по пробегу замена нужна примерно через год, раньше, чем по времени.
        self._entry(date(2020, 1, 1), 50000)
        self._entry(date(2022, 1, 1), 60000)
        self._entry(date(2022, 1, 1), 60000, item_name="Салонный фильтр")
        self._entry(date(2023, 1, 1), 80000, item_name="Салонный фильтр")
        oil = next(row for row in self._rows() if row["item_name"] == "Масло ДВС 5W-40")
        self.assertEqual(oil["interval_days"], 731)
        daily = services.calculate_daily_mileage(list(self.car.service_card_entries.all()))
        self.assertEqual(daily, (30000, 1096))
        self.assertEqual(oil["next_date"], date(2022, 1, 1) + timedelta(days=round(10000 * 1096 / 30000)))

    def test_row_is_overdue_by_mileage(self):
        self._entry(date(2023, 1, 1), 80000)
        self._entry(date(2023, 6, 1), 90000)
        row = self._rows()[0]
        self.assertEqual(row["next_mileage"], 100000)
        self.assertTrue(row["overdue"])

    def test_plan_includes_items_with_only_mileage_forecast(self):
        self._entry(None, 80000)
        self._entry(None, 90000)
        plan = services.build_plan_rows(self._rows())
        self.assertEqual(len(plan), 1)
        self.assertIsNone(plan[0]["next_date"])
        self.assertEqual(plan[0]["next_mileage"], 100000)
