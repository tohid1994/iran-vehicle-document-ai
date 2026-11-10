"""Versioned public contract. Confidence is reserved for calibrated probabilities."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Box(Contract):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TextRegion(Contract):
    text: str
    box: Box
    engineScore: float | None = Field(default=None, ge=0, le=100)


class FieldEvidence(Contract):
    rawValue: str | None = None
    sourceReadings: list[str] = Field(default_factory=list)
    normalizedValue: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    engineScore: float | None = Field(default=None, ge=0, le=100)
    boundingBox: Box | None = None
    extractionMethod: str = "missing"
    validationStatus: Literal["missing", "valid", "invalid", "unverified", "ambiguous"] = "missing"
    requiresReview: bool = True


class Vehicle(Contract):
    brand: str | None = None
    model: str | None = None
    year: str | None = None
    color: str | None = None
    fuelType: str | None = None
    vehicleType: str | None = None
    origin: Literal["DOMESTIC", "FOREIGN"] | None = None
    vin: str | None = None
    chassisNumber: str | None = None
    engineNumber: str | None = None
    plate: str | None = None


class Owner(Contract):
    firstName: str | None = None
    lastName: str | None = None
    fullName: str | None = None
    nationalId: str | None = None


class Quality(Contract):
    width: int
    height: int
    blurVariance: float
    brightness: float
    contrast: float
    warnings: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    # OCR boxes refer to this processed coordinate system, never the original photo.
    coordinateSpace: Literal["processed_image"] = "processed_image"
    originalToProcessed: list[list[float]]


class Analysis(Contract):
    schemaVersion: Literal["1.0"] = "1.0"
    quality: Quality
    regions: list[TextRegion]
    engine: str
    processingTimeMs: int


class Extraction(Contract):
    schemaVersion: Literal["1.0"] = "1.0"
    success: bool
    transcriptionComplete: bool = False
    documentType: Literal["IRAN_VEHICLE_REGISTRATION"] | None = None
    vehicle: Vehicle = Field(default_factory=Vehicle)
    owner: Owner = Field(default_factory=Owner)
    fields: dict[str, FieldEvidence]
    confidence: float | None = None
    requiresReview: bool = True
    reviewFields: list[str]
    warnings: list[str]
    quality: Quality
    processingTimeMs: int
