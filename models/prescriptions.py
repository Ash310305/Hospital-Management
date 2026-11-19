from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Treatment(BaseModel):
    doctor_id: str = Field(..., min_length=1, description="ID of the doctor")
    patient_id: str = Field(..., min_length=1, description="ID of the patient")
    medicines: List[str] = Field(
        default_factory=list, description="List of prescribed medicines"
    )
    machines: List[str] = Field(
        default_factory=list, description="List of medical machines or devices used"
    )

    def to_mongo_dict(self) -> dict:
        """Convert model to a BSON-compatible dictionary for MongoDB insertion."""
        data = self.model_dump()
        data["updated_at"] = datetime.utcnow()
        return data

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Treatment"]:
        """Instantiate a Treatment model from a MongoDB document."""
        if not doc:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        doc.pop("updated_at", None)
        return cls(**doc)


# Example usage
if __name__ == "__main__":
    sample_treatment = Treatment(
        doctor_id="doc_201",
        patient_id="pat_101",
        medicines=["Paracetamol 500mg", "Azithromycin 250mg"],
        machines=["Pulse Oximeter", "Nebulizer"],
    )

    print("Validated Model:", sample_treatment)
    print("MongoDB Payload:", sample_treatment.to_mongo_dict())