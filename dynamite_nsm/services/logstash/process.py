from typing import Dict, Optional, Union

from dynamite_nsm import utilities
from dynamite_nsm import exceptions
from dynamite_nsm.services.base import process
from dynamite_nsm.services.logstash import profile as logstash_profile


class CallLogstashProcessError(exceptions.CallProcessError):
    """
    Thrown when logstash process encounters an error state
    """
    def __init__(self, message):
        """
        :param message: A more specific error message
        """
        msg = "An error occurred while calling logstash process: {}".format(message)
        super(CallLogstashProcessError, self).__init__(msg)


class ProcessManager(process.BaseProcessManager):
    """
    LogStash Process Manager
    """
    def __init__(self, stdout=True, verbose=False, pretty_print_status=False):
        environ = utilities.get_environment_file_dict()
        process.BaseProcessManager.__init__(self, 'logstash.service', 'logstash', log_path=environ.get('LS_LOGS'),
                                            stdout=stdout, verbose=verbose, pretty_print_status=pretty_print_status)

        if not logstash_profile.ProcessProfiler().is_installed():
            self.logger.error("LogStash is not installed. Install it with 'dynamite logstash install -h'")
            raise CallLogstashProcessError("LogStash is not installed.")


def start(stdout: Optional[bool] = True, verbose: Optional[bool] = False,
          pretty_print_status: Optional[bool] = False) -> bool:
    return ProcessManager(stdout=stdout, verbose=verbose, pretty_print_status=pretty_print_status).start()


def stop(stdout: Optional[bool] = True, verbose: Optional[bool] = False,
         pretty_print_status: Optional[bool] = False) -> bool:
    return ProcessManager(stdout=stdout, verbose=verbose, pretty_print_status=pretty_print_status).stop()


def restart(stdout: Optional[bool] = True, verbose: Optional[bool] = False,
            pretty_print_status: Optional[bool] = False) -> bool:
    return ProcessManager(stdout=stdout, verbose=verbose, pretty_print_status=pretty_print_status).restart()


def status(stdout: Optional[bool] = True, verbose: Optional[bool] = False,
           pretty_print_status: Optional[bool] = False) -> Union[Dict, str]:
    return ProcessManager(stdout=stdout, verbose=verbose, pretty_print_status=pretty_print_status).status()

