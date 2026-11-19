import unittest
from datetime import date, datetime

from pydantic import ValidationError

from desktop_app import (
    RESOURCES,
    Appointment,
    format_form_value,
    record_to_mongo,
    validate_form_data,
)
from models.patient import Patient


class DesktopFormTests(unittest.TestCase):
    def test_all_crud_collections_are_configured(self):
        self.assertEqual(len(RESOURCES), 7)
        self.assertEqual(
            {resource.collection for resource in RESOURCES},
            {
                "patients",
                "doctors",
                "appointments",
                "medical_records",
                "prescriptions",
                "treatments",
                "payments",
            },
        )

    def test_patient_form_parses_enums_numbers_and_json_lists(self):
        patient = validate_form_data(
            Patient,
            {
                "name": "Alex Morgan",
                "age": "30",
                "sex": "other",
                "allergies": '["Penicillin"]',
                "address": "10 Example Road",
                "DOB": "1996-01-01",
                "marital_status": "single",
                "phone_number": "1234567890",
                "past_medical_history": "[]",
            },
        )

        self.assertEqual(patient.name, "Alex Morgan")
        self.assertEqual(patient.age, 30)
        self.assertEqual(patient.allergies, ["Penicillin"])

    def test_appointment_form_accepts_display_date_and_serializes_for_mongodb(self):
        appointment = validate_form_data(
            Appointment,
            {
                "doctor_id": "doctor-1",
                "patient_id": "patient-1",
                "date": "19-11-2026",
                "time": "143000",
                "fees": "500",
            },
        )

        self.assertEqual(appointment.date, date(2026, 11, 19))
        self.assertEqual(
            record_to_mongo(appointment)["date"],
            datetime(2026, 11, 19),
        )

    def test_existing_bson_dates_are_formatted_for_date_form_fields(self):
        field = Patient.model_fields["DOB"]
        self.assertEqual(
            format_form_value(field, datetime(1996, 1, 1), Patient),
            "1996-01-01",
        )

    def test_invalid_json_is_reported_as_validation_error(self):
        with self.assertRaises((ValueError, ValidationError)):
            validate_form_data(
                Patient,
                {
                    "name": "Alex Morgan",
                    "age": "30",
                    "sex": "other",
                    "allergies": "[not json]",
                    "address": "10 Example Road",
                    "DOB": "1996-01-01",
                    "marital_status": "single",
                    "phone_number": "1234567890",
                    "past_medical_history": "[]",
                },
            )


if __name__ == "__main__":
    unittest.main()
