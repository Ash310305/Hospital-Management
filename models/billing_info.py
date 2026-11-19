from datetime import datetime, time as Time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class PaymentMode(str, Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    NET_BANKING = "net_banking"
    INSURANCE = "insurance"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class Payment(BaseModel):
    patient_id: str = Field(..., min_length=1, description="ID of the patient")
    doctor_id: str = Field(..., min_length=1, description="ID of the doctor")
    payment_mode: PaymentMode = Field(..., description="Mode of payment")
    amount: int = Field(..., ge=0, description="Payment amount as an integer")
    time: Time = Field(..., description="Transaction time in HH:MM:SS or HHMMSS format")
    status: PaymentStatus = Field(
        default=PaymentStatus.PENDING, description="Payment transaction status"
    )

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
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "payment_mode": self.payment_mode.value,
            "amount": self.amount,
            "time": self.time.strftime("%H:%M:%S"),
            "status": self.status.value,
            "updated_at": datetime.now(),
        }

    @classmethod
    def from_mongo_dict(cls, doc: dict) -> Optional["Payment"]:
        """Instantiate a Payment model from a MongoDB document."""
        if not doc:
            return None
        parsed = dict(doc)
        parsed.pop("_id", None)
        parsed.pop("updated_at", None)
        return cls(**parsed)


# Example usage
if __name__ == "__main__":
    sample_payment = Payment(
        patient_id="pat_101",
        doctor_id="doc_201",
        payment_mode=PaymentMode.UPI,
        amount=1200,
        time="220500",
        status=PaymentStatus.COMPLETED,
    )

    print("Validated Model:", sample_payment)
    print("MongoDB Payload:", sample_payment.to_mongo_dict())
    