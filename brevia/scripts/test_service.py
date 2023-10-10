from logging import config, getLogger
from os import path, getcwd
import sys
import click
from dotenv import load_dotenv
import yaml
from brevia.async_jobs import create_service


# A `test_service.yml` in the root folder is needed.
# `service` and `payload` keys are required with this structure:
#
# service: brevia.extensions.my_extension.services.MyService
# output_path: path/to/output.txt
# payload:
#   file_path: /path/to/file
#   param1: value1
#   param2: value2

@click.command()
@click.option("-n", "--num", default=1, help="Number of attempts")
@click.option(
    "-f",
    "--file-path",
    default=f'{getcwd()}/test_service.yml',
    help="yaml file path"
)
def test_service(num: int = 1, file_path: str = f'{getcwd()}/test_service.yml'):
    """Service test"""
    load_dotenv()
    # allow module import from current working directory
    sys.path.append(getcwd())
    # initialize logging from optional log.ini
    log_ini_path = f'{getcwd()}/log.ini'
    if path.exists(log_ini_path):
        config.fileConfig(log_ini_path)

    if not path.isfile(file_path):
        raise FileNotFoundError(file_path)

    with open(file_path, 'r') as stream:
        parsed_yaml = yaml.safe_load(stream)

    attempt = 1
    while attempt <= num:
        test_run_service(
            service=parsed_yaml.get('service'),
            payload=parsed_yaml.get('payload'),
            output_path=parsed_yaml.get('output_path'),
            num_attempt=attempt,
        )
        attempt += 1


def test_save_result(file_path: str, num_attempt: int, output: str):
    """Save JOB result output to file, adding num attempt to file name"""
    file_name, file_extension = path.splitext(file_path)

    with open(f'{file_name}-{num_attempt}{file_extension}', 'w') as stream:
        stream.write(output)


def test_run_service(
    service: str,
    payload: dict,
    output_path: str = None,
    num_attempt: int = 1
):
    """Create and run service"""
    service = create_service(service)
    log = getLogger(__file__)
    attempt_message = f'Attempt: {num_attempt} - File: {payload.get("file_path")}'
    log.info('%s - start', attempt_message)
    result = service.run(payload)
    log.info('%s - end', attempt_message)

    if output_path is None:
        log.info('%s - `output_path` not specified, file not saved', attempt_message)
    else:
        test_save_result(
            file_path=output_path,
            num_attempt=num_attempt,
            output=result.get('output')
        )
