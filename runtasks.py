#!/usr/bin/env python3

import subprocess
import threading
import logging
import yaml
import argparse
import sys
import os
from string import Template

def run_app(cpuset: str, cmd_payload: str, args_list: list, repeat: int,
            global_logger: logging.Logger, working_dir: str):
    """
    Repeatedly launches the application on a specified cpuset using a dedicated working directory.

    The command payload (after variable substitution) can be either a single-line command or
    a multi-line script. If the payload contains newline characters, it is executed via bash (-c).

    All output (cpuset, pid, command, parameters, stdout, stderr) is logged to a single log file.
    The task repeats either a finite number of times or indefinitely (repeat=-1) until an error occurs.
    """
    iteration = 0
    # Create the working directory if it doesn't exist.
    os.makedirs(working_dir, exist_ok=True)

    while repeat == -1 or iteration < repeat:
        # Determine if the command payload is a script (contains newline)
        if "\n" in cmd_payload:
            # Treat as a script executed by bash.
            base_cmd = ["bash", "-c", cmd_payload] + args_list
        else:
            # Treat as a normal command.
            base_cmd = [cmd_payload] + args_list

        # Prepend taskset to set the CPU affinity.
        full_cmd_with_affinity = ["taskset", "-c", cpuset] + base_cmd

        # Start the subprocess with the dedicated working directory.
        process = subprocess.Popen(
            full_cmd_with_affinity,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_dir
        )
        pid = process.pid
        global_logger.info(
            f"Iteration {iteration+1} | cpuset: {cpuset} | cwd: {working_dir} | pid: {pid} | command: {' '.join(full_cmd_with_affinity)}"
        )

        # Wait for the process to complete and capture stdout and stderr.
        stdout_bytes, stderr_bytes = process.communicate()
        exit_code = process.returncode

        stdout = stdout_bytes.decode().strip() if stdout_bytes else ""
        stderr = stderr_bytes.decode().strip() if stderr_bytes else ""

        global_logger.info(f"Iteration {iteration+1} | pid: {pid} | stdout: {stdout}")
        global_logger.info(f"Iteration {iteration+1} | pid: {pid} | stderr: {stderr}")

        if exit_code != 0:
            global_logger.error(
                f"Iteration {iteration+1} | pid: {pid} | Error: Process exited with code {exit_code}"
            )
            # Stop further iterations on error.
            exit(-1)
        else:
            global_logger.info(
                f"Iteration {iteration+1} | pid: {pid} | Process exited successfully with code {exit_code}"
            )

        iteration += 1

def main():
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(
        description="Launch multiple copies of an application with specified cpusets from a YAML configuration file."
    )
    parser.add_argument(
        "config",
        metavar="TASKS_YAML",
        type=str,
        help="Path to the tasks YAML configuration file."
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress printing log output to stdout."
    )
    args = parser.parse_args()

    # Create a global logger that writes to a single log file.
    logger = logging.getLogger("app_logger")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Add a console (stdout) handler if not quiet.
    if not args.quiet:
        # File handler always enabled.
        file_handler = logging.FileHandler("app.log", mode="a")
        file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # Load tasks from the YAML configuration file.
    try:
        with open(args.config, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        sys.exit(f"Failed to load configuration file {args.config}: {e}")

    # Get top-level variables and tasks from the YAML.
    env_vars = config.get("vars", {})
    tasks = config.get("tasks", [])
    if not tasks:
        sys.exit(f"No tasks defined in {args.config}")

    threads = []
    # Process each task.
    for task_index, task in enumerate(tasks):
        raw_cpuset = task.get("cpuset")
        if not raw_cpuset:
            sys.exit("Each task must define a 'cpuset' field.")

        # Allow cpuset to be a list or a single string.
        cpusets = raw_cpuset if isinstance(raw_cpuset, list) else [raw_cpuset]

        raw_cmd = task.get("cmd")
        if not raw_cmd:
            sys.exit("Each task must define a 'cmd' field.")

        # Substitute variables in the command payload using the top-level variables.
        cmd_template = Template(raw_cmd)
        cmd_payload = cmd_template.safe_substitute(env_vars)

        # Process arguments (optional); default to an empty list.
        raw_args = task.get("args", [])
        args_list = [Template(arg).safe_substitute(env_vars) for arg in raw_args]

        # Determine the number of repetitions for the task (default is 1 if not specified).
        repeat = task.get("repeat", 1)

        # Launch a thread for each specified cpuset.
        for cpuset in cpusets:
            # Create a unique working directory for this task and cpuset.
            # For example: task_0_cpuset_0-3
            working_dir = f"task_{task_index}_cpuset_{cpuset}"
            os.makedirs(working_dir, exist_ok=True)

            t = threading.Thread(
                target=run_app,
                args=(cpuset, cmd_payload, args_list, repeat, logger, working_dir)
            )
            t.start()
            threads.append(t)

    # Wait for all tasks to complete.
    for t in threads:
        t.join()

if __name__ == '__main__':
    main()

