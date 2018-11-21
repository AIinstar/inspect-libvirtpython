import collections
from lxml import etree
import json
import threading
import time

libvirt = None
libvirt_type = 'kvm'
libvirt_uri = ''
Instance = collections.namedtuple('Instance', ['name', 'UUID', 'state'])
CPUStats = collections.namedtuple('CPUStats', ['number', 'util'])
Interface = collections.namedtuple('Interface', ['name', 'mac',
                                                 'fref', 'parameters'])
InterfaceStats = collections.namedtuple('InterfaceStats',
                                        ['rx_bytes', 'rx_packets',
                                         'tx_bytes', 'tx_packets'])
Disk = collections.namedtuple('Disk', ['device'])
DiskStats = collections.namedtuple('DiskStats',
                                   ['read_bytes', 'read_requests',
                                    'write_bytes', 'write_requests',
                                    'errors'])
DiskSize = collections.namedtuple('DiskSize', ['total', 'allocation', 'physical'])
Memory = collections.namedtuple('Memory', ['total', 'used', 'util'])


class InspectorException(Exception):
    def __init__(self, message=None):
        super(InspectorException, self).__init__(message)


class InstanceNotFoundException(InspectorException):
    pass


class LibvirtInspector():
    per_type_uris = dict(uml='uml:///system', xen='xen:///', lxc='lxc:///')

    def __init__(self):
        self.uri = self._get_uri()
        self.connection = None

    def _get_uri(self):
        return libvirt_uri or self.per_type_uris.get(libvirt_type,
                                                     'qemu:///system')

    def _get_connection(self):
        if not self.connection or not self._test_connection():
            global libvirt
            if libvirt is None:
                libvirt = __import__("libvirt")
            self.connection = libvirt.open(self.uri)
        return self.connection

    def _test_connection(self):
        try:
            self.connection.getCapabilities()
            return True
        except libvirt.libvirtError as e:
            if (e.get_error_code() == libvirt.VIR_ERR_SYSTEM_ERROR and
                    e.get_error_domain() in (libvirt.VIR_FROM_REMOTE,
                                             libvirt.VIR_FROM_RPC)):
                # LOG.debug('Connection to libvirt broke')
                return False
            raise

    def _lookup_by_name(self, instance_name):
        try:
            return self._get_connection().lookupByName(instance_name)
        except Exception as ex:
            if not libvirt or not isinstance(ex, libvirt.libvirtError):
                raise InspectorException(unicode(ex))
            error_code = ex.get_error_code()
            msg = ("Error from libvirt while looking up %(instance_name)s: "
                   "[Error Code %(error_code)s] "
                   "%(ex)s" % {'instance_name': instance_name,
                               'error_code': error_code,
                               'ex': ex})
            raise InstanceNotFoundException(msg)

    def inspect_instances(self):
        if self._get_connection().numOfDomains() > 0:
            for domain_id in self._get_connection().listDomainsID():
                try:
                    # We skip domains with ID 0 (hypervisors).
                    if domain_id != 0:
                        domain = self._get_connection().lookupByID(domain_id)
                        state = domain.state(0)[0]
                        if state != 1:
                            state = 0
                        yield Instance(name=domain.name(),
                                       UUID=domain.UUIDString(), state=state)
                except libvirt.libvirtError:
                    # Instance was deleted while listing... ignore it
                    pass

    # shut off instances
    def inspect_defined_domains(self):
        if self._get_connection().numOfDomain() > 0:
            for instance_name in self._get_connection().listDefineDomains():
                domain = self._lookup_by_name(instance_name)
                state = domain.state(0)[0]
                if state != 1:
                    state = 0
                yield Instance(name=instance_name, UUID=domain.UUIDString(), state=state)

    def inspect_disk_info_for_down(self, instance_name):
        domain = self._lookup_by_name(instance_name)

        #mem_totol = domain.info()[1]
        tree = etree.fromstring(domain.XMLDesc(0))
        for device in filter(bool, [target.get("dev") for target in tree.findall('devices/disk/target')]):
            disk = Disk(device=device)
            try:
                disk_size = domain.blockInfo(device, 0)
            except libvirt.libvirtError:
                pass







