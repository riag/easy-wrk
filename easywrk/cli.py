# coding: utf8

import sys
import argparse
from argparse import ArgumentParser
import logging

from easywrk.commands import help_command, run_command, view_config_command
from easywrk.commands import list_command, init_command
from easywrk.commands import register_cmd_help


def setup_config_argparse(parser:ArgumentParser):
    parser.add_argument(
        "-c", "--config", 
        dest="config_file", 
        default="./easywrk.toml",
        help="Location of the config file, default is easywrk.toml in current working directory."
        )
    parser.add_argument(
        "-f", "--file",
        dest="env_file",
        default="./.env",
        help="Location of the .env file, defaults to .env file in current working directory."
    )


def setup_argparse():

    parser = argparse.ArgumentParser(prog='easywrk')

    subparsers = parser.add_subparsers(
        title='These are common easywrk commands used in various situations',
        metavar='command')

    name = "help"
    help_parser = subparsers.add_parser(
        name,
        help="print command help"
    )
    help_parser.set_defaults(handle=help_command)
    register_cmd_help(name, help_parser)

    help_parser.add_argument(
        "name", nargs=1, 
        help="command name"
    )

    name = "init"
    init_parser = subparsers.add_parser(
        name, 
        help="create config file in current directory"
    )
    init_parser.set_defaults(handle=init_command)
    register_cmd_help(name, init_parser)

    name = "run"
    run_parser = subparsers.add_parser(
        name, 
        help="run single benchmark api"
    )
    run_parser.set_defaults(handle=run_command)
    register_cmd_help(name, run_parser)

    run_parser.add_argument(
        "name", nargs=1, 
        help="api name"
        )
    setup_config_argparse(run_parser)

    name = "view-config"
    view_config_parser = subparsers.add_parser(
        name,
        help="view config file"
    )
    view_config_parser.set_defaults(handle=view_config_command)
    register_cmd_help(name, view_config_parser)

    setup_config_argparse(view_config_parser)

    name = "list"
    list_parser = subparsers.add_parser(
        name, 
        help="list all api name and desc"
    )
    list_parser.set_defaults(handle = list_command)
    register_cmd_help(name, list_parser)

    setup_config_argparse(list_parser)

    return parser


def cli(argv, other_argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = setup_argparse()
    args = parser.parse_args(argv)
    if hasattr(args, 'handle'):
        args.handle(args, other_argv)
    else:
        parser.print_help()

def main():
    argv = sys.argv[1:]
    other_argv = None
    index = None
    for i, arg in enumerate(argv):
        if arg == '--':
            index = i
            break

    if index is not None:
        other_argv = argv[index+1:]
        argv = argv[:index]

    cli(argv, other_argv)



if __name__ == '__main__':
    main()