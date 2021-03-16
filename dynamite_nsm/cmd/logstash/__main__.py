from dynamite_nsm.cmd.logstash import get_action_parser
from dynamite_nsm.cmd.logstash import install, process, uninstall
from dynamite_nsm.services.logstash import process as process_service

if __name__ == '__main__':
    parser = get_action_parser()
    args = parser.parse_args()
    try:
        if args.sub_interface == 'install':
            install.interface.execute(args)
        elif args.sub_interface == 'uninstall':
            uninstall.interface.execute(args)
        elif args.sub_interface == 'process':
            result = process.interface.execute(args)
            if result:
                if args.action != 'status':
                    print(process_service.status(stdout=args.stdout, pretty_print_status=args.pretty_print_status,
                                                 verbose=args.verbose))
                else:
                    print(result)
    except AttributeError:
        parser.print_help()
