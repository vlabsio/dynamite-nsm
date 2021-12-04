from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

from tabulate import tabulate

from dynamite_nsm.cmd.base_interface import BaseInterface
from dynamite_nsm.cmd.base_interface import RESERVED_VARIABLE_NAMES
from dynamite_nsm.cmd.inspection_helpers import ArgparseParameters
from dynamite_nsm.cmd.inspection_helpers import get_function_definition
from dynamite_nsm.services.base.config_objects import generic
from dynamite_nsm.services.base.config_objects.filebeat import targets

"""
Commandline interface wrappers for services.base.config_objects
"""


class AnalyzersInterface(BaseInterface):
    """
    Convert any `generic.Analyzers` derived class into a commandline utility (E.G Zeek scripts, signatures, and redefs
    as well as Suricata rule-sets
    """

    def __init__(self, config_obj: generic.Analyzers):
        """
        Setup the interface
        Args:
            config_obj: A complex config object that contains one or more `Analyzers`
        """
        super().__init__()
        self.config_obj = config_obj
        self.changed_rows = []

    @staticmethod
    def build_parser(interface: AnalyzersInterface, parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        """ Build a parser from any `AnalysisInterface` and `argparse.ArgumentParser` derived class
        Args:
            parser: The `argparse.ArgumentParser` instance that you want to add a new parser too
            interface: The `AnalyzerInterface` instance you wish to append

        Returns:
            An argument parser instance combined with the instantiated `AnalyzersInterface` derived class
        """
        choices = []
        for analyzer in interface.config_obj.analyzers:
            choices.append(analyzer.id)
        parser.add_argument('--ids', dest='analyzer_ids', nargs='+', type=int, default=[],
                            help='Specify one or more ids for the config object you want to work with.')
        parser.add_argument('--enable', dest='enable', action='store_true', help=f'Enable selected object.')
        parser.add_argument('--disable', dest='disable', action='store_true', help=f'Disable selected object')
        if getattr(interface.config_obj.analyzers[0], 'value', None):
            parser.add_argument('--value', dest='value', type=str,
                                help='The value associated with the selected object')

        return parser

    def get_parser(self) -> argparse.ArgumentParser:
        """Get the current interface as an `argparse.ArgumentParser` instance

        Returns:
            An argparse.ArgumentParser instance for the instantiated `AnalyzerInterface` derived class
        """
        parser = argparse.ArgumentParser()
        return self.build_parser(self, parser)

    def execute(self, args: argparse.Namespace) -> Any:
        """Interpret the results of an `argparse.ArgumentParser.parse_args()` method and perform one or more operations.
        Args:
            args: `argparse.Namespace` created by a method such as `argparse.ArgumentParser().parse_args()`

        Returns:
            Any value; completely depends on the parent interface's `ConfigManager.commit` method
        """
        self.changed_rows = []
        headers = ['Id', 'Name', 'Enabled', 'Value']
        table = [headers]
        selected_items = []
        for analyzer in self.config_obj.analyzers:
            analyzer_value = 'N/A'
            if getattr(analyzer, 'value', None):
                analyzer_value = analyzer.value
            row = [analyzer.id, analyzer.name, analyzer.enabled, analyzer_value]
            table.append(row)
            if analyzer.id in list(args.analyzer_ids):
                selected_analyzer = analyzer
                if selected_analyzer:
                    if args.disable:
                        selected_analyzer.enabled = False
                    elif args.enable:
                        selected_analyzer.enabled = True
                    if getattr(args, 'value', None):
                        if not str(args.value).endswith(';'):
                            args.value = args.value + ';'
                        selected_analyzer.value = args.value
                    selected_items.append([selected_analyzer.id, selected_analyzer.name, selected_analyzer.enabled,
                                           selected_analyzer.value if selected_analyzer.value else 'N/A'])

        if not args.analyzer_ids:
            all_analyzers = []
            for analyzer in self.config_obj.analyzers:
                all_analyzers.append(
                    [analyzer.id, analyzer.name, analyzer.enabled, analyzer.value if analyzer.value else 'N/A'])
            return tabulate(headers=headers, tabular_data=all_analyzers, tablefmt='fancy_grid')
        else:
            self.changed_rows = selected_items
            return self.config_obj


class FilebeatTargetsInterface(BaseInterface):
    """
    Convert any Filebeat `BaseTargets` derived class into a commandline utility.
    """

    def __init__(self, config_obj: targets.BaseTargets, defaults: Optional[Dict] = None):
        """
        Setup the interface
        Args:
            config_obj: A Filebeat specific complex config object that specifies a downstream target config - where
            to send logs.
            defaults: Any default commandline arguments you wish to define ahead of time `dict(arg_name=arg_value)`
        """
        super().__init__(defaults=defaults)
        self.config_obj = config_obj
        self.changed_rows = []

    def _get_description_for_instance_var(self, var: str):
        from docstring_parser import parse as docstring_parse
        _, _, docs = get_function_definition(func=self.config_obj.__init__)
        for param in docstring_parse(docs).params:
            if param.arg_name == var:
                return param.description
        return ''

    @staticmethod
    def build_parser(interface: FilebeatTargetsInterface, parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        """Build a parser from any `BaseTargets` and `argparse.ArgumentParser` derived class
        Args:
            parser: The `argparse.ArgumentParser` instance that you want to add a new parser too
            interface: The `FilebeatTargetsInterface` instance you wish to append

        Returns:
            An argument parser instance for the instantiated `BaseTargets` derived class
        """
        target_options = parser.add_argument_group('target options')
        for var in vars(interface.config_obj):
            args = ArgparseParameters.create_from_typing_annotation(var, type(getattr(interface.config_obj, var)),
                                                                    required=False)
            if var == 'enabled':
                continue
            arg_description = interface._get_description_for_instance_var(var).replace('\n', ' ')
            args.add_description(arg_description)
            try:
                target_options.add_argument(*args.flags, **args.kwargs)
            except argparse.ArgumentError:
                continue
        target_options.add_argument('--enable', dest='enable', action='store_true', help=f'Enable selected target.')
        target_options.add_argument('--disable', dest='disable', action='store_true', help=f'Disable selected target')
        return parser

    def get_parser(self):
        """ For the given interface return an `argparse.ArgumentParser` object for a Filebeat `BaseTargets` object
        Returns:
            An argument parser instance for the instantiated `FilebeatTargetsInterface` derived class
        """
        parser = argparse.ArgumentParser()
        return self.build_parser(self, parser)

    def execute(self, args: argparse.Namespace) -> Any:
        """Interpret the results of an `argparse.ArgumentParser.parse_args()` method and perform one or more operations.
        Args:
            args: `argparse.Namespace` created by a method such as `argparse.ArgumentParser().parse_args()`

        Returns:
            Any value; completely depends on the parent interface's `ConfigManager.commit` method
        """
        self.changed_rows = []
        headers = ['Config Option', 'Value']
        table = []
        for option, value in args.__dict__.items():
            if option in ['enable', 'disable']:
                continue
            if option in self.defaults:
                continue
            if option in RESERVED_VARIABLE_NAMES:
                continue
            if not value:
                config_value = (option.replace('_', '-'), getattr(self.config_obj, option, None))
                if not config_value[1]:
                    config_value = option.replace('_', '-'), 'N/A'
                table.append(config_value)
            else:
                self.changed_rows.append([option.replace('_', '-'), value])
                setattr(self.config_obj, option, value)
        if args.enable:
            self.changed_rows.append(['enabled', True])
            self.config_obj.enabled = True
        elif args.disable:
            self.changed_rows.append(['enabled', False])
            self.config_obj.enabled = False

        if not self.changed_rows:
            table.append(['enabled', self.config_obj.enabled])
            return tabulate(table, tablefmt='fancy_grid', headers=headers)
        return self.config_obj


def append_config_object_analyzer_interface_to_parser(parser: argparse.ArgumentParser,
                                                      interface: AnalyzersInterface) -> argparse.ArgumentParser:
    """Append an `AnalyzersInterface` interface into an existing parser.
    Args:
        parser: The `argparse.ArgumentParser` instance that you want to add a new parser too
        interface: The `AnalyzerInterface` instance you wish to append

    Returns:
        The modified parser
    """
    return interface.build_parser(interface, parser)


def append_config_object_filebeat_targets_to_parser(parser: argparse.ArgumentParser,
                                                    interface: FilebeatTargetsInterface) -> argparse.ArgumentParser:
    """Append an `FilebeatTargetsInterface` interface into an existing parser.
    Args:
        parser: The `argparse.ArgumentParser` instance that you want to add a new parser too
        interface: The `FilebeatTargetsInterface` instance you wish to append

    Returns:
        The modified parser
    """

    return interface.build_parser(interface, parser)
