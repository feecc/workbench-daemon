import os
import sys
import typing as tp

from loguru import logger

from .Employee import Employee
from .Singleton import SingletonMeta
from .Types import GlobalConfig, WorkbenchConfig
from .Unit import Unit
from .WorkBench import WorkBench
from .Config import Config
from ._Printer import Printer
from .database import MongoDbWrapper
from .exceptions import EmployeeNotFoundError, UnitNotFoundError, WorkbenchNotFoundError


class Hub(metaclass=SingletonMeta):
    """
    Hub is the class on top of the object hierarchy that handles
    operating the workbenches and is meant to be initialized only once
    """

    def __init__(self) -> None:
        logger.info("Initialized an instance of hub")
        self._config: GlobalConfig = Config().global_config
        self.database: MongoDbWrapper = self._get_database()
        self._employees: tp.Dict[str, Employee] = self._get_employees()
        self._workbenches: tp.List[WorkBench] = self._initialize_workbenches()
        self._create_dirs()
        self._init_singletons()

    @staticmethod
    def _create_dirs() -> None:
        if not os.path.isdir("output"):
            os.mkdir("output")

    def _init_singletons(self) -> None:
        """Initialize all singleton classes for future reuse"""
        Printer(self._config)

    def authorize_employee(self, employee_card_id: str, workbench_no: int) -> None:
        """logs the employee in at a given workbench"""
        try:
            employee: Employee = self._employees[employee_card_id]
        except KeyError:
            raise EmployeeNotFoundError(f"Rfid card ID {employee_card_id} unknown")

        workbench: WorkBench = self.get_workbench_by_number(workbench_no)
        workbench.state.start_shift(employee)

    @staticmethod
    def _get_credentials_from_env() -> tp.Optional[tp.Tuple[str, str]]:
        """getting credentials from environment variables"""
        try:
            username, password = os.environ["MONGO_LOGIN"], os.environ["MONGO_PASS"]

            if all((username, password)):
                return username, password

        except KeyError:
            logger.debug("Failed to get credentials from environment variables. Trying to get from config")

        return None

    def _get_database(self) -> MongoDbWrapper:
        """establish MongoDB connection and initialize the wrapper"""

        try:
            env_credentials = self._get_credentials_from_env()

            if env_credentials is None:
                username: str = self._config["mongo_db"]["username"]
                password: str = self._config["mongo_db"]["password"]
            else:
                username, password = env_credentials

            wrapper: MongoDbWrapper = MongoDbWrapper(username, password)
            return wrapper

        except Exception as E:
            message: str = f"Failed to establish database connection: {E}. Exiting."
            logger.critical(message)
            sys.exit()

    def _get_employees(self) -> tp.Dict[str, Employee]:
        """load up employee database and initialize an array of Employee objects"""
        employee_list = self.database.get_all_employees()
        employees: tp.Dict[str, Employee] = {}

        for employee in employee_list:
            employees[employee.rfid_card_id] = employee

        return employees

    def get_workbench_by_number(self, workbench_no: int) -> WorkBench:
        """find the workbench with the provided number"""
        for workbench in self._workbenches:
            if workbench.number == workbench_no:
                return workbench

        message: str = f"Could not find the workbench with number {workbench_no}. Does it exist?"
        logger.error(message)
        raise WorkbenchNotFoundError(message)

    def create_new_unit(self, unit_type: str) -> str:
        """initialize a new instance of the Unit class"""
        unit = Unit(self._config, unit_type)
        self.database.upload_unit(unit)

        if unit.internal_id is not None:
            return unit.internal_id
        else:
            raise ValueError("Unit internal_id is None")

    def get_employee_by_card_id(self, card_id: str) -> Employee:
        """find the employee with the provided RFID card id"""
        if card_id not in self._employees.keys():
            raise EmployeeNotFoundError(f"No employee with card ID {card_id}")

        return self._employees[card_id]

    def get_unit_by_internal_id(self, unit_internal_id: str) -> Unit:
        """find the unit with the provided internal id"""
        try:
            unit: Unit = self.database.get_unit_by_internal_id(unit_internal_id, self._config)
            return unit

        except Exception as E:
            logger.error(E)
            message: str = f"Could not find the Unit with int. id {unit_internal_id}. Does it exist?"
            raise UnitNotFoundError(message)

    @staticmethod
    def _initialize_workbenches() -> tp.List[WorkBench]:
        """make all the WorkBench objects using data specified in workbench_config.yaml"""
        workbench_config: WorkbenchConfig = Config().workbench_config
        workbenches = []

        for workbench in workbench_config:
            workbench_object = WorkBench(workbench)
            workbenches.append(workbench_object)

        if not workbenches:
            logger.critical("No workbenches could be spawned using 'workbench_config.yaml'. Can't operate. Exiting.")
            sys.exit(1)

        return workbenches
