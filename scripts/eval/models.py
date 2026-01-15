import re
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator

CommitHexString = Annotated[
    str, BeforeValidator(lambda x: x if re.match(r"^[a-f0-9]{40}$", x) else None)
]


class AIxCCChallengeBlobInfo(BaseModel):
    harness_name: str
    sanitizer_name: str
    blob: str


class AIxCCChallengeDeltaMode(BaseModel):
    type: str = "delta"
    base_ref: CommitHexString
    delta_ref: CommitHexString


class AIxCCChallengeFullMode(BaseModel):
    type: str = "full"
    base_ref: CommitHexString


class AIxCCChallengeProjectDetection(BaseModel):
    vulnerability_identifier: str
    project_name: str
    blobs: list[AIxCCChallengeBlobInfo] = []
    mode: AIxCCChallengeFullMode | AIxCCChallengeDeltaMode
    sarif_report: Optional[str] = None


class TarballMetadata(BaseModel):
    task_id: str
    project_name: str
    focus: str
    bundle: Optional[list[dict[str, Any]]] = None
    pov: list[dict[str, Any]]


class TaskMetadata(BaseModel):
    task_id: str
    project_name: str
    focus: str
    detections: list[str]
    oss_fuzz_directory: str
    mode: str
    source_directory: str
    diff_commit: Optional[str] = None
    base_commit: str
