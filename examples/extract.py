from vehicle_document_ai import VehicleDocumentReader

# Local path only; this never downloads a model or sends the image anywhere.
result = VehicleDocumentReader().extract("vehicle.jpg")
print(result.model_dump_json(indent=2))  # Sensitive output: do not send to application logs.
