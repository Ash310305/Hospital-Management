from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"


class Patient(BaseModel):
    name: str = Field(..., min_length=1, description="Full name of the patient")
    age: int = Field(..., ge=0, le=150, description="Age in years")
    sex: Sex
    allergies: List[str] = Field(default_factory=list)
    address: str = Field(..., min_length=1)
    DOB: date
    marital_status: MaritalStatus
    phone_number: int = Field(..., gt=0, description="Numeric phone number")
    past_medical_history: List[str] = Field(default_factory=list)

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        data = self.model_dump()
        # MongoDB BSON stores datetime objects rather than bare datetime.date
        data["DOB"] = datetime.combine(self.DOB, datetime.min.time())
        data["sex"] = self.sex.value
        data["marital_status"] = self.marital_status.value
        return data

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Patient"]:
        """Instantiate a Patient model from a MongoDB document."""
        if not doc:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        if isinstance(doc.get("DOB"), datetime):
            doc["DOB"] = doc["DOB"].date()
        return cls(**doc)


# Example usage
if __name__ == "__main__":
    sample_patient = Patient(
        name="Rohan Verma",
        age=32,
        sex=Sex.MALE,
        allergies=["Penicillin", "Dust"],
        address="14 MG Road, Gurugram, Haryana",
        DOB=date(1994, 5, 18),
        marital_status=MaritalStatus.MARRIED,
        phone_number=9876543210,
        past_medical_history=["Asthma"],
    )

    print("Validated Model:", sample_patient)
    print("MongoDB Payload:", sample_patient.to_mongo_dict())