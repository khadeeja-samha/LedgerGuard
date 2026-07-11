from pydantic import BaseModel


class UploadRequest(BaseModel):
    source_code: str
