from datetime import date as Date, datetime, time as Time
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Appointment(BaseModel):
    doctor_id: str = Field(..., min_length=1, description="ID of the doctor")
    patient_id: str = Field(..., min_length=1, description="ID of the patient")
    date: Date = Field(..., description="Date in DD-MM-YYYY format")
    time: Time = Field(..., description="Time in HH:MM:SS or HHMMSS format")
    fees: int = Field(..., ge=0, description="Consultation or service fees in integer")

    @field_validator("date", mode="before")
    @classmethod
    def parse_dd_mm_yyyy(cls, value):
        """Accept date objects or DD-MM-YYYY / DD/MM/YYYY strings."""
        if isinstance(value, Date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            cleaned = value.strip().replace("/", "-")
            return datetime.strptime(cleaned, "%d-%m-%Y").date()
        return value

    @field_validator("time", mode="before")
    @classmethod
    def parse_hhmmss(cls, value):
        """Accept time objects or HH:MM:SS / HHMMSS strings."""
        if isinstance(value, Time):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if len(cleaned) == 6 and cleaned.isdigit():
                cleaned = f"{cleaned[0:2]}:{cleaned[2:4]}:{cleaned[4:6]}"
            return Time.fromisoformat(cleaned)
        return value

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        return {
            "doctor_id": self.doctor_id,
            "patient_id": self.patient_id,
            "date": datetime.combine(self.date, datetime.min.time()),
            "time": self.time.strftime("%H:%M:%S"),
            "fees": self.fees,
        }

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Appointment"]:
        """Instantiate an Appointment model from a MongoDB document."""
        if not doc:
            return None
        parsed = dict(doc)
        parsed.pop("_id", None)
        if isinstance(parsed.get("date"), datetime):
            parsed["date"] = parsed["date"].date()
        return cls(**parsed)


# Example usage
if __name__ == "__main__":
    sample = Appointment(
        doctor_id="doc_201",
        patient_id="pat_101",
        date="19-11-2026",
        time="143000",
        fees=500,
    )

    print("Validated Model:", sample)
    print("Formatted DD-MM-YYYY:", sample.date.strftime("%d-%m-%Y"))
    print("MongoDB Payload:", sample.to_mongo_dict())