from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class BloodGroup(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"


class PatientClinicalProfile(BaseModel):
    patient_id: str = Field(..., min_length=1, description="ID of the patient")
    blood_group: BloodGroup = Field(..., description="Patient blood group")
    chronic_conditions: List[str] = Field(
        default_factory=list, description="List of chronic medical conditions"
    )
    height: int = Field(..., gt=0, description="Height in centimeters")
    weight: int = Field(..., gt=0, description="Weight in kilograms")
    immunization_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of immunization records"
    )

    @field_validator("immunization_history", mode="before")
    @classmethod
    def normalize_immunization_dates(cls, value):
        """Normalize date values inside immunization entries if present."""
        if not isinstance(value, list):
            return value
        normalized = []
        for entry in value:
            if isinstance(entry, dict):
                item = dict(entry)
                if isinstance(item.get("date"), datetime):
                    item["date"] = item["date"].date()
                normalized.append(item)
            else:
                normalized.append(entry)
        return normalized

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        serialized_immunizations = []
        for entry in self.immunization_history:
            item = dict(entry)
            if isinstance(item.get("date"), date) and not isinstance(item.get("date"), datetime):
                item["date"] = datetime.combine(item["date"], datetime.min.time())
            serialized_immunizations.append(item)

        return {
            "patient_id": self.patient_id,
            "blood_group": self.blood_group.value,
            "chronic_conditions": self.chronic_conditions,
            "height": self.height,
            "weight": self.weight,
            "immunization_history": serialized_immunizations,
            "updated_at": datetime.now(),
        }

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["PatientClinicalProfile"]:
        """Instantiate a PatientClinicalProfile model from a MongoDB document."""
        if not doc:
            return None
        parsed = dict(doc)
        parsed.pop("_id", None)
        parsed.pop("updated_at", None)
        if isinstance(parsed.get("immunization_history"), list):
            restored = []
            for entry in parsed["immunization_history"]:
                if isinstance(entry, dict):
                    item = dict(entry)
                    if isinstance(item.get("date"), datetime):
                        item["date"] = item["date"].date()
                    restored.append(item)
                else:
                    restored.append(entry)
            parsed["immunization_history"] = restored
        return cls(**parsed)


# Example usage
if __name__ == "__main__":
    sample_profile = PatientClinicalProfile(
        patient_id="pat_101",
        blood_group=BloodGroup.O_POS,
        chronic_conditions=["Hypertension", "Type 2 Diabetes"],
        height=175,
        weight=74,
        immunization_history=[
            {"vaccine": "Tetanus", "date": date(2024, 3, 10), "dose": "Booster"},
            {"vaccine": "Hepatitis B", "date": "2022-07-15", "dose": "Dose 3"},
        ],
    )

    print("Validated Model:", sample_profile)
    print("MongoDB Payload:", sample_profile.to_mongo_dict())