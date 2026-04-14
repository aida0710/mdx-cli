from enum import Enum


class VMStatus(str, Enum):
    RUNNING = "Running"
    STOPPED = "Stopped"
    DEPLOYING = "Deploying"
    DESTROYING = "Destroying"


class ServiceLevel(str, Enum):
    SPOT = "spot"
    GUARANTEE = "guarantee"


class TaskStatus(str, Enum):
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
