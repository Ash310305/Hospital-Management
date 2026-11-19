import unittest
from datetime import date, datetime

from desktop_app import (
    RESOURCES,
    Appointment,
    format_form_value,
    parse_date_input,
    parse_time_input,
    record_to_mongo,
    shift_month,
    summarize_counts,
    validate_form_data,
)
from models.doctor import Doctor, Sex
from models.medical_records import PatientClinicalProfile
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

    def test_patient_form_accepts_day_month_year_for_dob(self):
        patient = validate_form_data(
            Patient,
            {
                "name": "Alex Morgan",
                "age": "22",
                "sex": "other",
                "allergies": "",
                "address": "10 Example Road",
                "DOB": "07/12/2003",
                "marital_status": "single",
                "phone_number": "1234567890",
                "past_medical_history": "",
            },
        )

        self.assertEqual(patient.DOB, date(2003, 12, 7))

    def test_date_parser_reports_supported_formats(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD or DD/MM/YYYY"):
            parse_date_input("not a date")

    def test_calendar_date_parser_accepts_supported_formats(self):
        self.assertEqual(parse_date_input("2003-12-07"), date(2003, 12, 7))
        self.assertEqual(parse_date_input("07/12/2003"), date(2003, 12, 7))
        self.assertEqual(parse_date_input("07-12-2003"), date(2003, 12, 7))

    def test_clock_input_validates_and_serializes_doctor_visiting_time(self):
        doctor = validate_form_data(
            Doctor,
            {
                "name": "Dr. Alex Morgan",
                "DOB": "07/12/2003",
                "college_name": "Example Medical College",
                "sex": "other",
                "specialization": "Cardiology",
                "age": "40",
                "visiting_time": "07:30 PM",
                "patient_list": "",
            },
        )

        self.assertEqual(doctor.visiting_time.hour, 19)
        self.assertEqual(doctor.visiting_time.minute, 30)
        self.assertEqual(record_to_mongo(doctor)["visiting_time"], "19:30:00")

    def test_clock_input_accepts_existing_24_hour_and_compact_time_formats(self):
        self.assertEqual(parse_time_input("19:30:00").hour, 19)
        self.assertEqual(parse_time_input("073000").hour, 7)
        self.assertEqual(parse_time_input("12:15 AM").hour, 0)
        self.assertEqual(parse_time_input("12:15 PM").hour, 12)

    def test_clock_input_formats_existing_doctor_visiting_time(self):
        field = Doctor.model_fields["visiting_time"]
        self.assertEqual(
            format_form_value(field, parse_time_input("19:30:00"), Doctor),
            "07:30 PM",
        )

    def test_calendar_month_navigation_handles_year_boundaries(self):
        self.assertEqual(shift_month(date(2026, 1, 15), -1), date(2025, 12, 1))
        self.assertEqual(shift_month(date(2026, 12, 15), 1), date(2027, 1, 1))

    def test_dashboard_summarizes_patient_doctor_and_all_resource_totals(self):
        totals = summarize_counts(
            {
                "patients": 12,
                "doctors": 4,
                "appointments": 20,
                "medical-records": 11,
                "prescriptions": 6,
                "treatments": 8,
                "billing": 19,
            }
        )

        self.assertEqual(totals, {"patients": 12, "doctors": 4, "total": 80})

    def test_all_top_level_date_fields_use_calendar_controls(self):
        expected = {
            "Patients.DOB",
            "Doctors.DOB",
            "Appointments.date",
            "Treatments.start_date",
            "Treatments.expected_end_date",
            "Treatments.next_review_date",
        }
        actual = {
            f"{resource.label}.{name}"
            for resource in RESOURCES
            for name, field in resource.model.model_fields.items()
            if field.annotation is date
            or date in getattr(field.annotation, "__args__", ())
        }
        self.assertEqual(actual, expected)

    def test_patient_form_accepts_comma_separated_list_values(self):
        patient = validate_form_data(
            Patient,
            {
                "name": "Alex Morgan",
                "age": "30",
                "sex": "other",
                "allergies": "Penicillin, Dust",
                "address": "10 Example Road",
                "DOB": "1996-01-01",
                "marital_status": "single",
                "phone_number": "1234567890",
                "past_medical_history": "",
            },
        )

        self.assertEqual(patient.allergies, ["Penicillin", "Dust"])
        self.assertEqual(patient.past_medical_history, [])

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
        with self.assertRaisesRegex(ValueError, "Immunization history must be a valid JSON array"):
            validate_form_data(
                PatientClinicalProfile,
                {
                    "patient_id": "patient-1",
                    "blood_group": "O+",
                    "chronic_conditions": "[]",
                    "height": "175",
                    "weight": "70",
                    "immunization_history": '[{"vaccine":}]',
                },
            )


if __name__ == "__main__":
    unittest.main()
