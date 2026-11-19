import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId
import certifi
from fastapi import HTTPException
from pymongo.errors import ServerSelectionTimeoutError

import app
import db
from models.appointments import Appointment
from models.billing_info import Payment, PaymentMode
from models.patient import MaritalStatus, Patient, Sex


class Cursor:
    def __init__(self, documents):
        self.documents = documents

    def limit(self, limit):
        return self.documents[:limit]


class Collection:
    def __init__(self):
        self.documents = {}

    def insert_one(self, document):
        inserted_id = ObjectId()
        self.documents[inserted_id] = dict(document)
        return SimpleNamespace(inserted_id=inserted_id)

    def find(self, query):
        matches = [
            {"_id": object_id, **document}
            for object_id, document in self.documents.items()
            if all(
                (object_id if key == "_id" else document.get(key)) == value
                for key, value in query.items()
            )
        ]
        return Cursor(matches)

    def find_one(self, query):
        return next(iter(self.find(query).limit(1)), None)

    def replace_one(self, query, document):
        object_id = query["_id"]
        if object_id not in self.documents:
            return SimpleNamespace(matched_count=0)
        self.documents[object_id] = dict(document)
        return SimpleNamespace(matched_count=1)

    def delete_one(self, query):
        deleted = self.documents.pop(query["_id"], None)
        return SimpleNamespace(deleted_count=int(deleted is not None))


class Database:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, Collection())


class CrudApiTests(unittest.TestCase):
    def test_database_client_uses_trusted_ca_bundle(self):
        db.get_database.cache_clear()
        try:
            with patch("db.MongoClient") as mongo_client:
                with patch.dict(
                    "os.environ",
                    {
                        "MONGODB_URI": "mongodb://localhost:27017",
                        "MONGODB_DATABASE": "test_database",
                    },
                ):
                    db.get_database()
                mongo_client.assert_called_once_with(
                    "mongodb://localhost:27017",
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=5000,
                )
        finally:
            db.get_database.cache_clear()

    def test_patient_create_read_list_update_and_delete(self):
        database = Database()
        patient = Patient(
            name="Alex Morgan",
            age=30,
            sex=Sex.OTHER,
            address="10 Example Road",
            DOB=date(1996, 1, 1),
            marital_status=MaritalStatus.SINGLE,
            phone_number=1234567890,
        )

        with patch("app.get_database", return_value=database):
            created = app.create_patient(patient)
            patient_id = created["id"]

            self.assertEqual(app.get_patient(patient_id)["name"], "Alex Morgan")
            self.assertEqual(len(app.list_patients(limit=10)), 1)

            patient.address = "11 Example Road"
            app.update_patient(patient_id, patient)
            self.assertEqual(app.get_patient(patient_id)["address"], "11 Example Road")

            app.delete_patient(patient_id)
            with self.assertRaises(HTTPException) as error:
                app.get_patient(patient_id)
            self.assertEqual(error.exception.status_code, 404)

    def test_invalid_id_returns_bad_request(self):
        with self.assertRaises(HTTPException) as error:
            app.parse_object_id("not-an-object-id")
        self.assertEqual(error.exception.status_code, 400)

    def test_health_check_reports_unavailable_database(self):
        with patch("app.get_database") as get_database:
            get_database.return_value.command.side_effect = ServerSelectionTimeoutError(
                "connection failed"
            )
            with self.assertRaises(HTTPException) as error:
                app.root()
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("MongoDB is unavailable", error.exception.detail)

    def test_all_resources_expose_crud_routes(self):
        paths = app.app.openapi()["paths"]
        for resource in (
            "patients",
            "doctors",
            "appointments",
            "medical-records",
            "prescriptions",
            "treatments",
            "billing",
        ):
            with self.subTest(resource=resource):
                self.assertTrue({"get", "post"}.issubset(paths[f"/{resource}"]))
                detail_path = f"/{resource}/{{{resource[:-1]}_id}}"
                if detail_path not in paths:
                    detail_path = {
                        "medical-records": "/medical-records/{record_id}",
                        "billing": "/billing/{payment_id}",
                    }.get(resource, detail_path)
                self.assertTrue({"get", "put", "delete"}.issubset(paths[detail_path]))

    def test_appointment_and_payment_mongo_serialization(self):
        appointment = Appointment(
            doctor_id="doctor-1",
            patient_id="patient-1",
            date="19-11-2026",
            time="143000",
            fees=500,
        )
        self.assertEqual(
            appointment.to_mongo_dict()["date"],
            datetime_from_date(date(2026, 11, 19)),
        )
        payment = Payment(
            doctor_id="doctor-1",
            patient_id="patient-1",
            payment_mode=PaymentMode.CASH,
            amount=500,
            time="143000",
        )
        self.assertEqual(payment.to_mongo_dict()["time"], "14:30:00")


def datetime_from_date(value):
    return datetime.combine(value, datetime.min.time())


if __name__ == "__main__":
    unittest.main()
