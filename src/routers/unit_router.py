from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from starlette import status

from src.dependencies import get_revision_pending_units, get_schema_by_id, get_unit_by_internal_id
from src.database import models as mdl
from src.feecc_workbench.exceptions import StateForbiddenError
from src.feecc_workbench.states import State
from src.unit.unit_utils import Unit
from src.feecc_workbench.WorkBench import Workbench as WORKBENCH

router = APIRouter(
    prefix="/unit",
    tags=["unit"],
)


@router.post("/new/{schema_id}", response_model=mdl.UnitOut)
async def create_unit(schema: mdl.ProductionSchema = Depends(get_schema_by_id)) -> mdl.UnitOut:  # noqa: B008
    """handle new Unit creation"""
    try:
        if not schema.is_allowed(WORKBENCH.employee.position):
            raise ValueError("schema is not allowed")
        unit: Unit = await WORKBENCH.create_new_unit(schema)
        logger.info(f"Initialized new unit with internal ID {unit.internal_id}")
        return mdl.UnitOut(
            status_code=status.HTTP_200_OK,
            detail="New unit created successfully",
            unit_internal_id=unit.internal_id,
        )

    except Exception as e:
        logger.error(f"Exception occurred while creating new Unit: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get("/{unit_internal_id}/info", response_model=mdl.UnitInfo)
def get_unit_data(unit: Unit = Depends(get_unit_by_internal_id)) -> mdl.UnitInfo:  # noqa: B008
    """return data for a Unit with matching ID"""
    return mdl.UnitInfo(
        status_code=status.HTTP_200_OK,
        detail="Unit data retrieved successfully",
        unit_internal_id=unit.internal_id,
        unit_status=unit.status,
        unit_operation_stages_completed=[
            mdl.BiographyStage(
                stage_name=stage.name
            )
            for stage in unit.operation_stages
            if stage.completed
        ],
        unit_operation_stages_pending=[
            mdl.BiographyStage(
                stage_name=stage.name
            )
            for stage in unit.operation_stages
            if not stage.completed
        ],
        unit_components=unit.components_ids or None,
        schema_id=unit.schema_id,
    )


@router.get("/pending_revision", response_model=mdl.UnitOutPending)
def get_revision_pending(
    units: list[dict[str, str]] = Depends(get_revision_pending_units)  # noqa: B008
) -> mdl.UnitOutPending:
    """return all units staged for revision"""
    return mdl.UnitOutPending(
        status_code=status.HTTP_200_OK,
        detail=f"{len(units)} units awaiting revision.",
        units=[
            mdl.UnitOutPendingEntry(unit_internal_id=unit["internal_id"], unit_name=unit["unit_name"]) for unit in units
        ],
    )


@router.post("/upload", response_model=mdl.GenericResponse)
async def unit_upload_record() -> mdl.GenericResponse:
    """handle Unit lifecycle end"""
    try:
        if WORKBENCH.employee is None:
            raise StateForbiddenError("Employee is not authorized on the workbench")

        await WORKBENCH.upload_unit_passport()
        return mdl.GenericResponse(
            status_code=status.HTTP_200_OK, detail=f"Uploaded data for unit {WORKBENCH.unit.internal_id}"
        )

    except Exception as e:
        message: str = f"Can't handle unit upload. An error occurred: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e


@router.post("/assign-component/{unit_internal_id}", response_model=mdl.GenericResponse)
async def assign_component(unit: Unit = Depends(get_unit_by_internal_id)) -> mdl.GenericResponse:  # noqa: B008
    """assign a unit as a component to the composite unit"""
    if WORKBENCH.state != State.GATHER_COMPONENTS_STATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Component assignment can only be done while the workbench is in state 'GatherComponents'",
        )

    try:
        await WORKBENCH.assign_component_to_unit(unit)
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Component has been assigned")

    except Exception as e:
        message: str = f"An error occurred during component assignment: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e
