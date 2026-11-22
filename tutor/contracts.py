from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


Locale = Literal["zh-Hans", "en"]
QuestionFormat = Literal["choice", "text", "tex"]
ApiReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
CodexReasoningEffort = Literal[ApiReasoningEffort, "ultra"]


class ModelCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["codex_cli", "api"]
    apiBaseUrl: Annotated[str, StringConstraints(max_length=1600)] | None = None
    apiKey: Annotated[SecretStr, Field(max_length=4096)] = SecretStr("")


class ModelEffortsRequest(ModelCatalogRequest):
    provider: Literal["api"]
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class RuntimeSettings(ModelCatalogRequest):
    codexModel: Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)] | None = None
    codexReasoningEffort: CodexReasoningEffort | None = None
    apiModel: Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)] | None = None
    apiReasoningEffort: ApiReasoningEffort | None = None


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Packet(Contract):
    locale: Locale


class Source(Contract):
    materialId: str
    page: int


class Topic(Contract):
    key: str
    parentKey: str | None
    title: str
    coverage: Literal["supported", "missing", "prerequisite"]
    explanation: str
    opening: str
    sources: list[Source]


class Outline(Packet):
    topics: list[Topic]


class Hypothesis(Contract):
    key: str
    description: str
    evidence: str


class Dialogue(Packet):
    topicKey: str | None
    message: str
    sources: list[Source]
    hypothesis: Hypothesis | None


class TopicSelection(Packet):
    topicKey: str | None


class Option(Contract):
    id: str
    text: str
    diagnostic: Literal["same_gap", "other_error", "ambiguous", "none"]


class AnswerField(Contract):
    id: str
    label: str
    accepted: list[str]


class Question(Packet):
    format: QuestionFormat
    prompt: str
    options: list[Option]
    fields: list[AnswerField]
    correctOptionId: str | None
    requiresReason: bool
    rubric: str
    solution: str
    sources: list[Source]


class Evaluation(Packet):
    correctness: Literal["correct", "incorrect", "uncertain"]
    evidenceType: Literal["same_gap", "other_error", "demonstrated", "insufficient"]
    evidence: str
    feedback: str
    otherHypothesis: Hypothesis | None


class QuestionAudit(Packet):
    valid: bool


class Translation(Packet):
    texts: list[str]
