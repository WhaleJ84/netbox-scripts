from core.models import Job
from dcim.models import Device, DeviceRole
from extras.scripts import (
    ChoiceVar,
    IntegerVar,
    MultiChoiceVar,
    ObjectVar,
    Script,
)

_NAME_PARTS = (
    ("SERIAL", "Serial Number"),
    ("ROLE_ID", "Role"),
    ("SITE_ID", "Site"),
    ("NAME", "Name"),
)

CASE = (
    ("0", "lower"),
    ("1", "UPPER"),
)

_SERIAL_CHARS: int = 6
_SERIAL_FROM: int = -1
SERIAL_FROM = (
    ("0", "From start"),
    ("-1", "From end"),
)

class DeviceNameGenerator(Script):
    class Meta:
        name = "Device Name Generator"
        description = "Generates a device name based off its role, serial number, etc."
        commit_default = False

    device = ObjectVar(
        model = Device,
    )

    name_case = ChoiceVar(
        choices = CASE,
        default = "0",
        description = "Whether the name should be in upper or lower case.",
        label = "Name case",
    )

    serial_from = ChoiceVar(
        choices = SERIAL_FROM,
        default = "-1",
        description = "Whether to use X number of characters starting from the start or the end of the serial number.",
        label = "Serial from",
        required = False
    )

    serial_chars = IntegerVar(
        default = _SERIAL_CHARS,
        description = "Number of characters to use from the serial number, if at all. '0' uses all characters.",
        label = "Serial characters",
        required = False,
    ) 

    name_parts = MultiChoiceVar(
        choices = _NAME_PARTS,
        default = ["SERIAL", "ROLE_ID"]
    )


    def get_serial(self, serial: str, serial_from: int = _SERIAL_FROM, serial_chars: int = _SERIAL_CHARS) -> str:
        self.log_debug(f"get_serial start: {serial}, {serial_from}, {serial_chars}")
        if serial_from == "0":
            serial = serial[:serial_chars]
        elif serial_from == "-1":
            serial = serial[-serial_chars:]
        self.log_debug(f"get_serial end: {serial}")
        return serial

    def get_role(self, role_id: int) -> str:
        role = DeviceRole.objects.get(id=role_id)
        self.log_debug(f"role: {role.__dict__}")
        return role.name

    def run(self, data, commit):
        job_id = Job.objects.order_by('-created').first().id
        result: str = ""

        device = data['device']
        self.log_info(device.__dict__)
        serial_from = data['serial_from']
        serial_chars = data['serial_chars']
        name_case = data['name_case']
        NAME_PARTS = data['name_parts']
        self.log_info(f"'name_parts': {NAME_PARTS}")

        # SERIAL
        serial = ""
        if "SERIAL" in NAME_PARTS:
            serial = self.get_serial(
                device.serial,
                serial_from,
                serial_chars,
            )

        # ROLE
        role_id = ""
        if "ROLE_ID" in NAME_PARTS:
            role_id = self.get_role(device.role_id).lower()
            self.log_debug(f"0: {role_id}")
            if role_id in ["router"]:
                self.log_debug(f"1: {role_id}")
                role_id = "gw"

        # SITE

        # NAME

        # RESULT
        for part in NAME_PARTS:
            self.log_debug(f"part: {part}")
            self.log_info(f"test: {locals()[part.lower()]}")
            pass

        self.log_debug("nc 0")
        if name_case == "0":
            self.log_debug("nc 1")
            result = result.lower()
        elif name_case == "1":
            self.log_debug("nc 2")
            result = result.upper()

        return result
