import json

from time import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.feecc_workbench.states import State


class GenericResponse(BaseModel):
    status_code: int
    detail: str | None


class OperatorStartResponse(GenericResponse):
    """Return 304 to front to ask for manual input"""

    license_plate: bool = False


class ManualInput(BaseModel):
    license_plate: str | None = None
    weight: str | None = None


class WorkbenchExtraDetails(BaseModel):
    additional_info: dict[str, str]


class OperationStageData(BaseModel):
    stage_data: dict[str, Any] | None = None
    premature_ending: bool = False


class EmployeeModel(BaseModel):
    name: str
    position: str


class EmployeeWCardModel(EmployeeModel):
    rfid_card_id: str | None
    username: str | None


class AdditionalDetail:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)

    def to_json(self):
        return json.dumps(self.__dict__)


class WorkbenchOut(BaseModel):
    state: State
    employee_logged_in: bool
    employee: EmployeeModel | None
    operation_ongoing: bool
    unit_internal_id: str | None
    unit_status: str | None
    unit_biography: list[str] | None
    unit_components: dict[str, str | None] | None


class EmployeeOut(GenericResponse):
    employee_data: EmployeeWCardModel | None


class EmployeeID(BaseModel):
    employee_rfid_card_no: str


class EmployeeCreds(BaseModel):
    employee_username: str
    employee_password: str


class UnitOut(GenericResponse):
    unit_internal_id: str | None


class UnitOutPendingEntry(BaseModel):
    unit_internal_id: str
    unit_name: str


class UnitOutPending(GenericResponse):
    units: list[UnitOutPendingEntry]


class BiographyStage(BaseModel):
    stage_name: str


class UnitInfo(UnitOut):
    unit_status: str
    unit_operation_stages_completed: list[BiographyStage]
    unit_operation_stages_pending: list[BiographyStage]
    unit_components: list[str] | None = None
    schema_id: str


class HidEvent(BaseModel):
    string: str
    name: str
    timestamp: float = Field(default_factory=time)
    info: dict[str, int | str] = {}


class ProductionSchemaStage(BaseModel):
    name: str
    type: str | None = None  # noqa: A003
    description: str | None = None
    equipment: list[str] | None = None
    workplace: str | None = None
    duration_seconds: int | None = None


class ProductionSchema(BaseModel):
    schema_id: str = Field(default_factory=lambda: uuid4().hex)
    schema_name: str
    schema_print_name: str | None = None
    schema_stages: list[ProductionSchemaStage]
    components_schema_ids: list[str] | None = None
    parent_schema_id: str | None = None
    schema_type: str | None = None
    erp_metadata: dict[str, str] | None = None
    allowed_positions: list[str] | None = None

    @property
    def is_composite(self) -> bool:
        return self.components_schema_ids is not None

    @property
    def is_a_component(self) -> bool:
        return self.parent_schema_id is not None

    @property
    def print_name(self) -> str:
        if self.schema_print_name is None:
            return self.schema_name
        return self.schema_print_name

    def is_allowed(self, position: str) -> bool:
        if not self.allowed_positions:
            return True
        if position in self.allowed_positions:
            return True
        return False


class ProductionSchemaResponse(GenericResponse):
    production_schema: ProductionSchema


class SchemaListEntry(BaseModel):
    schema_id: str
    schema_name: str
    included_schemas: list[dict[str, Any]] | None


class SchemasList(GenericResponse):
    available_schemas: list[SchemaListEntry]
