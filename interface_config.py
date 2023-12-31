from urllib.parse import urlparse

from dcim.models import CableTermination, Device, Interface, Platform
from extras.scripts import Job, Script, ObjectVar
from ipam.models import IPAddress, VLAN
from wireless.models import WirelessLink


class InterfaceDataScript(Script):
    class Meta:
        name = "Device Interface Configuration"
        description = "Generates a `/etc/hostname.$INT` configuration for the interface for OpenBSD."
        commit_default = True

    platform = ObjectVar(
        Platform,
        required=False
    )
    device = ObjectVar(
        Device,
        query_params={
            'platform_id': '$platform'
        },
        required=False
    )
    interface = ObjectVar(
        Interface,
        query_params={
            'device_id': '$device'
        }
    )

    def get_interface_status(self, status: bool):
        enabled = ""
        if status:
            enabled = "up"
        return enabled

    def get_interface_addresses(self, interface_id: int):
        addresses = []
        result = list(IPAddress.objects.filter(assigned_object_id=interface_id))
        for address in result:
            self.log_debug(f"address data:  {vars(address)}")
            if address.status == "dhcp":
                addresses.append("inet autoconf")
            elif '.' in str(address):
                addresses.append(f"inet {address}")
            elif ':' in str(address):
                addresses.append(f"inet6 {address}")
        return addresses

    def get_parent_interface(self, parent_id: int):
        parent_interface = Interface.objects.get(id=parent_id)
        return parent_interface

    def get_cable_terminations(self, cable_id: int, cable_end: str):
        terminations = CableTermination.objects.filter(cable_id=cable_id)
        self.log_debug(f"cable terminations data: {vars(terminations)}")
        for termination in terminations:
            if termination.cable_end != cable_end:
                device = Device.objects.get(id=termination._device_id)
                interface = Interface.objects.get(id=termination.termination_id)
                if interface.label:
                    interface = interface.label
                return f"{device} | {interface}"

    def get_wireless_terminations(self, wireless_link_id: int, device_id: int):
        termination = WirelessLink.objects.get(id=wireless_link_id)
        self.log_debug(f"wireless termination data: {vars(termination)}")
        if termination._interface_a_device_id == device_id:
            device = Device.objects.get(id=termination._interface_b_device_id)
            interface = Interface.objects.get(id=termination.interface_b_id)
        else:
            device = Device.objects.get(id=termination._interface_a_device_id)
            interface = Interface.objects.get(id=termination.interface_a_id)

        mode = str(interface.type).split('.')[-1]
        if interface.label:
            interface = interface.label
        return {
            "media": f"media autoselect mode {mode}",
            "wireless": f"nwid \"{termination.ssid}\" wpakey \"{termination.auth_psk}\"",
            "description": f"{device} | {interface}"
        }

    def get_vlan_data(self, vlan_id: int, parent_id: int):
        vlan = VLAN.objects.get(id=vlan_id)
        vlandev = self.get_parent_interface(parent_id).label
        vid = vlan.vid
        description = vlan.name
        return [vid, vlandev, description]

    def run(self, data, commit):
        device = data['device']
        interface = data['interface']
        self.log_debug(f"device data: {vars(device)}")
        self.log_debug(f"interface data: {vars(interface)}")
        file = f"/etc/hostname.{interface}"
        if interface.label:
            file = f"/etc/hostname.{interface.label}"
        config = {1: f"# {file}"}
        addresses = self.get_interface_addresses(interface.id)
        position = 600
        for address in addresses:
            config.update({position: address})
            position += 5
        enabled = self.get_interface_status(interface.enabled)
        config.update({999: enabled})

        type = interface.type
        if interface.cable_id:
            description = self.get_cable_terminations(
                interface.cable_id,
                interface.cable_end
            )
            config.update(
                {
                    800: f"description \"{description}\""
                }
            )
        elif interface.wireless_link_id:
            data = self.get_wireless_terminations(
                interface.wireless_link_id,
                device.id
            )
            config.update(
                {
                    450: data['media'],
                    500: data['wireless'],
                    800: f"description \"{data['description']}\""
                }
            )
        if "ieee802.11" in type:
            pass
        elif "virtual" in type:
            if "access" in interface.mode:
                vlan_data = self.get_vlan_data(interface.untagged_vlan_id, interface.parent_id)
                config.update(
                    {
                        200: f"vlan {vlan_data[0]}",
                        210: f"vlandev {vlan_data[1]}",
                        800: f"description \"{vlan_data[-1]}\""
                    }
                )

            if "wg" in interface.name:
                config.update({850: "!/usr/local/bin/wg setconf \$if /etc/wireguard/\$if.conf"})

        # PERSISTENT CHANGES
        job_id = Job.objects.order_by('-created').first().id
        interface.custom_field_data['last_config_render'] = f"https://{urlparse(self.request.META.get('HTTP_REFERER')).hostname}/extras/scripts/results/{job_id}"
        interface.save()

        return '\n'.join([value for _, value in sorted(config.items())])


script = InterfaceDataScript()
