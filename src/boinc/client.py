#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# client.py - Somewhat higher-level GUI_RPC API for BOINC core client
#
#    Copyright (C) 2013 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>

# Based on client/boinc_cmd.cpp


from functools import total_ordering
import hashlib
import socket
import time
from xml.etree import ElementTree

import rpc


GUI_RPC_PASSWD_FILE = "/etc/boinc-client/gui_rpc_auth.cfg"


def setattrs_from_xml(obj, xml, attrfuncdict={}):
    """
    Helper to set values for attributes of a class instance by mapping
    matching tags from a XML file.
    The attrfuncdict is a dict of functions to customize value data type of
    each attribute. It falls back to simple int/float/bool/str detection
    based on values defined in __init__(). This would not be needed if
    Boinc used standard RPC protocol, which includes data type in XML.
    """
    if not isinstance(xml, ElementTree.Element):
        xml = ElementTree.fromstring(xml)
    for e in list(xml):
        if hasattr(obj, e.tag):
            attr = getattr(obj, e.tag)
            attrfunc = attrfuncdict.get(e.tag, None)
            if attrfunc is None:
                if isinstance(attr, bool):
                    attrfunc = parse_bool
                elif isinstance(attr, int):
                    attrfunc = parse_int
                elif isinstance(attr, float):
                    attrfunc = parse_float
                elif isinstance(attr, str):
                    attrfunc = parse_str
                elif isinstance(attr, list):
                    attrfunc = parse_list
                else:
                    attrfunc = lambda x: x
            setattr(obj, e.tag, attrfunc(e))
        else:
            print("class missing attribute '%s': %r" % (e.tag, obj))
    return obj


def parse_bool(e):
    """
    Helper to convert ElementTree.Element.text to boolean.
    Treat '<foo/>' (and '<foo>[[:blank:]]</foo>') as True.
    Treat '0' and 'false' as False.
    """
    if e.text is None:
        return True
    else:
        return bool(e.text) and not e.text.strip().lower() in ("0", "false")


def parse_int(e):
    """
    Helper to convert ElementTree.Element.text to integer.
    Treat '<foo/>' (and '<foo></foo>') as 0.
    """
    return 0 if e.text is None else int(float(e.text.strip()))


def parse_float(e):
    """Helper to convert ElementTree.Element.text to float."""
    return 0.0 if e.text is None else float(e.text.strip())


def parse_str(e):
    """Helper to convert ElementTree.Element.text to string."""
    return "" if e.text is None else e.text.strip()


def parse_list(e):
    """
    Helper to convert ElementTree.Element to list. For now, simply return
    the list of root element's children.
    """
    return list(e)


class Enum(object):
    UNKNOWN = -1  # not in original API.

    @classmethod
    def name(cls, value):
        """Quick-and-dirty fallback for getting the "name" of an enum item."""

        # Value as string, if it matches an enum attribute.
        # Allows short usage as Enum.name("VALUE") besides Enum.name(Enum.VALUE).
        if hasattr(cls, str(value)):
            return cls.name(getattr(cls, value, None))

        # Value not handled in subclass name().
        for k, v in cls.__dict__.items():
            if v == value:
                return k.lower().replace("_", " ")

        # Value not found.
        return cls.name(Enum.UNKNOWN)


class NetworkStatus(Enum):
    """Values of 'network_status'"""

    ONLINE = 0  # have network connections open
    WANT_CONNECTION = 1  # need a physical connection
    WANT_DISCONNECT = 2  # do not have any connections, and do not need any
    LOOKUP_PENDING = 3  # a website lookup is pending (try again later)

    @classmethod
    def name(cls, v):
        if v == cls.UNKNOWN:
            return "unknown"
        elif v == cls.ONLINE:
            return "up"  # 'online' is misleading, but is 'up' better?
        elif v == cls.WANT_CONNECTION:
            return "need connection"
        elif v == cls.WANT_DISCONNECT:
            return "do not need connection"
        elif v == cls.LOOKUP_PENDING:
            return "reference site lookup pending"
        else:
            return super(NetworkStatus, cls).name(v)


class SuspendReason(Enum):
    """
    Bitmap defs for task_suspend_reason, network_suspend_reason.
    Note: does not need to be a bitmap, but keep for compatibility.
    """

    NOT_SUSPENDED = 0  # not in original API
    BATTERIES = 1
    USER_ACTIVE = 2
    USER_REQ = 4
    TIME_OF_DAY = 8
    BENCHMARKS = 16
    DISK_SIZE = 32
    CPU_THROTTLE = 64
    NO_RECENT_INPUT = 128
    INITIAL_DELAY = 256
    EXCLUSIVE_APP_RUNNING = 512
    CPU_USAGE = 1024
    NETWORK_QUOTA_EXCEEDED = 2048
    OS = 4096
    WIFI_STATE = 4097
    BATTERY_CHARGING = 4098
    BATTERY_OVERHEATED = 4099

    @classmethod
    def name(cls, v):
        if v == cls.UNKNOWN:
            return "unknown reason"
        elif v == cls.BATTERIES:
            return "on batteries"
        elif v == cls.USER_ACTIVE:
            return "computer is in use"
        elif v == cls.USER_REQ:
            return "user request"
        elif v == cls.TIME_OF_DAY:
            return "time of day"
        elif v == cls.BENCHMARKS:
            return "CPU benchmarks in progress"
        elif v == cls.DISK_SIZE:
            return "need disk space - check preferences"
        elif v == cls.NO_RECENT_INPUT:
            return "no recent user activity"
        elif v == cls.INITIAL_DELAY:
            return "initial delay"
        elif v == cls.EXCLUSIVE_APP_RUNNING:
            return "an exclusive app is running"
        elif v == cls.CPU_USAGE:
            return "CPU is busy"
        elif v == cls.NETWORK_QUOTA_EXCEEDED:
            return "network bandwidth limit exceeded"
        elif v == cls.OS:
            return "requested by operating system"
        elif v == cls.WIFI_STATE:
            return "not connected to WiFi network"
        elif v == cls.BATTERY_CHARGING:
            return "battery is recharging"
        elif v == cls.BATTERY_OVERHEATED:
            return "battery is overheated"
        else:
            return super(SuspendReason, cls).name(v)


class RunMode(Enum):
    """
    Run modes for CPU, GPU, network, controlled by Activity menu and snooze
    button.
    """

    ALWAYS = 1
    AUTO = 2
    NEVER = 3
    RESTORE = 4 # restore permanent mode - used only in set_X_mode() GUI RPC

    @classmethod
    def name(cls, v):
        # All other modes use the fallback name.
        if v == cls.AUTO:
            return "according to preferences"
        else:
            return super(RunMode, cls).name(v)


class CpuSched(Enum):
    """
    Values of ACTIVE_TASK::scheduler_state and ACTIVE_TASK::next_scheduler_state
    "SCHEDULED" is synonymous with "executing" except when CPU throttling
    is in use.
    """

    UNINITIALIZED = 0
    PREEMPTED = 1
    SCHEDULED = 2


class ResultState(Enum):
    """
    Values of RESULT::state in client.
    THESE MUST BE IN NUMERICAL ORDER
    (because of the > comparison in RESULT::computing_done())
    See html/inc/common_defs.inc
    """

    NEW = 0
    # Input files for result (WU, app version) are being downloaded.
    FILES_DOWNLOADING = 1
    # Files are downloaded, result can be (or is being) computed.
    FILES_DOWNLOADED = 2
    COMPUTE_ERROR = 3 # computation failed; no file upload
    # Output files for result are being uploaded.
    FILES_UPLOADING = 4
    # Files are uploaded, notify scheduling server at some point.
    FILES_UPLOADED = 5
    ABORTED = 6  # result was aborted
    UPLOAD_FAILED = 7  # some output file permanent failure


class Process(Enum):
    """Values of ACTIVE_TASK::task_state."""

    UNINITIALIZED = 0  # process does not exist yet.
    EXECUTING = 1  # process is running, as far as is known.
    SUSPENDED = 9  # sent it a "suspend" message.
    # Process exceeded limits; send "abort" message, waiting to exit.
    ABORT_PENDING = 5
    QUIT_PENDING = 8 # sent it a "quit" message, waiting to exit.
    COPY_PENDING = 10 # waiting for async file copies to finish.


class _Struct(object):
    """
    Base helper class with common methods for all classes derived from
    BOINC's C++ structs.
    """

    @classmethod
    def parse(cls, xml):
        return setattrs_from_xml(cls(), xml)

    def __str__(self, indent=0):
        buf = '%s%s:\n' % ('\t' * indent, self.__class__.__name__)
        for attr in self.__dict__:
            value = getattr(self, attr)
            if isinstance(value, list):
                buf += '%s\t%s [\n' % ('\t' * indent, attr)
                for v in value:
                    buf += '\t\t%s\t\t,\n' % v
                buf += '\t]\n'
            else:
                buf += '%s\t%s\t%s\n' % (
                    '\t' * indent,
                    attr,
                    (
                        value.__str__(indent + 2)
                        if isinstance(value, _Struct)
                        else repr(value)
                    ),
                )
        return buf


@total_ordering
class VersionInfo(_Struct):
    def __init__(self, major=0, minor=0, release=0):
        self.major = major
        self.minor = minor
        self.release = release

    @property
    def _tuple(self):
        return (self.major, self.minor, self.release)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._tuple == other._tuple

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self._tuple > other._tuple

    def __str__(self):
        return "%d.%d.%d" % (self.major, self.minor, self.release)

    def __repr__(self):
        return "%s%r" % (self.__class__.__name__, self._tuple)


class CcStatus(_Struct):
    def __init__(self):
        self.network_status = NetworkStatus.UNKNOWN
        self.ams_password_error = False
        self.manager_must_quit = False

        self.task_suspend_reason = SuspendReason.UNKNOWN  # bitmap
        self.task_mode = RunMode.UNKNOWN
        self.task_mode_perm = RunMode.UNKNOWN  # same, but permanent version
        self.task_mode_delay = 0.0  # time until perm becomes actual

        self.network_suspend_reason = SuspendReason.UNKNOWN
        self.network_mode = RunMode.UNKNOWN
        self.network_mode_perm = RunMode.UNKNOWN
        self.network_mode_delay = 0.0

        self.gpu_suspend_reason = SuspendReason.UNKNOWN
        self.gpu_mode = RunMode.UNKNOWN
        self.gpu_mode_perm = RunMode.UNKNOWN
        self.gpu_mode_delay = 0.0

        self.disallow_attach = False
        self.simple_gui_only = False


class HostInfo(_Struct):
    def __init__(self):
        self.timezone = 0  # local STANDARD time - UTC time (in seconds)
        self.domain_name = ""
        self.ip_addr = ""
        self.host_cpid = ""

        # These are per CPU, not total.
        self.p_ncpus = 0  # number of CPUs on host
        self.p_vendor = ""  # vendor name of CPU
        self.p_model = ""  # model of CPU
        self.p_features = ""
        self.p_fpops = 0.0  # measured floating point ops/sec of CPU
        self.p_iops = 0.0  # measured integer ops/sec of CPU
        self.p_membw = 0.0  # measured memory bandwidth (bytes/sec) of CPU

        self.p_calculated = 0.0  # when benchmarks were last run, or zero
        self.p_vm_extensions_disabled = False

        self.m_nbytes = 0  # size of memory in bytes
        self.m_cache = 0  # size of CPU cache in bytes (level? e.g. L1 or all)
        self.m_swap = 0  # size of swap space in bytes

        # Total disk space on volume containing the BOINC client directory.
        self.d_total = 0
        self.d_free = 0  # how much is free on that volume

        self.os_name = ""  # name of operating system
        self.os_version = ""  # version of operating system

        # The following is non-empty if VBox is installed.
        self.virtualbox_version = ""

        self.product_name = ""
        self.wsl_available = False

        self.coprocs = []  # co-processors

        self.n_usable_coprocs = 0

        # The following are currently unused (not in RPC XML).
        self.serialnum = ""  # textual description of coprocessors

    @classmethod
    def parse(cls, xml):
        if not isinstance(xml, ElementTree.Element):
            xml = ElementTree.fromstring(xml)

        # Parse main XML.
        hostinfo = super(HostInfo, cls).parse(xml)

        # Parse each coproc in coprocs list.
        aux = []
        for c in hostinfo.coprocs:
            aux.append(Coproc.parse(c))
        hostinfo.coprocs = aux

        return hostinfo


class Coproc(_Struct):
    """
    Represents a set of identical coprocessors on a particular computer.
    Abstract class;
    objects will always be a derived class (COPROC_CUDA, COPROC_ATI)
    Used in both client and server.
    """

    def __init__(self):
        self.type = ""  # must be unique
        self.count = 0  # how many are present
        self.peak_flops = 0.0
        self.used = 0.0  # how many are in use (used by client)
        self.have_cuda = False  # True if this GPU supports CUDA
        self.have_cal = False  # True if this GPU supports CAL
        self.have_opencl = False  # True if this GPU supports OpenCL
        self.available_ram = 0

        # If true, this coproc was listed in cc_config.xml
        # rather than being detected by the client.
        self.specified_in_config = False

        # The following are used in both client and server for work-fetch info.
        self.req_secs = 0.0 # how many instance-seconds of work requested.
        # Client is requesting enough jobs to use this many instances.
        self.req_instances = 0.0
        self.estimated_delay = 0  # resource will be saturated for this long

        self.opencl_device_count = 0
        self.last_print_time = 0.0

        # self.opencl_prop = None  # OPENCL_DEVICE_PROP


class Project(_Struct):
    def __init__(self):
        self.master_url = ""
        self.project_name = ""
        self.symstore = None
        self.user_name = ""
        self.team_name = ""
        self.host_venue = None
        self.email_hash = ""
        self.cross_project_id = ""
        self.external_cpid = ""
        self.cpid_time = 0.0

        self.user_total_credit = 0.0
        self.user_expavg_credit = 0.0
        self.user_create_time = 0.0

        self.rpc_seqno = 0

        self.userid = 0
        self.teamid = 0
        self.hostid = 0

        self.host_total_credit = 0.0
        self.host_expavg_credit = 0.0
        self.host_create_time = 0.0

        self.min_rpc_time = 0.0
        self.next_rpc_time = 0.0

        self.nrpc_failures = None
        self.master_fetch_failures = None

        self.rec = 0.0

        self.rec_time = 0.0
        self.resource_share = 0.0
        self.desired_disk_usage = 0.0

        self.duration_correction_factor = 0.0

        self.sched_rpc_pending = 0
        self.send_time_stats_log = 0
        self.send_job_log = 0

        self.njobs_success = 0
        self.njobs_error = 0

        self.elapsed_time = 0.0
        self.last_rpc_time = 0.0
        self.dont_use_dcf = None

        self.rsc_backoff_time = None
        self.rsc_backoff_interval = None

        self.dont_request_more_work = None

        self.verify_files_on_app_start = None

        self.gui_urls = []

        self.sched_priority = 0.0
        self.project_files_downloaded_time = 0.0
        self.project_dir = ""

        self.venue = None

    @classmethod
    def parse(cls, xml):
        if not isinstance(xml, ElementTree.Element):
            xml = ElementTree.fromstring(xml)

        # Parse main XML.
        result = super(Project, cls).parse(xml)

        return result

    def __str__(self):
        buf = '%s:\n' % self.__class__.__name__
        for attr in self.__dict__:
            value = getattr(self, attr)
            if attr in ["rec_time", "user_create_time", "host_create_time"]:
                value = time.ctime(value)
            buf += '\t%s\t%r\n' % (attr, value)
        return buf


class Result(_Struct):
    """Also called "task" in some contexts."""

    def __init__(self):
        # Names and values follow lib/gui_rpc_client.h @ RESULT
        # Order too, except when grouping contradicts client/result.cpp
        # RESULT::write_gui(), then XML order is used.

        self.name = ""
        self.wu_name = ""
        self.version_num = 0  # identifies the app used
        self.plan_class = ""
        self.project_url = ""  # from PROJECT.master_url
        self.report_deadline = 0.0  # seconds since epoch
        self.received_time = 0.0  # seconds since epoch; when received
        # Ready to report this result to the server;
        # Either computation is done and all the files have been uploaded
        # or there was an error
        self.ready_to_report = False
        self.got_server_ack = False  # received the acknowledgement
        self.final_cpu_time = 0.0
        self.final_elapsed_time = 0.0
        self.state = ResultState.NEW
        self.estimated_cpu_time_remaining = 0.0
        self.exit_status = 0  # return value from the application
        self.suspended_via_gui = False
        self.project_suspended_via_gui = False
        # Temporary used to tell GUI that this result is deadline-scheduled.
        self.edf_scheduled = False
        # A coproc needed by this job is missing (e.g. GPU board is removed).
        self.coproc_missing = False
        self.scheduler_wait = False
        self.scheduler_wait_reason = ""
        self.network_wait = False
        self.resources = ""  # textual description of resources used

        # The following defined if active.
        # XML is generated in client/app.cpp ACTIVE_TASK::write_gui()
        self.active_task = False
        self.active_task_state = Process.UNINITIALIZED
        self.app_version_num = 0
        self.slot = -1
        self.pid = 0
        self.scheduler_state = CpuSched.UNINITIALIZED
        self.checkpoint_cpu_time = 0.0
        self.current_cpu_time = 0.0
        self.fraction_done = 0.0
        self.elapsed_time = 0.0
        self.swap_size = 0
        self.working_set_size_smoothed = 0.0
        self.too_large = False
        self.needs_shmem = False
        self.graphics_exec_path = ""
        self.web_graphics_url = ""
        self.remote_desktop_addr = ""
        self.slot_path = ""  # only present if graphics_exec_path is

        # Are not in original API, but are present in RPC XML reply.
        self.completed_time = 0.0  # time when ready_to_report was set
        self.report_immediately = False
        self.working_set_size = 0
        self.page_fault_rate = 0.0  # derived by higher-level code

        # Are present in API documentation, but are never in RPC XML reply.
        self.signal = 0

        self.app = None  # APP*
        self.wup = None  # WORKUNIT*
        self.project = None  # PROJECT*
        self.avp = None  # APP_VERSION*

        self.progress_rate = None
        self.platform = None
        self.bytes_sent = None
        self.bytes_received = None

    @classmethod
    def parse(cls, xml):
        if not isinstance(xml, ElementTree.Element):
            xml = ElementTree.fromstring(xml)

        # Parse main XML.
        result = super(Result, cls).parse(xml)

        # Parse '<active_task>' children.
        active_task = xml.find("active_task")
        if active_task is None:
            result.active_task = False  # already the default after __init__()
        else:
            result.active_task = True  # already the default after main parse
            result = setattrs_from_xml(result, active_task)

        # If CPU time is nonzero but elapsed time is zero, then must be talking
        # to an old client (easier to deal with this here than in the manager).
        if result.current_cpu_time != 0 and result.elapsed_time == 0:
            result.elapsed_time = result.current_cpu_time

        if result.final_cpu_time != 0 and result.final_elapsed_time == 0:
            result.final_elapsed_time = result.final_cpu_time

        return result

    def __str__(self):
        buf = '%s:\n' % self.__class__.__name__
        for attr in self.__dict__:
            value = getattr(self, attr)
            if attr in ["received_time", "report_deadline"]:
                value = time.ctime(value)
            buf += '\t%s\t%r\n' % (attr, value)
        return buf


class BoincClient(object):
    def __init__(self, host="", passwd=None):
        host = host.split(":", 1)

        self.hostname = host[0]
        self.port = int(host[1]) if len(host) == 2 else 0
        self.passwd = passwd
        self.rpc = rpc.Rpc(text_output=False)
        self.version = None
        self.authorized = False

        # Informative, not authoritative. Records status of *last* RPC call,
        # but does not infer success about the *next* one.
        # Thus, it should be read *after* an RPC call, not prior to one.
        self.connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        try:
            self.rpc.connect(self.hostname, self.port)
            self.connected = True
        except socket.error:
            self.connected = False
            return
        self.authorized = self.authorize(self.passwd)
        self.version = self.exchange_versions()

    def disconnect(self):
        self.rpc.disconnect()

    def authorize(self, password):
        """
        Request authorization. If password is None and we are connecting
        to localhost, try to read password from the local config file
        GUI_RPC_PASSWD_FILE. If file cannot be read (not found or no
        permission to read), try to authorize with a blank password.
        If authorization is requested and fails, all subsequent calls
        will be refused with socket.error 'Connection reset by peer' (104).
        Since most local calls do no require authorization, do not attempt
        it if not sure about the password.
        """
        if password is None and not self.hostname:
            password = read_gui_rpc_password() or ""
        nonce = self.rpc.call("<auth1/>").text
        inputStr = "%s%s" % (nonce, password)
        hash = hashlib.md5(inputStr.encode("utf-8")).hexdigest().lower()
        reply = self.rpc.call(
            "<auth2><nonce_hash>%s</nonce_hash></auth2>" % hash
        )

        if reply.tag == "authorized":
            return True
        else:
            return False

    def exchange_versions(self):
        """Return VersionInfo instance with core client version information."""
        return VersionInfo.parse(self.rpc.call("<exchange_versions/>"))

    @property
    def status(self):
        return self.get_cc_status()

    def get_cc_status(self):
        """
        Return CcStatus instance containing basic status, such as
        CPU / GPU / Network active/suspended, etc..
        """
        if not self.connected:
            self.connect()
        try:
            return CcStatus.parse(self.rpc.call("<get_cc_status/>"))
        except socket.error:
            self.connected = False

    @property
    def host(self):
        return self.get_host_info()

    def get_host_info(self):
        """Get information about host hardware and usage."""
        return HostInfo.parse(self.rpc.call("<get_host_info/>"))

    @property
    def tasks(self):
        return self.get_tasks()

    def get_tasks(self):
        """Same as get_results(active_only=False)."""
        return self.get_results(False)

    @property
    def results(self):
        return self.get_results(False)

    @property
    def results_active(self):
        return self.get_results(True)

    def get_results(self, active_only=False):
        """
        Get a list of results.
        Those that are in progress will have information such as CPU time
        and fraction done. Each result includes a name;
        Use CC_STATE::lookup_result() to find this result in the current
        static state;
        if it is not there, call get_state() again.
        """
        reply = self.rpc.call(
            "<get_results><active_only>%d</active_only></get_results>"
            % (1 if active_only else 0)
        )
        if not reply.tag == "results":
            return []

        results = []
        for item in list(reply):
            results.append(Result.parse(item))

        return results

    @property
    def projects(self):
        return self.get_projects()

    def get_projects(self):
        reply = self.rpc.call("<get_project_status/>")

        if not reply or not reply.tag == "projects":
            return []

        projects = []
        for item in list(reply):
            projects.append(Project.parse(item))

        return projects

    def set_mode(self, component, mode, duration=0):
        """
        Do the real work of set_{run,gpu,network}_mode().
        This method is not part of the original API.
        Valid components are 'run' (or 'cpu'), 'gpu', 'network' (or 'net').
        """
        component = component.replace("cpu", "run")
        component = component.replace("net", "network")
        try:
            reply = self.rpc.call(
                "<set_%s_mode>"
                "<%s/><duration>%f</duration>"
                "</set_%s_mode>"
                % (component, RunMode.name(mode).lower(), duration, component)
            )
            return reply.tag == "success"
        except socket.error:
            return False

    def set_run_mode(self, mode, duration=0):
        """
        Set the run mode (RunMode.NEVER/AUTO/ALWAYS/RESTORE).
        NEVER will suspend all activity, including CPU, GPU and Network.
        AUTO will run according to preferences.
        If duration is zero, mode is permanent. Otherwise revert to last
        permanent mode after duration seconds elapse.
        """
        return self.set_mode("cpu", mode, duration)

    def set_gpu_mode(self, mode, duration=0):
        """Set the GPU run mode, similar to set_run_mode() but for GPU only."""
        return self.set_mode('gpu', mode, duration)

    def set_network_mode(self, mode, duration=0):
        """
        Set the Network run mode, similar to set_run_mode()
        but for network activity only.
        """
        return self.set_mode('net', mode, duration)

    def run_benchmarks(self):
        """Run benchmarks. Computing will suspend during benchmarks."""
        return self.rpc.call('<run_benchmarks/>').tag == "success"

    def quit(self):
        """Tell the core client to exit."""
        if self.rpc.call('<quit/>').tag == "success":
            self.connected = False
            return True
        return False


def read_gui_rpc_password():
    """
    Read password string from GUI_RPC_PASSWD_FILE file, trim the last CR
    (if any), and return the password.
    """
    try:
        with open(GUI_RPC_PASSWD_FILE, "r") as f:
            buf = f.read()
            if buf.endswith("\n"):
                return buf[:-1]  # trim last CR
            else:
                return buf
    except IOError:
        # Permission denied or File not found.
        pass


if __name__ == "__main__":
    # Example.
    with BoincClient(
        host="192.168.2.1", passwd="2f7b4b513d02f954cd22e8109c0bc0c0"
    ) as boinc:
        print(boinc.connected)
        print(boinc.authorized)
        print(boinc.version)
        print(boinc.get_cc_status())
        # for i, task in enumerate(boinc.get_results(True)):
        #     print(i + 1, task)
        print(boinc.get_host_info())
        # print boinc.run_benchmarks()
        # print boinc.set_run_mode(RunMode.NEVER, 6)
        # time.sleep(7)
        # print boinc.set_gpu_mode(RunMode.NEVER, 6)
        # time.sleep(7)
        # print boinc.set_network_mode(RunMode.NEVER, 6)
