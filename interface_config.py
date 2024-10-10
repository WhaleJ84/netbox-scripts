from importlib import import_module
from os import getenv

from core.models import Job
from dcim.models import CableTermination, Device, Interface, Platform
from extras.scripts import Script, ObjectVar
from ipam.models import IPAddress, VLAN
from wireless.models import WirelessLink


class OpenBSDConfiguration(Script):
    class Meta:
        name = "OpenBSD Configuration"
        description = "Generates a `/etc/hostname.$INT` configuration for the interface for OpenBSD."
        commit_default = False

    platform = ObjectVar(
        model=Platform,
        required=False
    )

    device = ObjectVar(
        model=Device,
        query_params={
            'platform_id': '$platform'
        },
        required=False
    )

    interface = ObjectVar(
        model=Interface,
        query_params={
            'device_id': '$device'
        },
        required=True
    )

    def get_interface_addresses(self, interface_id: int):
        result = list(IPAddress.objects.filter(assigned_object_id=interface_id))
        self.log_debug(f"Found addresses: {result}")
        addresses = []
        for address in result:
            self.log_debug(f"address data:  {vars(address)}")
            if address.status == "dhcp":
                addresses.append("inet autoconf")
            elif '.' in str(address):
                addresses.append(f"inet {address}")
            elif ':' in str(address):
                addresses.append(f"inet6 {address}")
        return addresses

    def get_interface_status(self, status: bool):
        enabled = ""
        if status:
            enabled = "up"
        self.log_debug(f"Found status: {status}")
        return enabled

    def get_parent_interface(self, parent_id: int):
        parent_interface = Interface.objects.get(id=parent_id)
        return parent_interface
    
    def get_vlan_data(self, vlan_id: int, parent_id: int):
        vlan = VLAN.objects.get(id=vlan_id)
        vlandev = self.get_parent_interface(parent_id).label
        vid = vlan.vid
        description = vlan.name
        return [vid, vlandev, description]

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

    def run(self, data, commit):
        config = import_module(getenv('NETBOX_CONFIGURATION', 'netbox.configuration'))
        primary_fqdn = getattr(config, 'ALLOWED_HOSTS')[0]
        device = data['device']
        interface = data['interface']
        
        file = f"/etc/hostname.{interface}"

        if interface.label:
            self.log_debug(f"Found label: {interface.label} for interface: {interface}")
            file = f"/etc/hostname.{interface.label}"
        else:
            self.log_failure(f"No label found for interface: {interface}")
        config = {1: f"# {file}"}

        addresses = self.get_interface_addresses(interface.id)
        position = 600
        for address in addresses:
            config.update({position: address})
            position += 5

        enabled = self.get_interface_status(interface.enabled)
        config.update({999: enabled})

        type = interface.type
        self.log_debug(f"Found interface type: {type}")
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

        job_id = Job.objects.order_by('-created').first().id
        interface.custom_field_data['last_config_render'] = f"https://{primary_fqdn}/extras/scripts/results/{job_id}"
        interface.save()

        return '\n'.join([value for _, value in sorted(config.items())])
