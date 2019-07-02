import os
import sys
import time
import signal
import shutil
import tarfile
import subprocess
from multiprocessing import Process
from installer import const
from installer import utilities
from installer import elastiflow

CONFIGURATION_DIRECTORY = '/etc/dynamite/logstash/'
INSTALL_DIRECTORY = '/opt/dynamite/logstash/'
LOG_DIRECTORY = '/var/log/dynamite/logstash/'


class LogstashConfigurator:
    """
    Wrapper for configuring logstash.yml and jvm.options
    """
    def __init__(self, configuration_directory):
        """
        :param configuration_directory: Path to the configuration directory (E.G /etc/dynamite/logstash/)
        """
        self.configuration_directory = configuration_directory
        self.ls_config_options = self._parse_logstashyaml()
        self.jvm_config_options = self._parse_jvm_options()
        self.java_home = None
        self.ls_home = None
        self.ls_path_conf = None
        self._parse_environment_file()

    def _parse_logstashyaml(self):
        """
        Parse logstash.yaml, return a object representing the config
        :return: A dictionary of config options and their values
        """
        ls_config_options = {}
        for line in open(os.path.join(self.configuration_directory, 'logstash.yml')).readlines():
            if not line.startswith('#') and ':' in line:
                k, v = line.strip().split(':')
                ls_config_options[k] = str(v).strip()
        return ls_config_options

    def _parse_jvm_options(self):
        """
        Parses the initial and max heap allocation from jvm.options configuration
        :return: A dictionary containing the initial_memory and maximum_memory allocated to JVM heap
        """
        jvm_options = {}
        for line in open(os.path.join(self.configuration_directory, 'jvm.options')).readlines():
            if not line.startswith('#') and '-Xms' in line:
                jvm_options['initial_memory'] = line.replace('-Xms', '').strip()
            elif not line.startswith('#') and '-Xmx' in line:
                jvm_options['maximum_memory'] = line.replace('-Xmx', '').strip()
        return jvm_options

    def _parse_environment_file(self):
        """
        Parses the /etc/environment file and returns results for JAVA_HOME, LS_PATH_CONF, LS_HOME;
        stores the results in class variables of the same name
        """
        for line in open('/etc/environment').readlines():
            if line.startswith('JAVA_HOME'):
                self.java_home = line.split('=')[1].strip()
            elif line.startswith('LS_PATH_CONF'):
                self.ls_path_conf = line.split('=')[1].strip()
            elif line.startswith('LS_HOME'):
                self.ls_home = line.split('=')[1].strip()

    def _overwrite_jvm_options(self):
        """
        Overwrites the JVM initial/max memory if settings were updated
        """
        new_output = ''
        for line in open(os.path.join(self.configuration_directory, 'jvm.options')).readlines():
            if not line.startswith('#') and '-Xms' in line:
                new_output += '-Xms' + self.jvm_config_options['initial_memory']
            elif not line.startswith('#') and '-Xmx' in line:
                new_output += '-Xmx' + self.jvm_config_options['maximum_memory']
            else:
                new_output += line
            new_output += '\n'
        open(os.path.join(self.configuration_directory, 'jvm.options'), 'w').write(new_output)

    def get_log_path(self):
        """
        :return: The path to Logstash logs on filesystem
        """
        return self.ls_config_options.get('path.logs')

    def get_node_name(self):
        """
        :return: The name of the LogStash collector node
        """
        return self.ls_config_options.get('node.name')

    def get_data_path(self):
        """
        :return: The directory where data (persistent queues) are being stored
        """
        return self.ls_config_options.get('path.data')

    def get_pipeline_batch_size(self):
        """
        :return: The number of events to retrieve from inputs before sending to filters+workers
        """
        return self.ls_config_options.get('pipeline.batch.size')

    def get_pipeline_batch_delay(self):
        """
        :return: The number of milliseconds while polling for the next event before dispatching an
        undersized batch to filters+outputs
        """
        return self.ls_config_options.get('pipeline.batch.delay')

    def get_jvm_initial_memory(self):
        """
        :return: The initial amount of memory the JVM heap allocates
        """
        return self.jvm_config_options.get('initial_memory')

    def get_jvm_maximum_memory(self):
        """
        :return: The maximum amount of memory the JVM heap allocates
        """
        return self.jvm_config_options.get('maximum_memory')

    def set_log_path(self, path):
        """
        :param path: The path to Logstash logs on the filesystem
        """
        self.ls_config_options['path.logs'] = path

    def set_node_name(self, name):
        """
        :param name: The name of the Logstash collector node
        """
        self.ls_config_options['node.name'] = name

    def set_data_path(self, path):
        """
        :param path: The path to the Logstash collector node
        """
        self.ls_config_options['path.data'] = path

    def set_pipeline_batch_size(self, event_count):
        """
        :param event_count: How many events to retrieve from inputs before sending to filters+workers
        """
        self.ls_config_options['pipeline.batch.size'] = event_count

    def set_pipeline_batch_delay(self, delay_millisecs):
        """
        :param delay_millisecs: How long to wait in milliseconds while polling for the next event before dispatching an
        undersized batch to filters+outputs
        """
        self.ls_config_options['pipeline.batch.delay'] = delay_millisecs

    def set_jvm_initial_memory(self, gigs):
        """
        :param gigs: The amount of initial memory (In Gigabytes) for the JVM to allocate to the heap
        """
        self.jvm_config_options['initial_memory'] = str(int(gigs)) + 'g'

    def set_jvm_maximum_memory(self, gigs):
        """
        :param gigs: The amount of maximum memory (In Gigabytes) for the JVM to allocate to the heap
        """
        self.jvm_config_options['maximum_memory'] = str(int(gigs)) + 'g'

    def write_configs(self):
        """
        Write (and backs-up) logstash.yml and jvm.option configurations
        """
        timestamp = int(time.time())
        backup_configurations = os.path.join(self.configuration_directory, 'config_backups/')
        es_config_backup = os.path.join(backup_configurations, 'logstash.yml.backup.{}'.format(timestamp))
        java_config_backup = os.path.join(backup_configurations, 'java.options.backup.{}'.format(
            timestamp
        ))
        subprocess.call('mkdir -p {}'.format(backup_configurations), shell=True)
        shutil.move(os.path.join(self.configuration_directory, 'logstash.yml'), es_config_backup)
        shutil.copy(os.path.join(self.configuration_directory, 'jvm.options'), java_config_backup)
        with open(os.path.join(self.configuration_directory, 'logstash.yml'), 'a') as logstash_search_config_obj:
            for k, v in self.ls_config_options.items():
                logstash_search_config_obj.write('{}: {}\n'.format(k, v))
        self._overwrite_jvm_options()


class LogstashInstaller:

    def __init__(self,
                 configuration_directory=CONFIGURATION_DIRECTORY,
                 install_directory=INSTALL_DIRECTORY,
                 log_directory=LOG_DIRECTORY):
        """
        :param configuration_directory: Path to the configuration directory (E.G /etc/dynamite/logstash/)
        :param install_directory: Path to the install directory (E.G /opt/dynamite/logstash/)
        :param log_directory: Path to the log directory (E.G /var/log/dynamite/logstash/)
        """

        self.configuration_directory = configuration_directory
        self.install_directory = install_directory
        self.log_directory = log_directory

    @staticmethod
    def download_logstash(stdout=False):
        """
        Download Logstash archive

        :param stdout: Print output to console
        """
        for url in open(const.LOGSTASH_MIRRORS, 'r').readlines():
            if utilities.download_file(url, const.LOGSTASH_ARCHIVE_NAME, stdout=stdout):
                break

    @staticmethod
    def extract_logstash(stdout=False):
        """
        Extract Logstash to local install_cache

        :param stdout: Print output to console
        """
        if stdout:
            sys.stdout.write('[+] Extracting: {} \n'.format(const.LOGSTASH_ARCHIVE_NAME))
        try:
            tf = tarfile.open(os.path.join(const.INSTALL_CACHE, const.LOGSTASH_ARCHIVE_NAME))
            tf.extractall(path=const.INSTALL_CACHE)
            if stdout:
                sys.stdout.write('[+] Complete!\n')
                sys.stdout.flush()
        except IOError as e:
            sys.stderr.write('[-] An error occurred while attempting to extract file. [{}]\n'.format(e))

    def setup_logstash(self, stdout=False):
        """
        Create required directories, files, and variables to run LogStash successfully;
        Setup Java environment

        :param stdout: Print output to console
        """
        if stdout:
            sys.stdout.write('[+] Creating logstash install|configuration|logging directories.\n')
        subprocess.call('mkdir -p {}'.format(self.install_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(self.configuration_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(self.log_directory), shell=True)
        subprocess.call('mkdir -p {}'.format(os.path.join(self.install_directory, 'data')), shell=True)
        subprocess.call('mkdir -p {}'.format('/var/run/dynamite/logstash/'), shell=True)
        config_paths = [
            'config/logstash.yml',
            'config/jvm.options',
            'config/log4j2.properties'
        ]
        install_paths = [
            'Gemfile',
            'Gemfile.lock',
            'bin/',
            'lib/',
            'logstash-core/',
            'logstash-core-plugin-api/',
            'modules/',
            'tools/',
            'vendor/',
            'x-pack/'
        ]
        for path in config_paths:
            try:
                shutil.move(os.path.join(const.INSTALL_CACHE, 'logstash-7.1.1/{}'.format(path)),
                            self.configuration_directory)

            except shutil.Error as e:
                sys.stderr.write('[-] {} already exists at this path. [{}]\n'.format(path, e))
        for path in install_paths:
            try:
                shutil.move(os.path.join(const.INSTALL_CACHE, 'logstash-7.1.1/{}'.format(path)),
                            self.install_directory)
            except shutil.Error as e:
                sys.stderr.write('[-] {} already exists at this path. [{}]\n'.format(path, e))
        if 'LS_PATH_CONF' not in open('/etc/environment').read():
            if stdout:
                sys.stdout.write('[+] Updating LogStash default configuration path [{}]\n'.format(
                    self.configuration_directory))
            subprocess.call('echo LS_PATH_CONF="{}" >> /etc/environment'.format(self.configuration_directory),
                            shell=True)
        if 'LS_HOME' not in open('/etc/environment').read():
            if stdout:
                sys.stdout.write('[+] Updating LogStash default home path [{}]\n'.format(
                    self.configuration_directory))
            subprocess.call('echo LS_HOME="{}" >> /etc/environment'.format(self.install_directory),
                            shell=True)
        sys.stdout.write('[+] Overwriting default configuration.\n')
        sys.stdout.flush()
        shutil.copy(os.path.join(const.DEFAULT_CONFIGS, 'logstash', 'logstash.yml'),
                    self.configuration_directory)
        ls_config = LogstashConfigurator(configuration_directory=self.configuration_directory)
        if stdout:
            sys.stdout.write('[+] Setting up JVM default heap settings [4GB]\n')
            sys.stdout.flush()
        ls_config.set_jvm_initial_memory(4)
        ls_config.set_jvm_maximum_memory(4)
        ls_config.write_configs()
        if stdout:
            sys.stdout.write('[+] Setting up Max File Handles [65535] VM Max Map Count [262144] \n')
        utilities.update_user_file_handle_limits()
        utilities.update_sysctl()
        ef_install = elastiflow.ElastiFlowInstaller(configuration_directory=
                                                    os.path.join(self.configuration_directory, 'elastiflow'))

        shutil.copy(os.path.join(const.DEFAULT_CONFIGS, 'logstash', 'elastiflow-pipeline.yml'),
                    os.path.join(self.configuration_directory, 'pipelines.yml'))
        ef_install.download_elasticflow(stdout=stdout)
        ef_install.extract_elastiflow(stdout=stdout)
        ef_install.setup_logstash_elastiflow(stdout=stdout)
        if stdout:
            sys.stdout.write('[+] Installing Logstash plugins\n')
            sys.stdout.flush()
        subprocess.call('{}/bin/logstash-plugin install logstash-codec-sflow'.format(self.install_directory),
                        shell=True)
        utilities.set_ownership_of_file('/etc/dynamite/')
        utilities.set_ownership_of_file('/opt/dynamite/')
        utilities.set_ownership_of_file('/var/log/dynamite')
        utilities.set_ownership_of_file('/var/run/dynamite')


class LogstashProcess:
    """
    An interface for start|stop|status|restart of the LogStash process
    """
    def __init__(self, configuration_directory=CONFIGURATION_DIRECTORY):
        """
        :param configuration_directory: Path to the configuration directory (E.G /etc/dynamite/logstash/)
        """

        self.configuration_directory = configuration_directory
        self.config = LogstashConfigurator(self.configuration_directory)
        try:
            self.pid = int(open('/var/run/dynamite/logstash/logstash.pid').read())
        except (IOError, ValueError):
            self.pid = -1

    def start(self, stdout=False):
        """
        Start the LogStash process
        :param stdout: Print output to console
        :return: True if started successfully
        """
        self.pid = -1

        def start_shell_out():
            command = 'runuser -l dynamite -c "{} {}/bin/logstash ' \
                      '--quiet --path.settings={} & echo \$! > /var/run/dynamite/logstash/logstash.pid"'.format(
                utilities.get_environment_file_str(), self.config.ls_home, self.config.ls_path_conf)
            print(command)
            subprocess.call(command, shell=True)
        if not utilities.check_pid(self.pid):
            Process(target=start_shell_out).start()
        else:
            sys.stderr.write('[-] Logstash is already running on PID [{}]\n'.format(self.pid))
            return True
        retry = 0
        time.sleep(5)
        while retry < 6:
            start_message = '[+] [Attempt: {}] Starting Logstash on PID [{}]\n'.format(retry + 1, self.pid)
            try:
                with open('/var/run/dynamite/logstash/logstash.pid') as f:
                    self.pid = int(f.read())
                start_message = '[+] [Attempt: {}] Starting LogStash on PID [{}]\n'.format(retry + 1, self.pid)
                if stdout:
                    sys.stdout.write(start_message)
                if not utilities.check_pid(self.pid):
                    retry += 1
                    time.sleep(3)
                else:
                    return True
            except IOError:
                if stdout:
                    sys.stdout.write(start_message)
                retry += 1
                time.sleep(3)
        return False

    def stop(self, stdout=False):
        """
        Stop the LogStash process

        :param stdout: Print output to console
        :return: True if stopped successfully
        """
        alive = True
        while alive:
            try:
                if stdout:
                    sys.stdout.write('[+] Attempting to stop LogStash [{}]\n'.format(self.pid))
                os.kill(self.pid, signal.SIGTERM)
                time.sleep(1)
                alive = utilities.check_pid(self.pid)
            except Exception as e:
                sys.stderr.write('[-] An error occurred while attempting to stop LogStash: {}\n'.format(e))
                return False
        return True

    def restart(self, stdout=False):
        """
        Restart the LogStash process

        :param stdout: Print output to console
        :return: True if started successfully
        """
        self.stop(stdout=stdout)
        return self.start(stdout=stdout)

