from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    """Base class for validated API boundary models."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ApiRequest(ContractModel):
    """Newline-delimited JSON request sent to the PyHerdr server."""

    id: str = "request"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "method")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        """Validate non-empty request identifiers and methods."""
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("value cannot be empty")
        return normalized


class ApiError(ContractModel):
    """Structured API error payload."""

    code: str
    message: str

    @field_validator("code", "message")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        """Validate non-empty error fields."""
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("value cannot be empty")
        return normalized


class ApiResponse(ContractModel):
    """Newline-delimited JSON response returned by the PyHerdr server."""

    id: str
    result: dict[str, Any] | None = None
    error: ApiError | None = None

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        """Validate non-empty response identifiers."""
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("response id cannot be empty")
        return normalized

    @model_validator(mode="after")
    def _has_result_or_error(self) -> ApiResponse:
        """Ensure responses carry either a result or an error."""
        if self.result is None and self.error is None:
            raise ValueError("response must include result or error")
        if self.result is not None and self.error is not None:
            raise ValueError("response cannot include both result and error")
        return self
