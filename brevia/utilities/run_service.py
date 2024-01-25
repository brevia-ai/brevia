"""Utility functions to run services"""
from logging import getLogger
from os import path
import yaml
from brevia.async_jobs import create_service


def run_service_from_yaml(file_path: str, num_attempts: int = 1):
    """Run service from YAML file"""
    if not path.isfile(file_path):
        raise FileNotFoundError(file_path)

    with open(file_path, 'r') as stream:
        parsed_yaml = yaml.safe_load(stream)

    attempt = 1
    while attempt <= num_attempts:
        run_service(
            service=parsed_yaml.get('service'),
            payload=parsed_yaml.get('payload'),
            output_path=parsed_yaml.get('output_path'),
            num_attempt=attempt,
        )
        attempt += 1


def save_test_result(file_path: str, num_attempt: int, output: str):
    """Save JOB result output to file, adding num attempt to file name"""
    file_name, file_extension = path.splitext(file_path)

    with open(f'{file_name}-{num_attempt}{file_extension}', 'w') as stream:
        stream.write(output)


def run_service(
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
        save_test_result(
            file_path=output_path,
            num_attempt=num_attempt,
            output=result.get('output')
        )
