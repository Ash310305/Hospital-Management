from datetime import date, datetime
from enum import Enum
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from pymongo.errors import ServerSelectionTimeoutError

from db import get_database
from models.appointments import Appointment
from models.billing_info import Payment
from models.doctor import Doctor
from models.medical_records import PatientClinicalProfile
from models.patient import Patient
from models.prescriptions import Treatment as Prescription

app = FastAPI(
    title="Hospital Management API",
    description=(
        "CRUD endpoints for patients, doctors, appointments, clinical records, "
        "prescriptions, treatments, and billing."
    ),
    version="1.0.0",
)


class TreatmentType(str, Enum):
    MEDICATION = "Medication"
    SURGERY_PROCEDURE = "Surgery / Procedure"
    PHYSIOTHERAPY = "Physiotherapy"
    LIFESTYLE_DIETARY = "Lifestyle / Dietary"
    OBSERVATION = "Observation"


class TreatmentStatus(str, Enum):
    PLANNED = "Planned"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    DISCONTINUED = "Discontinued"
    ON_HOLD = "On Hold"


class Route(str, Enum):
    ORAL = "Oral"
    IV = "IV"
    IM = "IM"
    TOPICAL = "Topical"
    INHALATION = "Inhalation"


class AnesthesiaType(str, Enum):
    NONE = "None"
    LOCAL = "Local"
    REGIONAL = "Regional"
    GENERAL = "General"


class MedicationItem(BaseModel):
    medicine_name: str = Field(..., min_length=1)
    dosage: str = Field(..., min_length=1)
    frequency: str = Field(..., min_length=1)
    route: Route = Route.ORAL
    duration_days: int = Field(..., ge=1)
    instructions: str = ""


class ProcedureItem(BaseModel):
    procedure_name: str = Field(..., min_length=1)
    scheduled_date: Optional[datetime] = None
    performed_date: Optional[datetime] = None
    assigned_staff_ids: list[str] = Field(default_factory=list)
    anesthesia_type: Optional[AnesthesiaType] = None
    procedure_notes: str = ""


class Treatment(BaseModel):
    treatment_id: Optional[str] = None
    record_id: Optional[str] = None
    patient_id: str = Field(..., min_length=1)
    doctor_id: str = Field(..., min_length=1)
    target_diagnosis: str = Field(..., min_length=1)
    treatment_type: TreatmentType
    treatment_status: TreatmentStatus = TreatmentStatus.PLANNED
    start_date: date
    expected_end_date: Optional[date] = None
    medications: list[MedicationItem] = Field(default_factory=list)
    procedures: list[ProcedureItem] = Field(default_factory=list)
    contraindications_checked: bool = False
    side_effects_observed: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    activity_restrictions: str = ""
    follow_up_required: bool = False
    next_review_date: Optional[date] = None
    outcome_notes: Optional[str] = None

    def to_mongo_dict(self) -> dict:
        data = self.model_dump()
        for field in ("start_date", "expected_end_date", "next_review_date"):
            if data[field] is not None:
                data[field] = datetime.combine(data[field], datetime.min.time())
        data["treatment_type"] = self.treatment_type.value
        data["treatment_status"] = self.treatment_status.value
        return data


def parse_object_id(doc_id: str) -> ObjectId:
    try:
        return ObjectId(doc_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID format: '{doc_id}'",
        )


def serialize_doc(doc: dict) -> dict:
    serialized = dict(doc)
    if "_id" in serialized:
        serialized["id"] = str(serialized.pop("_id"))
    return serialized


def model_to_mongo_dict(model: BaseModel) -> dict:
    converter = getattr(model, "to_mongo_dict", None)
    if converter is not None:
        return converter()
    return model.model_dump()


def create_resource(collection_name: str, model: BaseModel) -> dict:
    result = get_database()[collection_name].insert_one(model_to_mongo_dict(model))
    return {"id": str(result.inserted_id), "message": f"{collection_name} record created"}


def list_resources(collection_name: str, query: dict, limit: int) -> list[dict]:
    documents = get_database()[collection_name].find(query).limit(limit)
    return [serialize_doc(document) for document in documents]


def get_resource(collection_name: str, resource_id: str, resource_name: str) -> dict:
    doc = get_database()[collection_name].find_one({"_id": parse_object_id(resource_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{resource_name} not found")
    return serialize_doc(doc)


def replace_resource(
    collection_name: str,
    resource_id: str,
    resource_name: str,
    model: BaseModel,
) -> dict:
    result = get_database()[collection_name].replace_one(
        {"_id": parse_object_id(resource_id)},
        model_to_mongo_dict(model),
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"{resource_name} not found")
    return {"id": resource_id, "message": f"{resource_name} updated"}


def delete_resource(collection_name: str, resource_id: str, resource_name: str) -> dict:
    result = get_database()[collection_name].delete_one(
        {"_id": parse_object_id(resource_id)}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"{resource_name} not found")
    return {"message": f"{resource_name} deleted"}


@app.get("/")
def root():
    db = get_database()
    try:
        db.command("ping")
    except ServerSelectionTimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is unavailable. Check the connection URI and network access.",
        )
    return {"status": "ok", "database": db.name}


@app.post("/patients", status_code=status.HTTP_201_CREATED)
def create_patient(patient: Patient):
    return create_resource("patients", patient)


@app.get("/patients")
def list_patients(limit: int = Query(default=50, ge=1, le=100)):
    return list_resources("patients", {}, limit)


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    return get_resource("patients", patient_id, "Patient")


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, patient: Patient):
    return replace_resource("patients", patient_id, "Patient", patient)


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    return delete_resource("patients", patient_id, "Patient")


@app.post("/doctors", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: Doctor):
    return create_resource("doctors", doctor)


@app.get("/doctors")
def list_doctors(
    specialization: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {"specialization": specialization} if specialization else {}
    return list_resources("doctors", query, limit)


@app.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: str):
    return get_resource("doctors", doctor_id, "Doctor")


@app.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, doctor: Doctor):
    return replace_resource("doctors", doctor_id, "Doctor", doctor)


@app.delete("/doctors/{doctor_id}")
def delete_doctor(doctor_id: str):
    return delete_resource("doctors", doctor_id, "Doctor")


@app.post("/doctors/{doctor_id}/assign-patient/{patient_id}")
def assign_patient_to_doctor(doctor_id: str, patient_id: str):
    result = get_database().doctors.update_one(
        {"_id": parse_object_id(doctor_id)},
        {"$addToSet": {"patient_list": patient_id}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {"message": "Patient assigned to doctor", "patient_id": patient_id}


@app.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_appointment(appointment: Appointment):
    return create_resource("appointments", appointment)


@app.get("/appointments")
def list_appointments(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {
        key: value
        for key, value in (("patient_id", patient_id), ("doctor_id", doctor_id))
        if value is not None
    }
    return list_resources("appointments", query, limit)


@app.get("/appointments/{appointment_id}")
def get_appointment(appointment_id: str):
    return get_resource("appointments", appointment_id, "Appointment")


@app.put("/appointments/{appointment_id}")
def update_appointment(appointment_id: str, appointment: Appointment):
    return replace_resource(
        "appointments", appointment_id, "Appointment", appointment
    )


@app.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: str):
    return delete_resource("appointments", appointment_id, "Appointment")


@app.post("/medical-records", status_code=status.HTTP_201_CREATED)
def create_medical_record(record: PatientClinicalProfile):
    return create_resource("medical_records", record)


@app.get("/medical-records")
def list_medical_records(
    patient_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {"patient_id": patient_id} if patient_id else {}
    return list_resources("medical_records", query, limit)


@app.get("/medical-records/{record_id}")
def get_medical_record(record_id: str):
    return get_resource("medical_records", record_id, "Medical record")


@app.put("/medical-records/{record_id}")
def update_medical_record(record_id: str, record: PatientClinicalProfile):
    return replace_resource("medical_records", record_id, "Medical record", record)


@app.delete("/medical-records/{record_id}")
def delete_medical_record(record_id: str):
    return delete_resource("medical_records", record_id, "Medical record")


@app.post("/prescriptions", status_code=status.HTTP_201_CREATED)
def create_prescription(prescription: Prescription):
    return create_resource("prescriptions", prescription)


@app.get("/prescriptions")
def list_prescriptions(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {
        key: value
        for key, value in (("patient_id", patient_id), ("doctor_id", doctor_id))
        if value is not None
    }
    return list_resources("prescriptions", query, limit)


@app.get("/prescriptions/{prescription_id}")
def get_prescription(prescription_id: str):
    return get_resource("prescriptions", prescription_id, "Prescription")


@app.put("/prescriptions/{prescription_id}")
def update_prescription(prescription_id: str, prescription: Prescription):
    return replace_resource(
        "prescriptions", prescription_id, "Prescription", prescription
    )


@app.delete("/prescriptions/{prescription_id}")
def delete_prescription(prescription_id: str):
    return delete_resource("prescriptions", prescription_id, "Prescription")


@app.post("/treatments", status_code=status.HTTP_201_CREATED)
def create_treatment(treatment: Treatment):
    payload = treatment.to_mongo_dict()
    result = get_database().treatments.insert_one(payload)
    treatment_id = treatment.treatment_id or str(result.inserted_id)
    if treatment.treatment_id is None:
        get_database().treatments.update_one(
            {"_id": result.inserted_id},
            {"$set": {"treatment_id": treatment_id}},
        )
    return {"id": str(result.inserted_id), "message": "Treatment record created"}


@app.get("/treatments")
def list_treatments(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {
        key: value
        for key, value in (("patient_id", patient_id), ("doctor_id", doctor_id))
        if value is not None
    }
    return list_resources("treatments", query, limit)


@app.get("/treatments/{treatment_id}")
def get_treatment(treatment_id: str):
    return get_resource("treatments", treatment_id, "Treatment")


@app.put("/treatments/{treatment_id}")
def update_treatment(treatment_id: str, treatment: Treatment):
    return replace_resource("treatments", treatment_id, "Treatment", treatment)


@app.patch("/treatments/{treatment_id}/status")
def update_treatment_status(treatment_id: str, new_status: TreatmentStatus):
    result = get_database().treatments.update_one(
        {"_id": parse_object_id(treatment_id)},
        {"$set": {"treatment_status": new_status.value}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Treatment not found")
    return {"message": "Treatment status updated", "treatment_status": new_status.value}


@app.delete("/treatments/{treatment_id}")
def delete_treatment(treatment_id: str):
    return delete_resource("treatments", treatment_id, "Treatment")


@app.post("/billing", status_code=status.HTTP_201_CREATED)
def create_billing_record(payment: Payment):
    return create_resource("payments", payment)


@app.get("/billing")
def list_billing_records(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    query = {
        key: value
        for key, value in (("patient_id", patient_id), ("doctor_id", doctor_id))
        if value is not None
    }
    return list_resources("payments", query, limit)


@app.get("/billing/{payment_id}")
def get_billing_record(payment_id: str):
    return get_resource("payments", payment_id, "Billing record")


@app.put("/billing/{payment_id}")
def update_billing_record(payment_id: str, payment: Payment):
    return replace_resource("payments", payment_id, "Billing record", payment)


@app.delete("/billing/{payment_id}")
def delete_billing_record(payment_id: str):
    return delete_resource("payments", payment_id, "Billing record")
