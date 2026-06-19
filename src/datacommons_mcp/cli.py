# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""CLI module for Data Commons MCP server.

This module provides the command-line interface for running the
Data Commons MCP server in different transport modes.
"""

import logging
import os
import sys
from pathlib import Path

import click

from .version import __version__


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """DataCommons MCP CLI - Model Context Protocol server for Data Commons."""
    logging.basicConfig(level=logging.INFO)


@cli.group()
def serve() -> None:
    """Serve the MCP server in different modes."""


@serve.command()
@click.option("--host", default="localhost", help="Host to bind.")
@click.option("--port", default=8080, help="Port to bind.", type=int)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
@click.option(
    "--storage-dir",
    default=None,
    type=click.Path(),
    help="Directory for storing exported data files (overrides DC_STORAGE_DIR).",
)
def http(
    host: str,
    port: int,
    verbose: bool,
    storage_dir: str | None,
) -> None:
    """Start the MCP server in Streamable HTTP mode."""
    # Set storage directory environment variable if provided via CLI
    if storage_dir:
        os.environ["DC_STORAGE_DIR"] = storage_dir

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        from datacommons_mcp.fastmcp_server import mcp

        click.echo("Starting DataCommons MCP server in Streamable HTTP mode")
        click.echo(f"Version: {__version__}")
        click.echo(f"Server URL: http://{host}:{port}")
        click.echo(f"Streamable HTTP endpoint: http://{host}:{port}/mcp")
        click.echo("Press CTRL+C to stop")

        mcp.run(host=host, port=port, transport="streamable-http")

    except ImportError as e:
        click.echo(f"Error importing server: {e}", err=True)
        sys.exit(1)


@serve.command()
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
@click.option(
    "--storage-dir",
    default=None,
    type=click.Path(),
    help="Directory for storing exported data files (overrides DC_STORAGE_DIR).",
)
def stdio(verbose: bool, storage_dir: str | None) -> None:
    """Start the MCP server in stdio mode."""
    # Set storage directory environment variable if provided via CLI
    if storage_dir:
        os.environ["DC_STORAGE_DIR"] = storage_dir

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        from datacommons_mcp.fastmcp_server import mcp

        click.echo("Starting DataCommons MCP server in stdio mode", err=True)
        click.echo(f"Version: {__version__}", err=True)
        if verbose:
            click.echo("Verbose logging enabled", err=True)
        click.echo("Server is ready to receive requests via stdin/stdout", err=True)

        mcp.run(transport="stdio")

    except ImportError as e:
        click.echo(f"Error importing server: {e}", err=True)
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    # Set working directory to user's home to avoid macOS TCC prompts
    # when cwd is / (root). Claude Desktop launches extensions without
    # setting cwd, which causes privacy permission dialogs for every
    # protected directory (Desktop, Documents, Google Drive, etc.)
    os.chdir(Path.home())
    cli()


if __name__ == "__main__":
    main()
