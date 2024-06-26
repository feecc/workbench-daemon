from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from starlette import status

from src.config import CONFIG
from src.dependencies import get_employee_by_card_id, get_employee_by_username, identify_sender
from src.database import models as mdl
from src.employee.Employee import Employee
from src.employee.employee_wrapper import EmployeeWrapper
from src.feecc_workbench.Messenger import messenger
from src.feecc_workbench.translation import translation
from src.feecc_workbench.exceptions import StateForbiddenError, EmployeeNotFoundError
from src.feecc_workbench.WorkBench import Workbench as WORKBENCH


router = APIRouter(
    prefix="/employee",
    tags=["employee"],
)


@router.post("/info", response_model=mdl.EmployeeOut)
def get_employee_data(
    employee: mdl.EmployeeWCardModel = Depends(get_employee_by_card_id),  # noqa: B008
) -> mdl.EmployeeOut:
    """return data for an Employee with matching ID card"""
    return mdl.EmployeeOut(
        status_code=status.HTTP_200_OK, detail="Employee retrieved successfully", employee_data=employee
    )


@router.post("/login-creds", response_model=mdl.EmployeeOut)
def log_in_creds(employee: mdl.EmployeeWCardModel = Depends(get_employee_by_username)) -> mdl.EmployeeOut:
    try:
        WORKBENCH.log_in(
            Employee(
                rfid_card_id=employee.rfid_card_id,
                name=employee.name,
                position=employee.position,
                username=employee.username,
            )
        )
        return mdl.EmployeeOut(
            status_code=status.HTTP_200_OK, detail="Employee logged in successfully", employee_data=employee
        )

    except StateForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post("/log-in", response_model=mdl.EmployeeOut)
def log_in_employee(
    employee: mdl.EmployeeWCardModel = Depends(get_employee_by_card_id),  # noqa: B008
) -> mdl.EmployeeOut:
    """handle logging in the Employee at a given Workbench"""
    try:
        WORKBENCH.log_in(
            Employee(
                rfid_card_id=employee.rfid_card_id,
                name=employee.name,
                position=employee.position,
                username=employee.username,
            )
        )
        return mdl.EmployeeOut(
            status_code=status.HTTP_200_OK, detail="Employee logged in successfully", employee_data=employee
        )

    except StateForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post("/handle-rfid-event", response_model=mdl.GenericResponse)
async def handle_rfid_event(event: mdl.HidEvent) -> mdl.GenericResponse:
    try:
        if event.name != "rfid_reader":
            raise KeyError(f"Unknown sender: {event.name}")

        logger.debug(f"Handling RFID event. String: {event.string}")

        if not CONFIG.workbench.login:
            return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected")

        if WORKBENCH.employee is not None:
            WORKBENCH.log_out()
            return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected")

        try:
            employee: Employee = EmployeeWrapper.get_employee_by_card_id(card_id=event.string)
        except EmployeeNotFoundError as e:
            messenger.warning(translation("NoEmployee"))
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

        WORKBENCH.log_in(employee)
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Hid event has been handled as expected")

    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post("/log-out", response_model=mdl.GenericResponse)
def log_out_employee() -> mdl.GenericResponse:
    """handle logging out the Employee at a given Workbench"""
    try:
        WORKBENCH.log_out()
        if WORKBENCH.employee is not None:
            raise ValueError("Unable to logout employee")
        return mdl.GenericResponse(status_code=status.HTTP_200_OK, detail="Employee logged out successfully")

    except Exception as e:
        message: str = f"An error occurred while logging out the Employee: {e}"
        logger.error(message)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from e
