#! /usr/bin/python
import os
import sys
import pty
import json
import getpass
import argparse
import traceback

from dynamite_nsm import utilities, updater
from dynamite_nsm.services.helpers import oinkmaster
from dynamite_nsm.services import agent, elasticsearch, logstash, kibana, monitor, suricata, zeek
from dynamite_nsm.guis import zeek_node_config_gui, zeek_script_config_gui, suricata_interface_config_gui,\
    suricata_rule_config_gui


COMPONENTS = [
    'agent', 'monitor', 'elasticsearch', 'logstash', 'kibana', 'suricata-rules', 'mirrors', 'default-configs'
]

COMMANDS = [
    'prepare', 'install', 'uninstall', 'start', 'stop', 'restart', 'status', 'profile', 'update', 'configure',
    'point', 'chpasswd'
]


def _get_parser():
    parser = argparse.ArgumentParser(
        description='Install/Configure the Dynamite Network Monitor.'
    )
    parser.add_argument('command', metavar='command', type=str,
                        help='An action to perform [{}]'.format('|'.join(COMMANDS)))

    parser.add_argument('component', metavar='component', type=str,
                        help='The component to perform an action against [{}]'.format('|'.join(COMPONENTS)))

    parser.add_argument('--interface', type=str, dest='network_interface', required='install' in sys.argv
                                                                            and 'agent' in sys.argv,
                        help='A network interface to analyze traffic on.')

    parser.add_argument('--agent-label', type=str, dest='agent_label', required='install' in sys.argv and 'agent' in
                                                                                sys.argv,
                        help='A descriptive label associated with the agent. '
                             'This could be a location on your network (VLAN01),'
                             'or the types of servers on a segment (E.G Workstations-US-1).')

    parser.add_argument('--ls-host', type=str, dest='ls_host', required=('point' in sys.argv)
                                                                  or ('install' in sys.argv and 'agent' in sys.argv),
                        help='Target Logstash instance; A valid Ipv4/Ipv6 address or hostname')

    parser.add_argument('--ls-port', type=int, dest='ls_port', default=5044,
                        help='Target Logstash instance; A valid port [1-65535]')

    parser.add_argument('--es-host', type=str, dest='es_host',
                        required=(not elasticsearch.ElasticProfiler().is_installed
                                  and 'install' in sys.argv and ('kibana' in sys.argv or 'logstash' in sys.argv)
                                  ),
                        help='Target ElasticSearch cluster; A valid Ipv4/Ipv6 address or hostname')

    parser.add_argument('--es-port', type=int, dest='es_port', default=9200,
                        help='Target ElasticSearch cluster; A valid port [1-65535]')

    # Config Modes

    parser.add_argument('--zeek-cluster', default=False, dest='config_zeek_cluster', action='store_true',
                        help='Enter into Zeek Cluster Configuration Mode.')
    parser.add_argument('--zeek-scripts', default=False, dest='config_zeek_scripts', action='store_true',
                        help='Enter into Zeek Script Configuration Mode.')
    parser.add_argument('--suricata-interfaces', default=False, dest='config_suricata_interfaces', action='store_true',
                        help='Enter into Suricata Interface Configuration Mode.')
    parser.add_argument('--suricata-rules', default=False, dest='config_suricata_rules', action='store_true',
                        help='Enter into Suricata Rule Configuration Mode.')
    parser.add_argument('--zeek-shell', default=False, dest='config_zeek_shell', action='store_true',
                        help='Enter into ZeekCtl interactive shell')

    parser.add_argument('--debug', default=False, dest='debug', action='store_true',
                        help='Include detailed error messages in console.')

    return parser


def _fatal_exception(action, component, debug=False):
    message = '[-] {}.{} failed. Is it installed?\n' \
              '[-] \'dynamite install {}\'\n'.format(action, component, component)
    sys.stderr.write(message)
    if debug:
        sys.stderr.write('\n\n========== DEBUG ==========\n\n')
        traceback.print_exc(file=sys.stderr)
    sys.exit(1)


def _not_installed(action, component):
    _fatal_exception(action, component, debug=False)


def is_first_install():
    if not os.path.exists('/root/.dynamite'):
        return True
    return False


def mark_first_install():
    with open('/root/.dynamite', 'w') as f:
        f.write('')


if __name__ == '__main__':
    if not utilities.is_root():
        sys.stderr.write('[-] This script must be run as root.\n')
        sys.exit(1)
    parser = _get_parser()
    args = parser.parse_args()
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)
    if is_first_install():
        config_update_successful = updater.update_default_configurations()
        mirror_update_successful = updater.update_mirrors()
        if config_update_successful and mirror_update_successful:
            mark_first_install()
        else:
            sys.exit(1)
    utilities.create_dynamite_root_directory()
    utilities.create_dynamite_environment_file()
    if args.command == 'point':
        if args.component == 'agent':
            agent.point_agent(args.ls_host, args.ls_port)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'chpasswd':
        if args.component == 'elasticsearch':
            if elasticsearch.change_elasticsearch_password(
                old_password=getpass.getpass('Enter the old ElasticSearch password: '),
                password=utilities.prompt_password('Enter the new ElasticSearch password: '), stdout=True
            ):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to reset ElasticSearch password.\n')
                sys.exit(1)
        elif args.component == 'logstash':
            if logstash.change_logstash_elasticsearch_password(password=utilities.prompt_password(
                'Enter the new password (same as ElasticSearch): '
            ), prompt_user=True, stdout=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to reset LogStash -> ElasticSearch password.\n')
                sys.exit(1)
        elif args.component == 'kibana':
            if kibana.change_kibana_elasticsearch_password(password=utilities.prompt_password(
                'Enter the new password (same as ElasticSearch): '
            ),
                                                           prompt_user=True, stdout=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to reset Kibana -> ElasticSearch password.\n')
                sys.exit(1)
        elif args.component == 'monitor':
            if monitor.change_monitor_password(old_password=getpass.getpass('Enter the old ElasticSearch password: '),
                                               password=utilities.prompt_password(
                                                   'Enter the new ElasticSearch password: ')
                                               ):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to reset Monitor password.\n')
                sys.exit(1)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'prepare':
        if args.component == 'agent':
            agent.prepare_agent()
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command in ['config', 'configure']:
        if args.component == 'agent':
            agent_config_modes = ['--suricata-rules', '--suricata-interfaces',
                                  '--zeek-cluster', '--zeek-scripts', '--zeek-shell']
            if not zeek.ZeekProfiler().is_installed:
                sys.stderr.write('[-] The agent must be installed before it can be configured.')
                sys.exit(1)
            if args.config_zeek_cluster:
                try:
                    zeek_node_config = zeek_node_config_gui.ZeekNodeConfiguratorApp()
                    zeek_node_config.run()
                except KeyboardInterrupt:
                    sys.stdout.write('[+] Be sure to restart the agent for changes to take effect!\n')
                    sys.stdout.flush()
                sys.exit(0)
            elif args.config_zeek_scripts:
                try:
                    zeek_script_config = zeek_script_config_gui.ZeekScriptConfiguratorApp()
                    zeek_script_config.run()
                except KeyboardInterrupt:
                    sys.stdout.write('[+] Be sure to restart the agent for changes to take effect!\n')
                    sys.stdout.flush()
                sys.exit(0)
            elif args.config_suricata_interfaces:
                try:
                    suricata_interface_config = suricata_interface_config_gui.SuricataInstanceConfiguratorApp()
                    suricata_interface_config.run()
                except KeyboardInterrupt:
                    sys.stdout.write('[+] Be sure to restart the agent for changes to take effect!\n')
                    sys.stdout.flush()
                sys.exit(0)
            elif args.config_suricata_rules:
                try:
                    suricata_rule_config = suricata_rule_config_gui.SuricataRuleConfiguratorApp()
                    suricata_rule_config.run()
                except KeyboardInterrupt:
                    sys.stdout.write('[+] Be sure to restart the agent for changes to take effect!\n')
                    sys.stdout.flush()
                sys.exit(0)
            elif args.config_zeek_shell:
                env_variables = environment_variables = utilities.get_environment_file_dict()
                pty.spawn(os.path.join(env_variables['ZEEK_HOME'], 'bin/broctl'))
            else:
                sys.stderr.write('[-] Invalid/Empty agent configuration mode - valid modes: {}\n'.format(
                    agent_config_modes)
                )
                sys.exit(1)
    elif args.command == 'install':
        if args.component == 'elasticsearch':
            if elasticsearch.install_elasticsearch(
                password=utilities.prompt_password(prompt='Create a password for logging into ElasticSearch: '),
                                                   stdout=True, create_dynamite_user=True, install_jdk=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to install ElasticSearch.\n')
                sys.exit(1)
        elif args.component == 'logstash':
            if logstash.install_logstash(elasticsearch_host=args.es_host, elasticsearch_port=args.es_port,
                                         elasticsearch_password=utilities.prompt_password(
                                             'Enter the password used for logging into ElasticSearch: '
                                         ),
                                         stdout=True, create_dynamite_user=True, install_jdk=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to install Logstash.\n')
                sys.exit(1)
        elif args.component == 'kibana':
            if not elasticsearch.ElasticProfiler().is_installed:
                if kibana.install_kibana(elasticsearch_host=args.es_host, elasticsearch_port=args.es_port,
                                         elasticsearch_password=utilities.prompt_password(
                                             'Enter the password used for logging into ElasticSearch: '
                                         ),
                                         stdout=True, create_dynamite_user=True, install_jdk=True):
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to install Kibana.\n')
                    sys.exit(1)
            else:
                if kibana.install_kibana(elasticsearch_host=args.es_host, elasticsearch_port=args.es_port,
                                         elasticsearch_password=utilities.prompt_password(),
                                         stdout=True, create_dynamite_user=True, install_jdk=True):
                    env_variables = environment_variables = utilities.get_environment_file_dict()
                    kb_config = kibana.KibanaConfigurator(env_variables['KIBANA_PATH_CONF'])
                    sys.stdout.write('\n[+] Once started Kibana will be accessible at: ')
                    sys.stdout.write('\n\tHOST: http://{}{}\n'.format(kb_config.get_server_host(),
                                                                      kb_config.get_server_port()))
                    sys.stdout.write('\n\tUSER: elastic\n')
                    sys.stdout.write('\n\tPASSWORD: {}\n'.format(kb_config.get_elasticsearch_password()))
                    sys.stdout.flush()
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to install Kibana.\n')
                    sys.exit(1)
        elif args.component == 'monitor':
            installed = monitor.install_monitor(elasticsearch_password=utilities.prompt_password(
                'Create a password for logging into ElasticSearch: '
            ))
            if installed:
                env_variables = environment_variables = utilities.get_environment_file_dict()
                kb_config = kibana.KibanaConfigurator(env_variables['KIBANA_PATH_CONF'])
                sys.stdout.write('\n[+] Once started Kibana will be accessible at: ')
                sys.stdout.write('\n\tHOST: http://{}:{}'.format(kb_config.get_server_host(),
                                                                kb_config.get_server_port()))
                sys.stdout.write('\n\tUSER: elastic')
                sys.stdout.write('\n\tPASSWORD: {}\n'.format(kb_config.get_elasticsearch_password()))
                sys.stdout.flush()
                sys.exit(0)
            sys.exit(1)

        elif args.component == 'agent':
            installed = agent.install_agent(agent_label=args.agent_label, network_interface=args.network_interface,
                                logstash_target='{}:{}'.format(args.ls_host, args.ls_port))
            if installed:
                try:
                    zeek_node_config_gui.ZeekNodeConfiguratorApp().run()
                except KeyboardInterrupt:
                    pass
                try:
                    zeek_script_config_gui.ZeekScriptConfiguratorApp().run()
                except KeyboardInterrupt:
                    pass
                try:
                    suricata_interface_config_gui.SuricataInstanceConfiguratorApp().run()
                except KeyboardInterrupt:
                    pass
                try:
                    suricata_rule_config_gui.SuricataRuleConfiguratorApp().run()
                except KeyboardInterrupt:
                    pass
                sys.stdout.write('[+] To configure the agent: \n')
                sys.stdout.write('\n\tdynamite configure agent -- <options>\n\n')
                sys.stdout.write('[+] To start the agent:\n')
                sys.stdout.write('\n\tdynamite start agent\n')
                sys.stdout.flush()
                sys.exit(0)
            sys.exit(1)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'uninstall':
        if args.component == 'elasticsearch':
            if elasticsearch.uninstall_elasticsearch(stdout=True, prompt_user=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to uninstall ElasticSearch.\n')
                sys.exit(1)
        elif args.component == 'logstash':
            if logstash.uninstall_logstash(stdout=True, prompt_user=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to uninstall LogStash.\n')
                sys.exit(1)
        elif args.component == 'kibana':
            if kibana.uninstall_kibana(stdout=True, prompt_user=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to uninstall Kibana.\n')
                sys.exit(1)
        elif args.component == 'monitor':
            if monitor.uninstall_monitor(prompt_user=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to uninstall Monitor.\n')
                sys.exit(1)
        elif args.component == 'agent':
            if agent.uninstall_agent(prompt_user=True):
                sys.exit(0)
            else:
                sys.stderr.write('[-] Failed to uninstall Agent.\n')
                sys.exit(1)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'start':
        if args.component == 'elasticsearch':
            try:
                sys.stdout.write('[+] Starting ElasticSearch.\n')
                started = elasticsearch.ElasticProcess().start(stdout=True)
                if started:
                    sys.stdout.write('[+] ElasticSearch started successfully. Check its status at any time with: '
                                     '\'dynamite status elasticsearch\'.\n')
                    sys.exit(0)
                elif not elasticsearch.ElasticProfiler(stderr=False).is_installed:
                    _not_installed('start', 'elasticsearch')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to start ElasticSearch.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('start', 'elasticsearch', args.debug)
        elif args.component == 'logstash':
            try:
                sys.stdout.write('[+] Starting LogStash\n')
                started = logstash.LogstashProcess().start(stdout=True)
                if started:
                    sys.stdout.write('[+] LogStash started successfully. Check its status at any time with: '
                                     '\'dynamite status logstash\'.\n')
                    sys.exit(0)
                elif not logstash.LogstashProfiler(stderr=False).is_installed:
                    _not_installed('start', 'logstash')
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] An error occurred while attempting to start LogStash.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('start', 'logstash', args.debug)
        elif args.component == 'kibana':
            try:
                sys.stdout.write('[+] Starting Kibana\n')
                started = kibana.KibanaProcess().start(stdout=True)
                if started:
                    sys.stdout.write('[+] Kibana started successfully. Check its status at any time with: '
                                     '\'dynamite status kibana\'.\n')
                    sys.exit(0)
                elif not kibana.KibanaProfiler(stderr=False).is_installed:
                    _not_installed('start', 'kibana')
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] An error occurred while attempting to start Kibana.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('start', 'kibana', args.debug)
        elif args.component == 'monitor':
            try:
                if monitor.start_monitor():
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to start monitor.')
                    sys.exit(1)
            except Exception:
                _fatal_exception('start', 'monitor', args.debug)
        elif args.component == 'agent':
            try:
                if agent.start_agent():
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to start agent.')
                    sys.exit(1)
            except Exception:
                _fatal_exception('start', 'agent', args.debug)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'status':
            if args.component == 'elasticsearch':
                if not elasticsearch.ElasticProfiler(stderr=False).is_installed:
                    _not_installed('start', 'elasticsearch')
                    sys.exit(0)
                try:
                    sys.stdout.write(json.dumps(elasticsearch.ElasticProcess().status(), indent=1) + '\n')
                    sys.exit(0)
                except Exception:
                    _fatal_exception('status', 'elasticsearch', args.debug)
            elif args.component == 'logstash':
                if not logstash.LogstashProfiler(stderr=False).is_installed:
                    _not_installed('status', 'logstash')
                    sys.exit(0)
                try:
                    sys.stdout.write(json.dumps(logstash.LogstashProcess().status(), indent=1) + '\n')
                except Exception:
                    _fatal_exception('status', 'logstash', args.debug)
            elif args.component == 'kibana':
                if not kibana.KibanaProfiler(stderr=False).is_installed:
                    _not_installed('status', 'kibana')
                    sys.exit(0)
                try:
                    sys.stdout.write(json.dumps(kibana.KibanaProcess().status(), indent=1) + '\n')
                except Exception:
                    _fatal_exception('status', 'kibana', args.debug)
            elif args.component == 'monitor':
                try:
                    es_status, ls_status, kb_status = monitor.status_monitor()
                    sys.stdout.write(json.dumps(dict(
                        ElasticSearch=es_status,
                        LogStash=ls_status,
                        Kibana=kb_status
                    ), indent=1))
                    sys.stdout.flush()
                    sys.exit(0)
                except Exception:
                    _fatal_exception('status', 'monitor', args.debug)
            elif args.component == 'agent':
                try:
                    agent_status = agent.status_agent()
                    sys.stdout.write(json.dumps(agent_status, indent=1))
                    sys.stdout.flush()
                    sys.exit(0)
                except Exception:
                    _fatal_exception('status', 'agent', args.debug)
            else:
                sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
                sys.exit(1)
    elif args.command == 'stop':
        if args.component == 'elasticsearch':
            try:
                sys.stdout.write('[+] Stopping ElasticSearch.\n')
                stopped = elasticsearch.ElasticProcess().stop(stdout=True)
                if not elasticsearch.ElasticProfiler(stderr=False).is_installed:
                    _not_installed('stop', 'kibana')
                    sys.exit(0)
                elif stopped:
                    sys.stdout.write('[+] ElasticSearch stopped successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to stop ElasticSearch.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('stop', 'elasticsearch', args.debug)
        elif args.component == 'logstash':
            try:
                sys.stdout.write('[+] Stopping LogStash.\n')
                stopped = logstash.LogstashProcess().stop(stdout=True)
                if not logstash.LogstashProfiler(stderr=False).is_installed:
                    _not_installed('stop', 'logstash')
                    sys.exit(0)
                elif stopped:
                    sys.stdout.write('[+] LogStash stopped successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to stop LogStash.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('stop', 'logstash', args.debug)
        elif args.component == 'kibana':
            try:
                sys.stdout.write('[+] Stopping Kibana.\n')
                stopped = kibana.KibanaProcess().stop(stdout=True)
                if not kibana.KibanaProfiler(stderr=False).is_installed:
                    _not_installed('stop', 'kibana')
                    sys.exit(0)
                elif stopped:
                    sys.stdout.write('[+] Kibana stopped successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to stop Kibana.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('stop', 'kibana', args.debug)
        elif args.component == 'monitor':
            try:
                if monitor.stop_monitor():
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to stop monitor.')
            except Exception:
                _fatal_exception('stop', 'monitor', args.debug)
        elif args.component == 'agent':
            try:
                if agent.stop_agent():
                    sys.exit(0)
                else:
                    sys.stderr.write('[-] Failed to stop agent.')
            except Exception:
                _fatal_exception('stop', 'agent', args.debug)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'restart':
        if args.component == 'elasticsearch':
            try:
                sys.stdout.write('[+] Restarting ElasticSearch.\n')
                restarted = elasticsearch.ElasticProcess().restart(stdout=True)
                if not elasticsearch.ElasticProfiler(stderr=False).is_installed:
                    _not_installed('restart', 'kibana')
                    sys.exit(0)
                elif restarted:
                    sys.stdout.write('[+] ElasticSearch restarted successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to start ElasticSearch.\n')
                    sys.exit(0)
            except Exception:
                _fatal_exception('restart', 'elasticsearch', args.debug)
        elif args.component == 'logstash':
            try:
                sys.stdout.write('[+] Restarting LogStash.\n')
                restarted = logstash.LogstashProcess().restart(stdout=True)
                if not logstash.LogstashProfiler(stderr=False).is_installed:
                    _not_installed('restart', 'logstash')
                    sys.exit(0)
                elif restarted:
                    sys.stdout.write('[+] LogStash restarted successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to start LogStash.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('restart', 'logstash', args.debug)
        elif args.component == 'kibana':
            try:
                sys.stdout.write('[+] Restarting Kibana.\n')
                restarted = kibana.KibanaProcess().restart(stdout=True)
                if not kibana.KibanaProfiler(stderr=False).is_installed:
                    _not_installed('restart', 'logstash')
                    sys.exit(0)
                elif restarted:
                    sys.stdout.write('[+] Kibana restarted successfully.\n')
                    sys.exit(0)
                else:
                    sys.stdout.write('[-] An error occurred while attempting to start Kibana.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('restart', 'kibana', args.debug)
        elif args.component == 'monitor':
            try:
                if monitor.stop_monitor():
                    if monitor.start_monitor():
                        sys.stdout.write('[+] Monitor restarted successfully.\n')
                        sys.exit(0)
                    else:
                        sys.stdout.write('[-] Monitor failed to start.\n')
                        sys.exit(1)
                else:
                    sys.stdout.write('[-] Monitor failed to stop.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('restart', 'monitor', args.debug)
        elif args.component == 'agent':
            try:
                if agent.stop_agent():
                    if agent.start_agent():
                        sys.stdout.write('[+] Agent restarted successfully.\n')
                        sys.exit(0)
                    else:
                        sys.stdout.write('[-] Agent failed to start.\n')
                        sys.exit(1)
                else:
                    sys.stdout.write('[-] Agent failed to stop.\n')
                    sys.exit(1)
            except Exception:
                _fatal_exception('restart', 'agent', args.debug)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'profile':
        if args.component == 'elasticsearch':
            try:
                sys.stdout.write('[+] Profiling ElasticSearch.\n')
                profile_result = elasticsearch.ElasticProfiler(stderr=True)
                sys.stdout.write('[+]  ELASTICSEARCH.INSTALLED: {}\n'.format(profile_result.is_installed))
                sys.stdout.write('[+] ELASTICSEARCH.CONFIGURED: {}\n'.format(profile_result.is_configured))
                sys.stdout.write('[+]    ELASTICSEARCH.RUNNING: {}\n'.format(profile_result.is_running))
                sys.stdout.write('[+]     ELASTICSEARCH.API_UP: {}\n'.format(profile_result.is_listening))
                sys.exit(0)
            except Exception:
                _fatal_exception('profile', 'elasticsearch', args.debug)
        elif args.component == 'logstash':
            try:
                sys.stdout.write('[+] Profiling LogStash.\n')
                profile_result = logstash.LogstashProfiler(stderr=True)
                sys.stdout.write('[+]            LOGSTASH.INSTALLED: {}\n'.format(profile_result.is_installed))
                sys.stdout.write('[+]  LOGSTASH.ELASIFLOW.INSTALLED: {}\n'.format(profile_result.is_installed))
                sys.stdout.write('[+]           LOGSTASH.CONFIGURED: {}\n'.format(profile_result.is_configured))
                sys.stdout.write('[+]              LOGSTASH.RUNNING: {}\n'.format(profile_result.is_running))
                sys.exit(0)
            except Exception:
                _fatal_exception('profile', 'elasticsearch', args.debug)
        elif args.component == 'kibana':
            try:
                sys.stdout.write('[+] Profiling Kibana.\n')
                profile_result = kibana.KibanaProfiler(stderr=True)
                sys.stdout.write('[+]  KIBANA.INSTALLED: {}\n'.format(profile_result.is_installed))
                sys.stdout.write('[+] KIBANA.CONFIGURED: {}\n'.format(profile_result.is_configured))
                sys.stdout.write('[+]    KIBANA.RUNNING: {}\n'.format(profile_result.is_running))
                sys.stdout.write('[+]     KIBANA.API_UP: {}\n'.format(profile_result.is_listening))
                sys.exit(0)
            except Exception:
                _fatal_exception('profile', 'kibana', args.debug)
        elif args.component == 'agent':
            try:
                profile_result = agent.profile_agent()
                sys.stdout.write('[+]  PF_RING.INSTALLED: {}\n'.format(profile_result['PF_RING']['INSTALLED']))
                sys.stdout.write('[+]    PF_RING.RUNNING: {}\n'.format(profile_result['PF_RING']['RUNNING']))
                sys.stdout.write('[+]     ZEEK.INSTALLED: {}\n'.format(profile_result['ZEEK']['INSTALLED']))
                sys.stdout.write('[+]       ZEEK.RUNNING: {}\n'.format(profile_result['ZEEK']['RUNNING']))
                sys.stdout.write('[+] SURICATA.INSTALLED: {}\n'.format(profile_result['SURICATA']['INSTALLED']))
                sys.stdout.write('[+]   SURICATA.RUNNING: {}\n'.format(profile_result['SURICATA']['RUNNING']))
                sys.stdout.write('[+] FILEBEAT.INSTALLED: {}\n'.format(profile_result['FILEBEAT']['INSTALLED']))
                sys.stdout.write('[+]   FILEBEAT.RUNNING: {}\n'.format(profile_result['FILEBEAT']['RUNNING']))
                sys.stdout.flush()
            except Exception:
                _fatal_exception('profile', 'agent', args.debug)
        elif args.component == 'monitor':
            try:
                profile_result = monitor.profile_monitor()
                sys.stdout.write('[+]  ELASTICSEARCH.INSTALLED: {}\n'.format(profile_result['ELASTICSEARCH']['INSTALLED']))
                sys.stdout.write('[+]    ELASTICSEARCH.RUNNING: {}\n'.format(profile_result['ELASTICSEARCH']['RUNNING']))
                sys.stdout.write('[+]  ELASTICSEARCH.LISTENING: {}\n'.format(profile_result['ELASTICSEARCH']['LISTENING']))
                sys.stdout.write('[+]       LOGSTASH.INSTALLED: {}\n'.format(profile_result['LOGSTASH']['INSTALLED']))
                sys.stdout.write('[+]         LOGSTASH.RUNNING: {}\n'.format(profile_result['LOGSTASH']['RUNNING']))
                sys.stdout.write('[+]         KIBANA.INSTALLED: {}\n'.format(profile_result['KIBANA']['INSTALLED']))
                sys.stdout.write('[+]           KIBANA.RUNNING: {}\n'.format(profile_result['KIBANA']['RUNNING']))
                sys.stdout.write('[+]         KIBANA.LISTENING: {}\n'.format(profile_result['KIBANA']['LISTENING']))
                sys.stdout.flush()
            except Exception:
                _fatal_exception('profile', 'agent', args.debug)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    elif args.command == 'update':
        suricata_profiler = suricata.SuricataProfiler()
        if args.component == 'default-configs':
            updater.update_default_configurations()
            sys.exit(0)
        elif args.component == 'mirrors':
            updater.update_mirrors()
            sys.exit(0)
        elif args.component == 'suricata-rules':
            if suricata_profiler.is_installed:
                environment_variables = utilities.get_environment_file_dict()
                suricata_config_dir = environment_variables.get('SURICATA_CONFIG')
                suricata_install_dir = environment_variables.get('SURICATA_HOME')
                oinkmaster_install_dir = os.path.join(suricata_install_dir, 'oinkmaster')
                oinkmaster.update_suricata_rules()
                sys.exit(0)
            else:
                sys.stderr.write("[-] Suricata is not installed. You must install the agent before you can update "
                                 "rulesets.\n 'dynamite install agent'\n")
                sys.exit(1)
        else:
            sys.stderr.write('[-] Unrecognized component - {}\n'.format(args.component))
            sys.exit(1)
    else:
        sys.stderr.write('[-] Unrecognized command - {}\n'.format(args.command))
        sys.exit(1)
