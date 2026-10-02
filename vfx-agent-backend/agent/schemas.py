from dataclasses import dataclass
from typing import TypedDict, Annotated, Sequence, Literal, Union
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr


ParameterValue = Union[StrictBool, StrictInt, StrictFloat, StrictStr]


class ReferenceRequest(BaseModel):
    """One explicitly mentioned saved Effect and the aspect to reuse."""

    model_config = ConfigDict(extra="forbid")

    effect_id: str = Field(min_length=1)
    reference_intent: str = Field(min_length=1)


class ReferenceSource(BaseModel):
    """Authorized source passed from storage to EffectAnalyzer."""

    model_config = ConfigDict(extra="forbid")

    effect_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_intent: str = Field(min_length=1)


class ReferenceFinding(BaseModel):
    """One exact source excerpt and its intended reuse."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=2000)
    usage: str = Field(min_length=1, max_length=500)


class ReferenceEvidence(BaseModel):
    """Validated internal evidence for one referenced Effect."""

    model_config = ConfigDict(extra="forbid")

    effect_id: str = Field(min_length=1)
    reference_intent: str = Field(min_length=1)
    findings: list[ReferenceFinding] = Field(min_length=1, max_length=5)


class ReferenceSafeSummary(BaseModel):
    """Code-free description safe to expose to MainAgent and product users."""

    model_config = ConfigDict(extra="forbid")

    effect_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class GenerationBrief(BaseModel):
    """Code-free requirement compiled by MainAgent for CodeAgent."""

    model_config = ConfigDict(extra="forbid")

    user_description: str = Field(min_length=1)
    requested_name: str | None = None
    references: list[ReferenceRequest] = Field(default_factory=list)
    parameter_updates: dict[str, ParameterValue] = Field(default_factory=dict)


class ClarificationOption(BaseModel):
    """Product option backed by a complete executable generation brief."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    brief: GenerationBrief


class RespondAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["respond"] = "respond"
    message: str = Field(min_length=1)


class ClarifyAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["clarify"] = "clarify"
    question: str = Field(min_length=1)
    options: list[ClarificationOption] = Field(min_length=2, max_length=4)


class GenerateAction(GenerationBrief):
    action: Literal["generate"] = "generate"


class UpdateEffectAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["update_effect"] = "update_effect"
    requested_name: str | None = None
    parameter_updates: dict[str, ParameterValue] = Field(default_factory=dict)


class InspectEffectsAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["inspect_effects"] = "inspect_effects"
    effect_ids: list[str] = Field(min_length=1, max_length=3)
    question: str = Field(min_length=1)


MainAgentAction = Annotated[
    Union[
        RespondAction,
        ClarifyAction,
        GenerateAction,
        UpdateEffectAction,
        InspectEffectsAction,
    ],
    Field(discriminator="action"),
]


class EffectMention(BaseModel):
    """Frontend-selected saved Effect reference."""

    effect_id: str
    display_name: str


@dataclass
class CodeAgentResult:
    """Explicit CodeAgent delivery contract for success or failure.

    submitted means code was delivered. failed includes a reason and may retain the latest
    validated code as a draft fallback.
    """
    status: str                        # "submitted" | "failed"
    code: str = ""                     # Submitted code, present only on success.
    reason: str = ""                   # Failure reason for retry or user feedback.
    last_validated_code: str = ""      # Latest validated code for draft fallback.
    effect_id: str = ""                # Internal ID for this CodeAgent run.
    injected_reference_ids: list[str] | None = None  # Saved Effects injected as verified evidence.

class AgentState(TypedDict):
    """MainAgent graph state."""

    # Inputs supplied with each request.
    messages: Annotated[Sequence[BaseMessage], add_messages]
    video_id: str
    user_input: str
    effect_id: str                         # Stable effect workspace ID.
    operation: Literal["create", "edit"]  # Derived from backend effect storage.
    effect_mentions: list[dict]             # Active mentions resolved by the backend.
    pinned_joints: dict[str, str]            # Trusted editor aliases mapped to Pose joints.
    editor_context: dict                     # Trusted editor controls fixed for this run.
    required_control_ids: list[str]          # Controls inherited from original user intent.
    main_action: dict                       # Current validated MainAgent action.
    action_name: str                        # Current action discriminator.
    action_result: dict                     # Code-controlled execution result.
    action_error: str                       # Deterministic schema or execution failure.
    inspection_count: int                   # Read-only inspections performed this turn.
    pending_options: dict[str, dict]         # One-use option ID to generation brief mapping.
    forced_action: dict                     # Stored option action executed without the model.
    explicit_parameter_updates: dict[str, ParameterValue]

    # Cross-turn context restored for the current effect.
    effect_messages: list[dict]            # Conversation history [{role, content}].
    prev_code: str                         # Existing code supplied for edits.

    # Cross-effect context supplied by the frontend.
    effect_list: list[dict]                # Effect summaries [{id, name, impl_note}].

    injected_reference_ids: list[str]      # Saved Effect IDs injected as verified evidence.

    # Intermediate outputs populated by invoke_code_agent.
    code: str                              # Current code.
    params: str                            # Current params JSON.
    effect_name: str                       # Effect name.
    code_status: str                       # Final CodeAgent status.
    failure_reason: str                    # Final failure reason.
    last_validated_code: str               # Latest validated code for draft fallback.


class CodeAgentState(TypedDict):
    """CodeAgent graph state."""

    # Inputs.
    video_id: str
    user_description: str                  # Requirement constructed by MainAgent.
    prev_code: str                         # Existing code for edits, empty for new effects.
    max_soft_fixes: int                    # Maximum failed soft reviews before bypass.
    max_hard_fixes: int                    # Maximum failed hard-validation submissions.

    # Read-only context supplied by MainAgent.
    effect_list: list[dict]                # Cross-effect context.
    pose_stats: dict                       # Pose-data statistics.
    editor_context: dict                   # Trusted editor controls fixed for this run.
    required_control_ids: list[str]        # Controls explicitly named in the requirement.

    # Generation process.
    todo: list[dict]                       # Execution plan [{content, status}].
    code: str                              # submit_code output.
    last_validated_code: str               # Latest validated code for fallback.
    validate_result: dict                  # validate output.
    soft_fix_count: int                    # Number of failed soft reviews for the current code version.
    hard_fix_count: int                    # Number of failed hard-validation submissions.
    soft_validation_bypassed: bool         # Whether soft review exhausted and hard submission is allowed.
    rounds_since_todo: int                 # Rounds since update_todo for reminder logic.
    submitted: bool                        # Whether submit_code succeeded.

    messages: Annotated[Sequence[BaseMessage], add_messages]
