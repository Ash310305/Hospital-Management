from datetime import date, datetime, time
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Doctor(BaseModel):
    name: str = Field(..., min_length=1, description="Full name of the doctor")
    DOB: date
    college_name: str = Field(..., min_length=1, description="Medical college / alma mater")
    sex: Sex
    specialization: str = Field(..., min_length=1)
    age: int = Field(..., ge=18, le=120, description="Age in years")
    visiting_time: time = Field(..., description="Visiting time in HH:MM:SS format")
    patient_list: List[str] = Field(
        default_factory=list, description="List of patient IDs assigned to the doctor"
    )

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        data = self.model_dump()
        # MongoDB BSON stores datetime rather than bare date or time objects
        data["DOB"] = datetime.combine(self.DOB, datetime.min.time())
        data["visiting_time"] = self.visiting_time.strftime("%H:%M:%S")
        data["sex"] = self.sex.value
        return data

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Doctor"]:
        """Instantiate a Doctor model from a MongoDB document."""
        if not doc:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        if isinstance(doc.get("DOB"), datetime):
            doc["DOB"] = doc["DOB"].date()
        if isinstance(doc.get("visiting_time"), str):
            doc["visiting_time"] = time.fromisoformat(doc["visiting_time"])
        return cls(**doc)


# Example usage
if __name__ == "__main__":
    sample_doctor = Doctor(
        name="Dr. Ananya Sharma",
        DOB=date(1988, 9, 12),
        college_name="AIIMS New Delhi",
        sex=Sex.FEMALE,
        specialization="Cardiology",
        age=38,
        visiting_time=time(10, 30, 0),
        patient_list=["pat_101", "pat_102", "pat_105"],
    )

    print("Validated Model:", sample_doctor)
    print("MongoDB Payload:", sample_doctor.to_mongo_dict())