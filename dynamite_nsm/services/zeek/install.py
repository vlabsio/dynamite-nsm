import os
import subprocess
import time
from typing import List, Optional

from dynamite_nsm import const, utilities
from dynamite_nsm.service_objects.zeek import node, local_site
from dynamite_nsm.services.base import install, systemctl
from dynamite_nsm.services.zeek import config

COMPILE_PROCESS_EXPECTED_LINE_COUNT = 6779


class InstallManager(install.BaseInstallManager):

    def __init__(self, configuration_directory: str, install_directory: str,
                 download_zeek_archive: Optional[bool] = True, stdout: Optional[bool] = False,
                 verbose: Optional[bool] = False):
        """
        :param configuration_directory: Path to the configuration directory (E.G /etc/dynamite/zeek/)
        :param install_directory: Path to the install directory (E.G /opt/dynamite/zeek/)
        :param download_zeek_archive: If True, download the Zeek archive from a mirror
        :param stdout: Print output to console
        :param verbose: Include detailed debug messages
        """
        self.configuration_directory = configuration_directory
        self.install_directory = install_directory
        self.stdout = stdout
        self.verbose = verbose

        super(InstallManager, self).__init__(name='zeek', verbose=verbose, stdout=stdout)
        if download_zeek_archive:
            self.logger.info("Attempting to download Zeek archive.")
            _, archive_name, self.local_mirror_root = self.download_from_mirror(const.ZEEK_MIRRORS)
            self.logger.info(f'Attempting to extract Zeek archive ({archive_name}).')
            self.extract_archive(os.path.join(const.INSTALL_CACHE, archive_name))
            self.logger.info("Extraction completed.")
        else:
            _, _, self.local_mirror_root = self.get_mirror_info(const.ZEEK_MIRRORS)

    def configure_compile_zeek(self, parallel_threads: Optional[int] = None) -> None:
        """
        Configure and build Zeek from source

        :param parallel_threads: Number of parallel threads to use during the compiling process
        """
        zeek_source_install_cache = os.path.join(const.INSTALL_CACHE, self.local_mirror_root)
        configure_args = [f'--prefix={self.install_directory}', f'--scriptdir={self.configuration_directory}',
                          '--enable-jemalloc']
        self.configure_source_package(zeek_source_install_cache, configure_args=configure_args)
        time.sleep(1)
        self.compile_source_package(zeek_source_install_cache,
                                    parallel_threads=parallel_threads,
                                    expected_lines_printed=COMPILE_PROCESS_EXPECTED_LINE_COUNT)

    def configure_compile_zeek_af_packet_plugin(self, parallel_threads: Optional[int] = None) -> None:
        """
        Configure and build AF_PACKET plugin

        :param parallel_threads: Number of parallel threads to use during the compiling process
        """
        zeek_source_install_cache = os.path.join(const.INSTALL_CACHE, self.local_mirror_root)
        zeek_af_packet_plugin_source = f'{const.DEFAULT_CONFIGS}/zeek/uncompiled_scripts/zeek-af_packet-plugin'
        configure_args = [f'--zeek-dist={zeek_source_install_cache}', f'--install-root={self.configuration_directory}']
        self.configure_source_package(zeek_af_packet_plugin_source, configure_args=configure_args)
        self.compile_source_package(zeek_af_packet_plugin_source, compile_args=None,
                                    parallel_threads=parallel_threads,
                                    expected_lines_printed=None)
        self.copy_file_or_directory_to_destination(f'{self.configuration_directory}/Zeek_AF_Packet',
                                                   f'{self.install_directory}/lib/zeek/plugins/Zeek_AF_Packet')

    def configure_compile_zeek_community_id_plugin(self, parallel_threads: Optional[int] = None) -> None:
        """
        Configure and build Community_ID plugin

        :param parallel_threads: Number of parallel threads to use during the compiling process
        """
        zeek_source_install_cache = os.path.join(const.INSTALL_CACHE, self.local_mirror_root)
        zeek_community_id_plugin_source = f'{const.DEFAULT_CONFIGS}/zeek/uncompiled_scripts/zeek-community-id'
        configure_args = [f'--zeek-dist={zeek_source_install_cache}', f'--install-root={self.configuration_directory}']
        self.configure_source_package(zeek_community_id_plugin_source, configure_args=configure_args)
        self.compile_source_package(zeek_community_id_plugin_source, compile_args=None,
                                    parallel_threads=parallel_threads,
                                    expected_lines_printed=None)
        self.copy_file_or_directory_to_destination(f'{self.configuration_directory}/Corelight_CommunityID',
                                                   f'{self.install_directory}/lib/zeek/plugins/Corelight_CommunityID')

    def create_update_zeek_environment_variables(self) -> None:
        """
        Creates all the required Zeek environmental variables
        """
        self.create_update_env_variable('ZEEK_HOME', self.install_directory)
        self.create_update_env_variable('ZEEK_SCRIPTS', self.configuration_directory)

    def install_zeek_dependencies(self) -> None:
        """
        Install Zeek dependencies (And PowerTools repo if on redhat based distro)
        """

        def install_powertools_rhel(pacman_type):
            """
            Workaround for RHEL based distros to ensure they have access to the powertools repo

            :param pacman_type: yum or apt-get
            """
            if pacman_type != 'yum':
                self.logger.info('Skipping RHEL PowerTools install, as it is not needed on this distribution.')
                return
            self.install_dependencies(yum_packages=['dnf-plugins-core'])
            enable_powertools_p = subprocess.Popen(['yum', 'config-manager', '--set-enabled', 'PowerTools'],
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            enable_powertools_p.communicate()
            if enable_powertools_p.returncode == 0:
                self.logger.info("Installed PowerTools.")

        apt_get_packages = \
            ['bison', 'cmake', 'cmake3', 'flex', 'g++', 'gcc', 'libjemalloc-dev', 'libpcap-dev', 'libssl-dev',
             'linux-headers-$(uname -r)', 'linux-headers-generic', 'make', 'python-dev', 'swig', 'tar', 'zlib1g-dev']

        yum_packages = \
            ['bison', 'cmake', 'cmake3', 'flex', 'gcc', 'gcc-c++', 'jemalloc-devel', 'kernel-devel', 'libpcap-devel',
             'make', 'openssl-devel', 'python2-devel', 'python3-devel', 'swig', 'tar', 'zlib-devel']

        self.install_dependencies(apt_get_packages=apt_get_packages, yum_packages=yum_packages,
                                  pre_install_function=install_powertools_rhel)

    def setup(self, capture_network_interfaces: Optional[List[str]] = None):
        """
        Install Zeek

        :param capture_network_interfaces: A list of network interfaces to capture on (E.G ["mon0", "mon1"])
        """
        if not capture_network_interfaces:
            capture_network_interfaces = utilities.get_network_interface_names()
        if not self.validate_capture_network_interfaces(capture_network_interfaces):
            raise install.NetworkInterfaceNotFound(capture_network_interfaces)
        sysctl = systemctl.SystemCtl()
        self.install_zeek_dependencies()
        self.create_update_zeek_environment_variables()
        self.logger.debug(f'Creating directory: {self.configuration_directory}')
        utilities.makedirs(self.configuration_directory)
        self.logger.debug(f'Creating directory: {self.install_directory}')
        utilities.makedirs(self.install_directory)
        self.logger.info('Setting up Zeek from source. This can take up to 15 minutes.')
        if self.stdout:
            utilities.print_coffee_art()
        self.configure_compile_zeek()
        self.logger.info('Adding AF_PACKET socket support.')
        self.configure_compile_zeek_af_packet_plugin()
        self.logger.info('Adding CommunityID support.')
        self.configure_compile_zeek_community_id_plugin()

        self.copy_file_or_directory_to_destination(f'{const.DEFAULT_CONFIGS}/zeek/broctl-nodes.cfg',
                                                   f'{self.install_directory}/etc/node.cfg')
        self.copy_file_or_directory_to_destination(f'{const.DEFAULT_CONFIGS}/zeek/local.zeek',
                                                   f'{self.configuration_directory}/site/local.zeek')
        self.copy_file_or_directory_to_destination(f'{const.DEFAULT_CONFIGS}/zeek/dynamite_extra_scripts',
                                                   self.configuration_directory)

        # Optimize Configurations
        site_local_config = config.SiteLocalConfigManager(self.configuration_directory, stdout=self.stdout,
                                                          verbose=self.verbose)
        node_config = config.NodeConfigManager(self.install_directory, stdout=self.stdout, verbose=self.verbose)
        node_config.workers = node.Workers()
        for worker in node_config.get_optimal_zeek_worker_config(capture_network_interfaces):
            node_config.workers.add_worker(
                worker=worker
            )
        self.logger.info('Applying node configuration.')
        node_config.commit()

        # Enable our extra scripts
        extra_scripts_destination_directory = f'{self.configuration_directory}/dynamite_extra_scripts'
        for script_dir in os.listdir(extra_scripts_destination_directory):
            site_local_config.scripts.add(
                local_site.Script(
                    name=f'{extra_scripts_destination_directory}/{script_dir}',
                    enabled=True
                )
            )
        self.logger.info('Applying local site configuration.')
        site_local_config.commit()

        # Fix Permissions
        self.logger.info('Setting up file permissions.')
        utilities.set_ownership_of_file(self.configuration_directory, user='dynamite', group='dynamite')
        utilities.set_ownership_of_file(self.install_directory, user='dynamite', group='dynamite')

        self.logger.info(f'Installing service -> {const.DEFAULT_CONFIGS}/systemd/zeek.service')
        sysctl.install_and_enable(os.path.join(const.DEFAULT_CONFIGS, 'systemd', 'zeek.service'))


if __name__ == '__main__':
    install_mngr = InstallManager(
        install_directory=f'{const.INSTALL_PATH}/zeek',
        configuration_directory=f'{const.CONFIG_PATH}/zeek',
        download_zeek_archive=False,
        stdout=True,
        verbose=True
    )
    install_mngr.setup()
