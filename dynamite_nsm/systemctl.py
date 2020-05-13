import os
import subprocess
from shutil import copy2

from dynamite_nsm import exceptions


class CmdResult:
    """
    Container class for parsed and decoded systemctl command output
    """

    def __init__(self):
        self.out = None
        self.err = None
        self.exit = None
        self.cmd = None
        self.svc = None


class SystemCtl:
    """
    Provides a wrapper for systemctl for managing Dynamite services.
    """
    # Class variables
    UNIT_FILE_DIR = '/etc/systemd/system'

    # Map each role type to a list of associated service unit files
    ROLE_SVCS = {
        'agent': ['dynamite-agent.target', 'filebeat.service', 'suricata.service', 'zeek.service'],
        'monitor': ['dynamite-monitor.target', 'elastic.service', 'logstash.service', 'kibana.service'],
        'scanner': ['dynamite-scanner.target', 'rumble.service', 'filebeat.service']
    }

    def __init__(self, roles=('agent',)):
        # Placeholder for statically selecting the currently supported roles
        # we need to replace this with some logic (utilities) that
        # get the active roles configured at install time and use that to
        # determine which services get loaded.

        # For now, if no list is provided to the roles kwarg assume
        # the agent role.
        # TODO: Pull Dynamite component role list from file system.
        # all roles.

        # Verify systemctl is installed and in path, bail if not
        p = subprocess.Popen('which systemctl', stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=True)
        p.communicate()
        if p.returncode != 0:
            raise exceptions.CallProcessError('Systemctl not found, is it installed?  {}'.format(p.stderr.read()))

        # Update the status for Dynamite services based on the active roles
        svcs = self._get_svc_units(roles)
        for s in svcs:
            self._update_comp_status(s)

    @staticmethod
    def _format_svc_string(svc):
        if str(svc).startswith('dynamite'):
            return svc + '.target'
        return svc

    def _get_svc_units(self, roles):
        """
        Returns a unique list of service unit files used by the given roles.
        """
        svcs = set()
        for r in roles:
            if r in self.ROLE_SVCS:
                for s in self.ROLE_SVCS[r]:
                    svcs.add(s)
        return svcs

    def __getattribute__(self, name):
        """
        Retrieves an attribute by name.
        """
        return object.__getattribute__(self, name)

    def _get_svc_status(self, svc):
        """
        Retrieve the full status output from systemctl for a given service name.
        """
        return self._exec('status', svc, [])

    def _enable_svc(self, svc):
        """
        Execute the systemctl enable command for the given service.
        """
        return self._exec('enable', svc, [])

    def _disable_svc(self, svc):
        """
        Execute the systemctl disable command for the given service.
        """
        return self._exec('disable', svc, [])

    def _get_comp_state(self, component):
        """
        Retrieve the ActiveState and LoadState from systemctl for a given unit name.
        """
        state = {'LoadState': None, 'ActiveState': None}
        res = self._exec('show', component, ['-p ActiveState -p LoadState'])
        if res.exit == 0 and res.err == '' and res.out != '':
            state = {l.split('=')[0].strip(): l.split('=')[1].strip() for l in res.out.split('\n') if '=' in l}
        return state

    def _get_comp_status(self, component):
        """
        Convert ActiveState and LoadState to status report for a given component.

        :return: dict() with keys 'RUNNING' and 'ENABLED'
        """
        status = {'ENABLED': False, 'RUNNING': False}
        res = self._exec('show', component, ['-p ActiveState -p LoadState'])
        if res.exit == 0 and res.err == '' and res.out != '':
            state = {l.split('=')[0].strip(): l.split('=')[1].strip() for l in res.out.split('\n') if '=' in l}
            if state['LoadState'] == 'loaded':
                status['ENABLED'] = True
            if state['ActiveState'] == 'active':
                status['RUNNING'] = True
        return status

    def _update_comp_status(self, component):
        """
        Update the status attributes of the given component based on the state reported by systemctl.
        """
        state = self._get_comp_state(component)

        comp = component.split('.')[0]
        comp_enabled = comp + "_enabled"
        comp_running = comp + "_running"
        if state['LoadState'] == 'loaded':
            self.__setattr__(comp_enabled, True)
        else:
            self.__setattr__(comp_enabled, False)
        if state['ActiveState'] == 'active':
            self.__setattr__(comp_running, True)
        else:
            self.__setattr__(comp_running, False)

        return comp, self.__getattribute__(comp_running), self.__getattribute__(comp_enabled)

    def _exec(self, cmd=None, svc=None, args=None):
        """
        Wrapper for systemctl cli utility.
        Returns an object containing stdout, stderr, exit code from the executed systemctl command.
        """
        res = CmdResult()
        res.svc = svc
        res.cmd = " ".join(["systemctl", cmd, svc])
        if args and len(args) > 0:
            for arg in args:
                res.cmd += " " + arg
        p = subprocess.Popen(res.cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=True)
        out, err = p.communicate()
        res.err = err.decode().strip()
        res.out = out.decode().strip()
        res.exit = p.returncode
        return res

    def _exec_update(self, cmd, svc):
        """
        Executes the given systemctl cmd for the given component and updates the component's status in the instance object.
        :return:  A tuple in the form of: (<"service name">, Running (T/F), Enabled (T/F))
        """
        self._exec(cmd, svc, [])
        return self._update_comp_status(svc)

    @staticmethod
    def daemon_reload():
        """
        Executes `systemctl daemon-reload` to reload all systemd unit files.
        :return:  True if successful.  False otherwise.
        """
        p = subprocess.Popen('systemctl daemon-reload', stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=True)
        p.communicate()
        return p.returncode == 0

    def disable(self, svc, daemon_reload=True):
        """
        Disable the given service. This will prevent it from running at boot.
        """
        svc = self._format_svc_string(svc)
        _, _, enabled = self._exec_update("disable", svc)
        if daemon_reload and not enabled:
            self.daemon_reload()
        return not enabled

    def enable(self, svc, daemon_reload=True):
        """
        Enable the given service. This will cause it to run at boot after network services have started.
        :return: True if successful. False otherwise.
        """
        svc = self._format_svc_string(svc)
        _, _, enabled = self._exec_update("enable", svc)
        if daemon_reload and enabled:
            self.daemon_reload()
        return enabled

    def install_and_enable(self, path_to_svc):
        copy2(path_to_svc, self.UNIT_FILE_DIR)
        return self.enable(os.path.basename(path_to_svc))

    def start(self, svc):
        """
        Start the specified service and show the result.
        """
        svc = self._format_svc_string(svc)
        _, running, _ = self._exec_update("start", svc)
        return running

    def status(self, svc):
        """
        Displays the full systemctl status output for the given service.
        """
        svc = self._format_svc_string(svc)
        return self._get_svc_status(svc)

    def stop(self, svc):
        """
        Stop the specified service and show the result.
        """
        svc = self._format_svc_string(svc)
        _, running, _ = self._exec_update("stop", svc)
        return not running
