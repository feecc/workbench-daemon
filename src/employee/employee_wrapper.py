from loguru import logger

from src.database.database import BaseMongoDbWrapper
from src.feecc_workbench.utils import time_execution
from src.feecc_workbench.exceptions import EmployeeNotFoundError
from src.feecc_workbench.Types import Document
from .Employee import Employee
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])


class _EmployeeWrapper:
    collection = "employeeData"

    def get_employee_by_card_id(self, card_id: str) -> Employee:
        """find the employee with the provided RFID card id"""
        filters = {"rfid_card_id": card_id}
        projection = {"_id": 0, "hashed_password": 0}
        employee_data = BaseMongoDbWrapper.find_one(collection=self.collection, filters=filters, projection=projection)

        if employee_data is None:
            message = f"No employee with card ID {card_id}"
            logger.error(message)
            raise EmployeeNotFoundError(message)

        return Employee(**employee_data)

    def get_employee_by_username(self, username: str, password: str) -> Employee:
        """find the employee with the provided RFID card id"""
        filters = {"username": username}
        projection = {"_id": 0}
        employee_data = BaseMongoDbWrapper.find_one(collection=self.collection, filters=filters, projection=projection)

        if employee_data is None:
            message = f"No employee with username {username}"
            logger.error(message)
            raise EmployeeNotFoundError(message)

        if not bool(pwd_context.verify(password, employee_data["hashed_password"])):
            message = f"Incorrect password for username {username}"
            logger.error(message)
            raise EmployeeNotFoundError(message)

        return Employee(
            rfid_card_id=employee_data["rfid_card_id"],
            name=employee_data["name"],
            position=employee_data["position"],
            username=employee_data["username"],
        )


EmployeeWrapper = _EmployeeWrapper()
