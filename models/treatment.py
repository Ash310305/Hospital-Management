from datetime import time
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class TreatmentType(str, Enum):
    MEDICATION = "medication"
    SURGERY_PROCEDURE = "surgery_procedure"
    PHYSIOTHERAPY = "physiotherapy"
    LIFESTYLE_DIETARY = "lifestyle_dietary"
    OBSERVATION = "observation"


class TreatmentStatus(str, Enum):
    PLANNED = "planned"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"
    ON_HOLD = "on_hold"


class Treatment(BaseModel):
    doctor_id: str = Field(..., min_length=1, description="ID of the prescribing doctor")
    patient_id: str = Field(..., min_length=1, description="ID of the patient")
    treatment_type: TreatmentType
    treatment_status: TreatmentStatus = TreatmentStatus.PLANNED
    medicine_name: List[str] = Field(
        default_factory=list, description="List of prescribed medicine names"
    )
    dosage: List[time] = Field(
        default_factory=list, description="Dosage times in HH:MM:SS format"
    )
    frequency: List[int] = Field(
        default_factory=list, description="Frequency counts corresponding to each item"
    )
    duration_days: int = Field(..., ge=1, description="Treatment duration in days")
    instructions: str = Field(default="", description="General administration instructions")

    @field_validator("dosage", mode="before")
    @classmethod
    def parse_dosage_times(cls, value):
        """Accept datetime.time objects or HH:MM:SS / HHMMSS strings."""
        if not isinstance(value, list):
            return value
        parsed = []
        for item in value:
            if isinstance(item, time):
                parsed.append(item)
            elif isinstance(item, str):
                cleaned = item.strip()
                if len(cleaned) == 6 and cleaned.isdigit():
                    cleaned = f"{cleaned[0:2]}:{cleaned[2:4]}:{cleaned[4:6]}"
                parsed.append(time.fromisoformat(cleaned))
            else:
                parsed.append(item)
        return parsed

    @field_validator("frequency")
    @classmethod
    def validate_positive_frequency(cls, frequencies: List[int]) -> List[int]:
        for freq in frequencies:
            if freq < 1:
                raise ValueError("Each frequency value must be at least 1")
        return frequencies

    @model_validator(mode="after")
    def validate_array_lengths(self) -> "Treatment":
        """Ensure medicine_name, dosage, and frequency stay aligned when populated."""
        lengths = {
            len(self.medicine_name),
            len(self.dosage),
            len(self.frequency),
        }
        # Allow empty arrays if no medicines are specified, or matching lengths when provided
        if len(lengths) > 1:
            raise ValueError(
                "medicine_name, dosage, and frequency arrays must have the same length"
            )
        return self

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        data = self.model_dump()
        data["treatment_type"] = self.treatment_type.value
        data["treatment_status"] = self.treatment_status.value
        data["dosage"] = [t.strftime("%H:%M:%S") for t in self.dosage]
        return data

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Treatment"]:
        """Instantiate a Treatment model from a MongoDB document."""
        if not doc:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        return cls(**doc)


# Example usage
if __name__ == "__main__":
    sample_treatment = Treatment(
        doctor_id="doc_201",
        patient_id="pat_101",
        treatment_type=TreatmentType.MEDICATION,
        treatment_status=TreatmentStatus.ONGOING,
        medicine_name=["Amoxicillin 500mg", "Pantoprazole 40mg"],
        dosage=["08:00:00", "20:00:00"],
        frequency=[1, 1],
        duration_days=7,
        instructions="Take after meals with a full glass of water.",
    )

    print("Validated Model:", sample_treatment)
    print("MongoDB Payload:", sample_treatment.to_mongo_dict())