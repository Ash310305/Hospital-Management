from datetime import date, datetime, time
from enum import Enum
from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from db import get_database
from doctors import Doctor, Sex as DoctorSex
from patients import MaritalStatus, Patient, Sex as PatientSex

app = FastAPI(
    title="Hospital Management API",
    description="Endpoints for managing patients, doctors, and treatment plans in MongoDB.",
    version="1.0.0",
)


# --- Treatment Models ---


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
    assigned_staff_ids: List[str] = Field(default_factory=list)
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
    medications: List[MedicationItem] = Field(default_factory=list)
    procedures: List[ProcedureItem] = Field(default_factory=list)
    contraindications_checked: bool = False
    side_effects_observed: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
    activity_restrictions: str = ""
    follow_up_required: bool = False
    next_review_date: Optional[date] = None
    outcome_notes: Optional[str] = None

    def to_mongo_dict(self) -> dict:
        data = self.model_dump()
        data["start_date"] = datetime.combine(self.start_date, datetime.min.time())
        if self.expected_end_date:
            data["expected_end_date"] = datetime.combine(
                self.expected_end_date, datetime.min.time()
            )
        if self.next_review_date:
            data["next_review_date"] = datetime.combine(
                self.next_review_date, datetime.min.time()
            )
        data["treatment_type"] = self.treatment_type.value
        data["treatment_status"] = self.treatment_status.value
        return data


# --- Helpers ---


def parse_object_id(doc_id: str) -> ObjectId:
    try:
        return ObjectId(doc_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID format: '{doc_id}'",
        )


def serialize_doc(doc: dict) -> dict:
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


# --- Health Check ---


@app.get("/")
def root():
    db = get_database()
    db.command("ping")
    return {"status": "ok", "database": db.name}


# --- Patients Endpoints ---


@app.post("/patients", status_code=status.HTTP_201_CREATED)
def create_patient(patient: Patient):
    db = get_database()
    result = db.patients.insert_one(patient.to_mongo_dict())
    return {"id": str(result.inserted_id), "message": "Patient created"}


@app.get("/patients")
def list_patients(limit: int = 50):
    db = get_database()
    docs = db.patients.find().limit(limit)
    return [serialize_doc(d) for d in docs]


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    db = get_database()
    oid = parse_object_id(patient_id)
    doc = db.patients.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Patient not found")
    return serialize_doc(doc)


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    db = get_database()
    oid = parse_object_id(patient_id)
    res = db.patients.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"message": "Patient deleted"}


# --- Doctors Endpoints ---


@app.post("/doctors", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: Doctor):
    db = get_database()
    result = db.doctors.insert_one(doctor.to_mongo_dict())
    return {"id": str(result.inserted_id), "message": "Doctor created"}


@app.get("/doctors")
def list_doctors(specialization: Optional[str] = None, limit: int = 50):
    db = get_database()
    query = {"specialization": specialization} if specialization else {}
    docs = db.doctors.find(query).limit(limit)
    return [serialize_doc(d) for d in docs]


@app.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: str):
    db = get_database()
    oid = parse_object_id(doctor_id)
    doc = db.doctors.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return serialize_doc(doc)


@app.post("/doctors/{doctor_id}/assign-patient/{patient_id}")
def assign_patient_to_doctor(doctor_id: str, patient_id: str):
    db = get_database()
    doc_oid = parse_object_id(doctor_id)
    res = db.doctors.update_one(
        {"_id": doc_oid},
        {"$addToSet": {"patient_list": patient_id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {"message": "Patient assigned to doctor", "patient_id": patient_id}


# --- Treatments Endpoints ---


@app.post("/treatments", status_code=status.HTTP_201_CREATED)
def create_treatment(treatment: Treatment):
    db = get_database()
    payload = treatment.to_mongo_dict()
    result = db.treatments.insert_one(payload)
    if not treatment.treatment_id:
        db.treatments.update_one(
            {"_id": result.inserted_id},
            {"$set": {"treatment_id": str(result.inserted_id)}},
        )
    return {"id": str(result.inserted_id), "message": "Treatment record created"}


@app.get("/treatments")
def list_treatments(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    limit: int = 50,
):
    db = get_database()
    query = {}
    if patient_id:
        query["patient_id"] = patient_id
    if doctor_id:
        query["doctor_id"] = doctor_id
    docs = db.treatments.find(query).limit(limit)
    return [serialize_doc(d) for d in docs]


@app.patch("/treatments/{treatment_id}/status")
def update_treatment_status(treatment_id: str, new_status: TreatmentStatus):
    db = get_database()
    oid = parse_object_id(treatment_id)
    res = db.treatments.update_one(
        {"_id": oid},
        {"$set": {"treatment_status": new_status.value}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Treatment not found")
    return {"message": "Treatment status updated", "treatment_status": new_status.value}