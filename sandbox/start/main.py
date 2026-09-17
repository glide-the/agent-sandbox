import argparse
import asyncio
import logging
import logging.config
import os
from argparse import Namespace

from sandbox.common.logs import get_config_dict, get_log_file, get_timestamp_ms
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.server_init import dispatch as dispatch_web

# 需要显式引用
from sandbox.server.servlet.boot.runner_bootstrap import RunnerBootstrapBaseWeb
from sandbox.start import Speaker, WebSpeaker
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger('start_logger')


async def dispatch(args: Namespace):
    args_dict = vars(args)

    logger.info(f'Running in {args.mode} mode')

    if args.mode in 'demo':

        speaker = Speaker(speakers_config_file=args.speakers_config_file, verbose=args.verbose)
        await speaker.preparation_runner(task_id="0", payload=PayLoad())
    elif args.mode in 'web':

        logging_conf = get_config_dict(
            "info",
            get_log_file(log_path="logs", sub_dir=f"web_{get_timestamp_ms()}"),
            1024 * 1024 * 1024 * 3,
            1024 * 1024 * 1024 * 3,
            )
        logging.config.dictConfig(logging_conf)  # type: ignore
        await dispatch_web(speakers_config_file=args.speakers_config_file)

    elif args.mode in 'web_runner':

        logging_conf = get_config_dict(
            "info",
            get_log_file(log_path="logs", sub_dir=f"web_runner_{get_timestamp_ms()}"),
            1024 * 1024 * 1024 * 3,
            1024 * 1024 * 1024 * 3,
            )

        logging.config.dictConfig(logging_conf)  # type: ignore
        logger.info(f"""
        Running in web_runner mode
        Nonce: {args.nonce}
        """)
        translator = WebSpeaker(speakers_config_file=args.speakers_config_file, verbose=args.verbose, nonce=args.nonce)
        await translator.listen()


def main():
    parser = argparse.ArgumentParser(prog='speakers',
                                     description='S')
    parser.add_argument('-m', '--mode', default='demo', type=str, choices=['demo', 'web', 'web_runner'],
                        help='Run ')

    parser.add_argument('-v', '--verbose', action='store_true', help='Print debug info in result folder')
    parser.add_argument("--speakers-config-file", type=str, default="sandbox.yaml")
    parser.add_argument('--nonce', default='', type=str, help='Used by web module to decide which secret for securing '
                                                              'internal web server communication')

    args = None
    try:
        args = parser.parse_args()
        asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        if not args or args.mode != 'web':
            print()
    except Exception as e:
        logger.error(f'{e.__class__.__name__}: {e}',
                     exc_info=e if args and args.verbose else None)


if __name__ == '__main__':
    main()
