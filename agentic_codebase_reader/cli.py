"""CLI entry-point for Codebase Reader."""
from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    """Run the full pipeline from the command line.

    Usage::

        codebase-reader <github_url> [--mode docs|readme]

    Examples::

        codebase-reader https://github.com/tiangolo/fastapi
        codebase-reader https://github.com/pallets/flask --mode readme
    """
    parser = argparse.ArgumentParser(
        prog="codebase-reader",
        description="Generate documentation or a README for any public GitHub repository.",
    )
    parser.add_argument(
        "repo_url",
        help="Public GitHub repository URL (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--mode",
        choices=["docs", "readme"],
        default="docs",
        help=(
            "Output mode: 'docs' generates a full technical reference (default), "
            "'readme' generates a concise GitHub README.md."
        ),
    )
    args = parser.parse_args()

    repo_url: str = args.repo_url
    mode: str = args.mode

    try:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn

        console = Console()

        async def _run() -> None:
            from agentic_codebase_reader.agents.supervisor import Supervisor

            supervisor = Supervisor()
            label = "README" if mode == "readme" else "docs"
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]Generating {label} for {repo_url}…", total=None
                )
                report = await supervisor.run(repo_url, mode=mode)
                progress.update(task, completed=True)

            console.print(
                f"\n[bold green]✓ {label.capitalize()} generated![/bold green]\n"
                f"  Output: [cyan]{report.output_path}[/cyan]"
            )

        asyncio.run(_run())

    except ImportError:
        # Fallback if rich is not installed.
        async def _run_plain() -> None:
            from agentic_codebase_reader.agents.supervisor import Supervisor

            print(f"Generating {mode} for {repo_url}…")
            report = await Supervisor().run(repo_url, mode=mode)
            print(f"Done! Output: {report.output_path}")

        asyncio.run(_run_plain())

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
