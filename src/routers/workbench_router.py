import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.dependencies import get_schema_by_id, get_unit_by_internal_id, identify_sender
from src.database import models as mdl
from src.prod_schema.prod_schema_wrapper import ProdSchemaWrapper
from src.employee.employee_wrapper import EmployeeWrapper
from src.employee.Employee import Employee
from src.feecc_workbench.exceptions import EmployeeNotFoundError, ManualInputNeeded
from src.feecc_workbench.Messenger import messenger
from src.feecc_workbench.states import State
from src.feecc_workbench.translation import translation
from src.unit.unit_utils import Unit
from src.feecc_workbench.WorkBench import STATE_SWITCH_EVENT
from src.feecc_workbench.WorkBench import Workbench as WORKBENCH
from src.config import CONFIG

router = APIRouter(
    prefix="/workbench",
    tags=["workbench"],
)


def get_workbench_status_data() -> mdl.WorkbenchOut:
    unit = WORKBENCH.unit
    return mdl.WorkbenchOut(
        state=WORKBENCH.state.value,
        employee_logged_in=bool(WORKBENCH.employee),
        employee=WORKBENCH.employee.data if WORKBENCH.employee else None,
        operation_ongoing=WORKBENCH.state.value == State.PRODUCTION_STAGE_ONGOING_STATE.value,
        unit_internal_id=unit.internal_id if unit else None,
        unit_status=unit.status if unit else None,
        unit_biography=[stage.name for stage in unit.operation_stages] if unit else None,
        unit_components=unit.assigned_components() if unit else None,
    )


@router.get("/status", response_model=mdl.WorkbenchOut, deprecated=True)
def get_workbench_status() -> mdl.WorkbenchOut:
    """
    handle providing status of the given Workbench

    DEPRECATED: Use SSE instead
    """
    return get_workbench_status_data()


async def state_update_generator(event: asyncio.Event) -> AsyncGenerator[str, None]:
    """State update event generator for SSE streaming"""
    logger.info("SSE connection to state streaming endpoint established.")

    try:
        while True:
            yield get_workbench_status_data().model_dump_json()
            logger.debug("State notification sent to the SSE client")
            event.clear()
            await event.wait()

    except asyncio.CancelledError as e:
        logger.info(f"SSE connection to state streaming endpoint closed. {e}")


@router.get("/status/stream")
async def stream_workbench_status() -> EventSourceResponse:
    """Send updates on the workbench state into an SSE stream"""
    status_stream = state_update_generator(STATE_SWITCH_EVENT)
    return EventSourceResponse(status_stream)


@router.post("/assign-unit/{unit_internal_id}", response_model=mdl.GenericResponse)
def assign_unit(unit: Unit = Depends(get_unit_by_internal_id)) -> mdl.GenericResponse:  # noqa: B008
    """assign the provided unit to the workbench"""
    try:
        WORKBENCH.assign_unit(unit)
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail=f"Unit {unit.internal_id} has been assigned")

    except Exception as e:
        message: str = f"An error occurred during unit assignment: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e


@router.post("/remove-unit", response_model=mdl.GenericResponse)
def remove_unit() -> mdl.GenericResponse:
    """remove the unit from the workbench"""
    try:
        WORKBENCH.remove_unit()
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Unit has been removed")

    except Exception as e:
        message: str = f"An error occurred during unit removal: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e


@router.post("/start-operation")
async def start_operation(
    workbench_details: mdl.WorkbenchExtraDetails, manual_input: mdl.ManualInput | None = None
) -> mdl.GenericResponse:
    """handle start recording operation on a Unit"""
    try:
        await WORKBENCH.start_operation(workbench_details.additional_info, manual_input)
        unit = WORKBENCH.unit
        message: str = f"Started operation '{unit.next_pending_operation.name}' on Unit {unit.internal_id}"
        logger.info(message)
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail=message)
    except ManualInputNeeded as e:
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content=e.args)
    except Exception as e:
        message = f"Couldn't handle request. An error occurred: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e


@router.post("/end-operation", response_model=mdl.GenericResponse)
async def end_operation(workbench_data: mdl.OperationStageData) -> mdl.GenericResponse:
    """handle end recording operation on a Unit"""
    try:
        await WORKBENCH.end_operation(workbench_data.stage_data, workbench_data.premature_ending)
        unit = WORKBENCH.unit
        message: str = f"Ended current operation on unit {unit.internal_id}"
        logger.info(message)
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail=message)

    except Exception as e:
        message = f"Couldn't handle end record request. An error occurred: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e


@router.get("/production-schemas/names", response_model=mdl.SchemasList)
def get_schemas() -> mdl.SchemasList:
    """get all available schemas"""
    all_schemas = {
        schema.schema_id: schema for schema in ProdSchemaWrapper.get_all_schemas(WORKBENCH.employee.position)
    }
    handled_schemas = set()

    def get_schema_list_entry(schema: mdl.ProductionSchema) -> mdl.SchemaListEntry:
        nonlocal all_schemas, handled_schemas
        included_schemas: list[mdl.SchemaListEntry] | None = (
            [get_schema_list_entry(all_schemas[s_id]) for s_id in schema.components_schema_ids]
            if schema.is_composite
            else None
        )
        handled_schemas.add(schema.schema_id)
        return mdl.SchemaListEntry(
            schema_id=schema.schema_id,
            schema_name=schema.schema_name,
            included_schemas=included_schemas,
        )

    available_schemas = [
        get_schema_list_entry(schema)
        for schema in sorted(all_schemas.values(), key=lambda s: bool(s.is_composite), reverse=True)
        if schema.schema_id not in handled_schemas
    ]
    available_schemas.sort(key=lambda le: len(le.schema_name))

    return mdl.SchemasList(
        status_code=status.HTTP_200_OK,
        detail=f"Gathered {len(all_schemas)} schemas",
        available_schemas=available_schemas,
    )


@router.get("/production-schemas/{schema_id}", response_model=mdl.ProductionSchemaResponse)
async def get_schema(
    schema: mdl.ProductionSchema = Depends(get_schema_by_id),  # noqa: B008
) -> mdl.ProductionSchemaResponse:
    """get schema by its ID"""
    return mdl.ProductionSchemaResponse(
        status_code=status.HTTP_200_OK,
        detail=f"Found schema {schema.schema_id}",
        production_schema=schema,
    )


@router.post("/handle-barcode-event", response_model=mdl.GenericResponse)
async def handle_barcode_event(event: mdl.HidEvent) -> mdl.GenericResponse:
    """Handle HID event produced by the barcode reader"""
    try:
        if event.name != "barcode_reader":
            raise KeyError(f"Unknown sender: {event.name}")

        logger.debug(f"Handling BARCODE event. String: {event.string}")

        if WORKBENCH.state == State.PRODUCTION_STAGE_ONGOING_STATE:
            await WORKBENCH.end_operation()
            return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected")

        unit = get_unit_by_internal_id(event.string)

        match WORKBENCH.state:
            case State.AUTHORIZED_IDLING_STATE:
                WORKBENCH.assign_unit(unit)
            case State.UNIT_ASSIGNED_IDLING_STATE:
                if WORKBENCH.unit is not None and WORKBENCH.unit.unit_id == unit.uuid:
                    messenger.info(translation("UnitOnWorkbench"))
                    return mdl.GenericResponse(
                        status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected"
                    )
                WORKBENCH.remove_unit()
                WORKBENCH.assign_unit(unit)
            case State.GATHER_COMPONENTS_STATE:
                await WORKBENCH.assign_component_to_unit(unit)
            case _:
                logger.error(f"Received input {event.string}. Ignoring event since no one is authorized.")
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected")

    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
